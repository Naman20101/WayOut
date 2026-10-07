"""Read preserved sources, crop locally and create inspectable JSON datasets.

No missing values are filled with fabricated observations. The Kochi source
units are unconfirmed: only mapped flood membership is used, never fake depth.

NASA SRTMGL1 v003 supplies elevation and slope. Both are stored in the same
risk_scores table as hazards 'elevation' and 'slope' with original values
in metres and degrees respectively.

For custom regions (id starting 'custom_'), global hazards are also sampled:
  river_flood  — JRC Global River Flood Hazard Map, depth in metres
  landslide    — NASA SEDAC Global Landslide Hazard, class 1..10

The radius is taken from each region's config, defaulting to 15 000 m.
"""
import argparse, csv, io, json, math, sys, zipfile, collections
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.features import shapes
import shapefile
from shapely.geometry import shape, mapping, Point, LineString, box
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer, CRS
from backend.config import REGIONS, BASE_DIR
from backend.scripts.crop_regions import circle, distance
from backend.scripts.calculate_risk import (rank_score, mmi_score,
                                            elevation_score, slope_score)
import backend.scripts.srtm as srtm_mod


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False,
                               separators=(',', ':')), encoding='utf8')


def shp_records(path, suffix=None):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(suffix or '.shp'))
        base = name[:-4]
        reader = shapefile.Reader(
            shp=io.BytesIO(z.read(name)),
            shx=io.BytesIO(z.read(base + '.shx')),
            dbf=io.BytesIO(z.read(base + '.dbf')),
            encoding='cp932')
        project = Transformer.from_crs(
            CRS.from_wkt(z.read(base + '.prj').decode()), 4326,
            always_xy=True).transform
        return [(transform(project, shape(s.__geo_interface__)), r.as_dict())
                for s, r in zip(reader.shapes(), reader.records())]


# ---------------------------------------------------------------------------
# Samplers
# ---------------------------------------------------------------------------

def srtm_sampler(region):
    """Return a callable sampling elevation (m) and slope (deg) per WGS84 point."""
    raw = BASE_DIR / 'data/raw' / region / 'srtm'
    if not raw.exists():
        print(f'[srtm] no directory for {region}', flush=True)
        return None
    elev, slope = srtm_mod.load_region_tiles(raw)
    if not elev:
        print(f'[srtm] no tiles for {region}; terrain will be absent', flush=True)
        return None
    print(f'[srtm] loaded {sorted(elev)} for {region}', flush=True)

    def sample(coords):
        els, sls = [], []
        for lon, lat in coords:
            els.append(srtm_mod.lookup(elev, lat, lon))
            sls.append(srtm_mod.lookup(slope, lat, lon))
        return {'elevation': els, 'slope': sls}
    return sample


def hazards_sampler(region):
    """Global flood and landslide rasters for custom regions only.

    Returns a sampler producing keys 'river_flood' (metres) and
    'landslide' (class 1..10), or None if unavailable.
    """
    if not str(region).startswith('custom_'):
        return None
    try:
        from backend.hazards import build_sampler
        cfg = REGIONS.get(region)
        if not cfg:
            print(f'[hazards] region {region} not in REGIONS; skipping',
                  flush=True)
            return None
        boundary = circle(cfg['lat'], cfg['lon'], cfg.get('radius_m', 3000))
        sampler = build_sampler(mapping(boundary), cfg['lat'], cfg['lon'],
                                hazards=('flood', 'landslide'))
        if sampler:
            print('[hazards] global sampler enabled for', region, flush=True)
        return sampler
    except Exception as exc:
        print(f'[hazards] global sampler unavailable: {exc}', flush=True)
        return None


def compose(*samplers):
    active = [s for s in samplers if s]
    if not active:
        return None
    if len(active) == 1:
        return active[0]

    def combined(coords):
        out = {}
        for s in active:
            out.update(s(coords))
        return out
    return combined


# ---------------------------------------------------------------------------
# Primary hazard layers per study region
# ---------------------------------------------------------------------------

def layers(region, boundary, out):
    raw = BASE_DIR / 'data/raw' / region
    features = []
    primary = None

    if region == 'kochi' and (raw / 'flood_10_25_50.zip').exists():
        archive = raw / 'flood_10_25_50.zip'
        with zipfile.ZipFile(archive) as z:
            name = next(n for n in z.namelist()
                        if n.endswith('50_yr_Historical.tif'))
        with rasterio.open(f'zip://{archive.as_posix()}!{name}') as ds:
            data, affine = mask(ds, [mapping(boundary)],
                                crop=True, filled=False)
            band = data[0]
            valid = ~np.ma.getmaskarray(band)
            profile = ds.profile
            profile.update(height=band.shape[0], width=band.shape[1],
                           transform=affine)
            with rasterio.open(out / 'flood_50yr.tif', 'w', **profile) as target:
                target.write(data.filled(ds.nodata))
            for geom, _ in shapes(valid.astype('uint8'),
                                  mask=valid, transform=affine):
                g = shape(geom).intersection(boundary)
                if not g.is_empty:
                    features.append({
                        'type': 'Feature', 'geometry': mapping(g),
                        'properties': {
                            'layer': 'flood',
                            'name': '50-year mapped flood footprint',
                            'score': 100,
                            'source': 'ksdma_flood',
                            'note': ('Membership only. Raw units unconfirmed; '
                                     'blank area is unknown, not dry.')}})

            def flood_sampler(coords):
                vals = []
                for x, y in coords:
                    col, row = ~affine * (x, y)
                    row, col = int(math.floor(row)), int(math.floor(col))
                    ok = (0 <= row < band.shape[0]
                          and 0 <= col < band.shape[1]
                          and valid[row, col])
                    vals.append(float(band[row, col]) if ok else None)
                return {'flood': vals}
            primary = flood_sampler

    elif region == 'kathmandu' and (raw / 'shakemap_grid.xml').exists():
        root = ET.parse(raw / 'shakemap_grid.xml').getroot()
        ns = {'s': root.tag.split('}')[0].strip('{')}
        fields = {f.attrib['name']: int(f.attrib['index']) - 1
                  for f in root.findall('s:grid_field', ns)}
        a = np.fromstring(root.find('s:grid_data', ns).text,
                          sep=' ').reshape(-1, len(fields))
        cells = {(round(float(v[fields['LON']]), 4),
                  round(float(v[fields['LAT']]), 4)):
                 float(v[fields['MMI']]) for v in a}
        lons = np.unique(a[:, fields['LON']])
        lats = np.unique(a[:, fields['LAT']])

        def shakemap_sampler(coords):
            vals = []
            for x, y in coords:
                if not lons[0] <= x <= lons[-1] or not lats[0] <= y <= lats[-1]:
                    vals.append(None); continue
                xx = lons[np.argmin(abs(lons - x))]
                yy = lats[np.argmin(abs(lats - y))]
                vals.append(cells.get((round(float(xx), 4),
                                       round(float(yy), 4))))
            return {'shaking': vals}

        dx = float(np.median(np.diff(lons))) / 2
        dy = float(np.median(np.diff(lats))) / 2
        for (x, y), v in cells.items():
            if boundary.contains(Point(x, y)):
                features.append({
                    'type': 'Feature',
                    'geometry': mapping(
                        box(x - dx, y - dy, x + dx, y + dy).intersection(boundary)),
                    'properties': {
                        'layer': 'shaking',
                        'name': f'2015 Gorkha: MMI {v}',
                        'score': mmi_score(v),
                        'original_value': v,
                        'source': 'usgs_gorkha'}})
        primary = shakemap_sampler

    elif region == 'tokyo' and (raw / 'regional_risk.zip').exists():
        records = []
        for g, p in shp_records(raw / 'regional_risk.zip'):
            if not g.is_valid:
                g = g.buffer(0)
            if g.intersects(boundary):
                clipped = g.intersection(boundary)
                props = {'layer': 'collapse',
                         'name': f"{p['区市町村名']} {p['町丁目名']}",
                         'score': rank_score(p['建物_ラ']),
                         'collapse_rank': p['建物_ラ'],
                         'fire_rank': p['火災_ラ'],
                         'accessibility': p['災害_係'],
                         'ground_note': 'Neighbourhood proxy; not building inspection',
                         'source': 'tmg_risk'}
                records.append((clipped, props))
                features.append({'type': 'Feature',
                                 'geometry': mapping(clipped),
                                 'properties': props})
        tree = STRtree([r[0] for r in records])

        def tmg_sampler(coords):
            values = {'collapse': [], 'fire': [], 'accessibility': []}
            for x, y in coords:
                matches = tree.query(Point(x, y), predicate='intersects')
                p = records[int(matches[0])][1] if len(matches) else None
                for key, field in [('collapse', 'collapse_rank'),
                                   ('fire', 'fire_rank'),
                                   ('accessibility', 'accessibility')]:
                    values[key].append(p[field] if p else None)
            return values

        if (raw / 'ground_0.zip').exists():
            for g, p in shp_records(raw / 'ground_0.zip'):
                if boundary.contains(g):
                    features.append({
                        'type': 'Feature', 'geometry': mapping(g),
                        'properties': {
                            'layer': 'ground',
                            'name': f"Borehole PL: {p['PL_Dist']}",
                            'source': 'tmg_ground',
                            'note': 'Point observation; not interpolated'}})
        if (raw / 'ground_2.zip').exists():
            for g, p in shp_records(
                    raw / 'ground_2.zip',
                    'eqliq_2011TohokuEarthquake_polygon.shp'):
                if not g.is_valid:
                    g = g.buffer(0)
                if g.intersects(boundary):
                    features.append({
                        'type': 'Feature',
                        'geometry': mapping(g.intersection(boundary)),
                        'properties': {
                            'layer': 'liquefaction',
                            'name': '2011 reported liquefaction area',
                            'source': 'tmg_ground',
                            'note': 'Historical footprint, not current prediction'}})
        primary = tmg_sampler

    sampler = compose(primary, srtm_sampler(region), hazards_sampler(region))
    write(out / 'hazards.geojson',
          {'type': 'FeatureCollection', 'features': features})
    return sampler


# ---------------------------------------------------------------------------
# Road classification
# ---------------------------------------------------------------------------

def modes(tags):
    h = tags.get('highway', '')
    access = tags.get('access')
    restricted = access in ('no', 'private')

    def allow(k, default):
        return (tags.get(k) in ('yes', 'designated', 'permissive')
                or (tags.get(k) not in ('no', 'private')
                    and not restricted and default))
    walk = allow('foot', h not in ('motorway', 'motorway_link',
                                    'trunk', 'trunk_link'))
    bike = allow('bicycle', h not in ('motorway', 'motorway_link',
                                       'trunk', 'trunk_link', 'steps'))
    car = allow('motor_vehicle', h not in ('footway', 'path', 'pedestrian',
                                            'steps', 'cycleway', 'bridleway',
                                            'corridor'))
    if tags.get('motorcar') in ('no', 'private') or tags.get('vehicle') == 'no':
        car = False
    if tags.get('vehicle') == 'no' and \
       tags.get('bicycle') not in ('yes', 'designated'):
        bike = False
    return walk, bike, car


def _score_hazard(hazard, good, region):
    """Return (scores, rule_version) for one hazard's sampled values."""
    if hazard == 'flood':
        return [100 for _ in good], 'flood-footprint-v1; raw units unresolved'
    if hazard == 'river_flood':
        from backend.hazards import flood_score
        return [flood_score(v) for v in good], 'jrc-flood-depth-v1'
    if hazard == 'landslide':
        from backend.hazards import landslide_score
        return [landslide_score(v) for v in good], 'sedac-landslide-class-v1'
    if hazard == 'shaking':
        return [mmi_score(v) for v in good], 'mmi-linear-1-to-10-v1'
    if hazard in ('collapse', 'fire'):
        return [rank_score(v) for v in good], 'ordinal-rank-times20-v1'
    if hazard == 'accessibility':
        return [min(100, max(0, v * 100)) for v in good], \
               'activity-coefficient-times100-v1'
    if hazard == 'elevation':
        return [elevation_score(v, region) for v in good], \
               f'elevation-band-{region}-v1'
    if hazard == 'slope':
        return [slope_score(v) for v in good], 'slope-2-to-15-deg-v1'
    raise ValueError(f'Unknown hazard: {hazard}')


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process(region):
    cfg = REGIONS[region]
    raw = BASE_DIR / 'data/raw' / region
    out = BASE_DIR / 'data/processed' / region
    out.mkdir(parents=True, exist_ok=True)
    boundary = circle(cfg['lat'], cfg['lon'], cfg.get('radius_m', 15000))
    sample = layers(region, boundary, out)

    with open(raw / 'osm.json', 'rb') as fh:
        obj = json.load(fh)
    elements = {(e['type'], e['id']): e for e in obj['elements']}
    del obj

    nodes = {e['id']: [e['lon'], e['lat']] for e in elements.values()
             if e['type'] == 'node' and 'lat' in e}
    ways = [e for e in elements.values()
            if e['type'] == 'way'
            and e.get('tags', {}).get('highway') not in
                (None, 'construction', 'proposed', 'platform', 'raceway')]

    # Drop heavy per-way fields we no longer need to reduce peak memory.
    ways = [{'id': w['id'], 'tags': w['tags'], 'nodes': w['nodes']} for w in ways]

    counts = collections.Counter(n for w in ways for n in set(w['nodes']))
    projector = Transformer.from_crs(4326, cfg['epsg'], always_xy=True).transform
    unprojector = Transformer.from_crs(cfg['epsg'], 4326, always_xy=True).transform

    radius_m = cfg.get('radius_m', 15000)
    inside = {n for n, xy in nodes.items()
              if distance((cfg['lon'], cfg['lat']), xy) <= radius_m}

    edges = []
    used = set()
    road_features = []
    for way in ways:
        tags = way['tags']
        walk, bike, car = modes(tags)
        if not any((walk, bike, car)):
            continue
        oneway = (-1 if tags.get('oneway') == '-1' else
                  (1 if tags.get('oneway') in ('yes', '1', 'true')
                        or (tags.get('junction') == 'roundabout'
                            and tags.get('oneway') != 'no') else 0))
        chain = []
        for n in way['nodes']:
            if n not in inside:
                chain = []
                continue
            chain.append(n)
            if len(chain) > 1 and (counts[n] > 1 or n == way['nodes'][-1]):
                coords = [nodes[k] for k in chain]
                g = LineString(coords)
                metric = transform(projector, g)
                length = metric.length
                if length < 0.2 or chain[0] == chain[-1]:
                    chain = [n]
                    continue
                risk = {}
                if sample:
                    intervals = max(1, math.ceil(length / 40))
                    pts = [transform(unprojector,
                                     metric.interpolate(
                                         length * (i + 0.5) / intervals))
                           for i in range(intervals)]
                    values = sample([(p.x, p.y) for p in pts])
                    for hazard, vs in values.items():
                        good = [v for v in vs if v is not None]
                        if not good:
                            continue
                        scores, rule = _score_hazard(hazard, good, region)
                        risk[hazard] = {
                            'original': sum(good) / len(good),
                            'score': sum(scores) / len(scores) if scores else None,
                            'coverage': len(good) / len(vs),
                            'rule': rule,
                        }
                t = {k: v for k, v in tags.items()
                     if k in ('surface', 'bridge', 'tunnel', 'access', 'foot',
                              'bicycle', 'motor_vehicle', 'oneway:bicycle',
                              'name:en')}
                t['_coords'] = coords
                e = {'way': way['id'], 'u': chain[0], 'v': chain[-1],
                     'length': length,
                     'name': tags.get('name:en',
                                      tags.get('name', 'Unnamed road'))[:250],
                     'highway': tags['highway'],
                     'walk': walk, 'bicycle': bike, 'car': car,
                     'oneway': oneway, 'tags': t, 'risk': risk}
                edges.append(e)
                used.update((chain[0], chain[-1]))
                road_features.append({
                    'type': 'Feature',
                    'geometry': mapping(g.simplify(.00005)),
                    'properties': {'way': way['id'],
                                   'name': e['name'],
                                   'highway': e['highway']}})
                chain = [n]

    locations = []
    for e in elements.values():
        t = e.get('tags', {})
        name = t.get('name:en', t.get('name'))
        kind = t.get('amenity', t.get('place'))
        if not name or not kind:
            continue
        center = e.get('center', e)
        if 'lon' not in center:
            continue
        if distance((cfg['lon'], cfg['lat']),
                    (center['lon'], center['lat'])) > radius_m:
            continue
        locations.append({'osm_id': e['id'], 'name': name[:250],
                          'local_name': t.get('name', ''), 'kind': kind,
                          'lat': center['lat'], 'lon': center['lon']})

    write(out / 'graph.json',
          {'nodes': {str(n): nodes[n] for n in used}, 'edges': edges})
    write(out / 'roads.geojson',
          {'type': 'FeatureCollection', 'features': road_features})
    write(out / 'locations.json', locations)

    srtm_used = any('elevation' in e['risk'] for e in edges)
    global_used = any(('river_flood' in e['risk'] or 'landslide' in e['risk'])
                      for e in edges)
    summary = {'region': region, 'nodes': len(used), 'edges': len(edges),
               'locations': len(locations),
               'radius_m': radius_m, 'sampling_m': 40,
               'srtm_applied': srtm_used,
               'global_hazards_applied': global_used,
               'limitations': [
                   'Turn-restriction relations and conditional access not '
                   'modelled. Planning only; not turn-by-turn directions.',
                   'No road passability or facility opening feed.',
                   'SRTM elevation is a relative-terrain indicator, not a '
                   'flood depth.',
                   'Global flood and landslide values are planning indices, '
                   'not official hazard forecasts.']}
    write(out / 'summary.json', summary)
    print(region, summary, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--region', choices=list(REGIONS), required=True)
    process(p.parse_args().region)