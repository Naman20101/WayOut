"""Import a processed region transactionally; only replace WAYOUT regional data."""
import argparse, csv, hashlib, json, sys, unicodedata
from pathlib import Path
from backend.config import BASE_DIR, REGIONS
from backend.db import connection
from backend.database_setup import setup
from backend.routing.graph_builder import invalidate


SOURCE_INFO = {
 'ksdma_flood': ('kochi', 'Historical 50-year flood footprint',
   'KSDMA / UNEP / CIMA', 'https://sdma.kerala.gov.in/hazard-maps/',
   '2020 study; 2026 archive', 'GeoTIFF',
   'Reuse terms need confirmation; retain publisher attribution',
   True, 'flood_10_25_50.zip'),
 'usgs_gorkha': ('kathmandu', 'Gorkha earthquake ShakeMap Atlas', 'USGS',
   'https://earthquake.usgs.gov/earthquakes/eventpage/us20002926',
   '2015 event; 2020 Atlas product', 'XML grid',
   'USGS attribution; inspect contributing data terms', True,
   'shakemap_grid.xml'),
 'iom_spaces': ('kathmandu', '83 humanitarian open spaces', 'IOM',
   'https://publications.iom.int/books/updated-report-83-open-spaces-identified-humanitarian-purposes-kathmandu-valley',
   '2020', 'PDF', 'Publication rights; attribution retained',
   True, 'iom_open_spaces.pdf'),
 'tmg_risk': ('tokyo', 'Ninth neighbourhood earthquake risk assessment',
   'Tokyo Metropolitan Government',
   'https://www.funenka.metro.tokyo.lg.jp/area-hazard-level/regional-risk-list/index.html',
   '2022', 'Shapefile / CSV',
   'Dataset reuse terms to confirm before redistribution', True,
   'regional_risk.zip'),
 'tmg_ground': ('tokyo', 'PL observations and liquefaction history',
   'Tokyo Metropolitan Government',
   'https://doboku.metro.tokyo.lg.jp/start/03-jyouhou/ekijyoukaEn/top.aspx',
   '2026 download; observation years vary', 'Shapefile',
   'CC BY 2.1 Japan; derived geometry labelled', True, 'ground_0.zip'),
 'sumida_shelters': ('tokyo',
   'Sumida designated assembly / evacuation / shelter list',
   'Sumida ward',
   'https://www.city.sumida.lg.jp/kuseijoho/sumida_info/opendata/opendata_ichiran/bosai_data/hinan_data.html',
   '2022-03-01', 'CSV', 'CC BY 2.1 Japan', True, 'hinan_20220301.csv'),
 'nasa_srtm': ('_all_', 'NASA SRTMGL1 v003 elevation and derived slope',
   'NASA LP DAAC / USGS EROS',
   'https://lpdaac.usgs.gov/products/srtmgl1v003/',
   '2000 mission; 2026 download', 'HGT raster (int16)',
   'NASA open data; retain product citation and per-tile provenance',
   True, 'srtm/'),
}


def _folder_hash(folder):
    h = hashlib.sha256()
    for p in sorted(folder.glob('*.metadata.json')):
        h.update(p.read_bytes())
    return h.hexdigest()


def _insert_source(cur, key, region, name, org, url, year, fmt, licence,
                   official, file):
    raw_root = BASE_DIR / 'data/raw' / region
    meta = raw_root / (file + '.metadata.json')
    sha = None
    if meta.exists():
        sha = json.loads(meta.read_text(encoding='utf8'))['sha256']
    elif (raw_root / file).is_dir():
        sha = _folder_hash(raw_root / file)
    cur.execute(
        'INSERT INTO data_sources(id,region_id,dataset_name,organisation,url,'
        'accessed_at,observation_year,coverage,variables_used,format,licence,'
        'official,status,preprocessing,sha256) VALUES(' +
        ','.join(['%s'] * 15) + ') '
        'ON DUPLICATE KEY UPDATE dataset_name=VALUES(dataset_name), '
        'url=VALUES(url), status=VALUES(status), sha256=VALUES(sha256)',
        (key, region, name, org, url, '2026-09-17', year,
         '15 km study-circle crop',
         'See methodology and preserved original fields',
         fmt, licence, official,
         'Downloaded; processed with documented limitations',
         'Crop, CRS conversion, 40 m line sampling; retain original values',
         sha))


def source_rows(cur, region):
    cfg = REGIONS[region]
    cur.execute(
        'INSERT INTO regions(id,name,latitude,longitude,primary_hazard) '
        'VALUES(%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE name=VALUES(name)',
        (region, cfg['name'], cfg['lat'], cfg['lon'], cfg['hazard']))

    sources = dict(SOURCE_INFO)
    sources['osm_' + region] = (
        region, 'Local OpenStreetMap road / infrastructure extract',
        'OpenStreetMap contributors',
        'https://www.openstreetmap.org/copyright',
        'Snapshot 2026-09-17', 'OSM JSON', 'ODbL 1.0', False, 'osm.json')

    for key, (r, name, org, url, year, fmt, licence, official, file) in sources.items():
        if r == '_all_':
            if not (BASE_DIR / 'data/raw' / region / file).exists():
                continue
            _insert_source(cur, key, region, name, org, url, year, fmt, licence,
                           official, file)
            continue
        if r != region:
            continue
        if not (BASE_DIR / 'data/raw' / r / file).exists():
            continue
        _insert_source(cur, key, r, name, org, url, year, fmt, licence,
                       official, file)


def import_region(region):
    setup()
    p = BASE_DIR / 'data/processed' / region
    data = json.loads((p / 'graph.json').read_text(encoding='utf8'))
    locations = json.loads((p / 'locations.json').read_text(encoding='utf8'))
    hazards = json.loads((p / 'hazards.geojson').read_text(encoding='utf8'))

    with connection() as conn:
        c = conn.cursor()
        for table in ['admin_simulations', 'shelters', 'locations',
                      'hazard_zones', 'hazard_history']:
            c.execute(f'DELETE FROM {table} WHERE region_id=%s', (region,))
        c.execute('DELETE FROM road_edges WHERE region_id=%s', (region,))
        c.execute('DELETE FROM road_nodes WHERE region_id=%s', (region,))

        source_rows(c, region)

        rows = [(region, int(k), xy[1], xy[0])
                for k, xy in data['nodes'].items()]
        for i in range(0, len(rows), 4000):
            c.executemany('INSERT INTO road_nodes(region_id,id,latitude,longitude) '
                          'VALUES(%s,%s,%s,%s)', rows[i:i + 4000])

        offset = {'kochi': 1000000, 'kathmandu': 2000000, 'tokyo': 3000000}[region]
        source = {'kochi': 'ksdma_flood', 'kathmandu': 'usgs_gorkha',
                  'tokyo': 'tmg_risk'}[region]

        for start in range(0, len(data['edges']), 1500):
            batch = []
            risks = []
            for idx, e in enumerate(data['edges'][start:start + 1500], start):
                edge_id = offset + idx
                batch.append((edge_id, region, e['way'], e['u'], e['v'],
                              e['length'], e['name'], e['highway'], e['walk'],
                              e['bicycle'], e['car'], e['oneway'],
                              json.dumps(e['tags'], ensure_ascii=False)))
                for h, v in e['risk'].items():
                    src = 'nasa_srtm' if h in ('elevation', 'slope') else source
                    risks.append((edge_id, src, h, v['original'], v['score'],
                                  v['coverage'], v['rule']))
            c.executemany(
                'INSERT INTO road_edges(id,region_id,osm_way_id,from_node,'
                'to_node,distance_m,name,highway,walk,bicycle,car,oneway,tags) '
                'VALUES(' + ','.join(['%s'] * 13) + ')', batch)
            if risks:
                c.executemany(
                    'INSERT INTO risk_scores(edge_id,source_id,hazard,'
                    'original_value,normalised_value,coverage_fraction,'
                    'rule_version) VALUES(%s,%s,%s,%s,%s,%s,%s)', risks)
            if start % 30000 == 0:
                print('Import progress', region, start,
                      len(data['edges']), flush=True)

        if locations:
            c.executemany(
                'INSERT INTO locations(region_id,osm_id,name,kind,latitude,'
                'longitude,source_id) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                [(region, l['osm_id'], l['name'], l['kind'], l['lat'], l['lon'],
                  'osm_' + region) for l in locations])

        for f in hazards['features']:
            prop = f['properties']
            original = prop.get('original_value',
                                prop.get('collapse_rank', prop.get('name')))
            c.execute(
                'INSERT INTO hazard_zones(region_id,hazard,original_value,'
                'normalised_value,geometry_json,source_id) '
                'VALUES(%s,%s,%s,%s,%s,%s)',
                (region, prop['layer'], str(original)[:100],
                 prop.get('score'), json.dumps(f),
                 prop.get('source', source)))

        if region == 'tokyo':
            raw = BASE_DIR / 'data/raw/tokyo/hinan_20220301.csv'
            if raw.exists():
                s = raw.read_bytes().decode('cp932')
                rows2 = list(csv.reader(s.splitlines()))
                names = {r[4].strip() for r in rows2[1:]
                         if len(r) > 4 and r[4].strip()}

                def norm(t):
                    return (unicodedata.normalize('NFKC', t)
                            .replace('墨田区立', '')
                            .replace('区立', '').strip())
                names = {norm(n) for n in names}
                seen = set()
                for l in locations:
                    name = norm(l['local_name'])
                    if name in names and name not in seen and l['kind'] == 'school':
                        seen.add(name)
                        c.execute(
                            'INSERT INTO shelters(region_id,name,kind,latitude,'
                            'longitude,hazard,verified_designation,source_id,'
                            'notes) VALUES(%s,%s,%s,%s,%s,%s,TRUE,%s,%s)',
                            (region, l['local_name'],
                             'Historical designated shelter',
                             l['lat'], l['lon'], 'earthquake',
                             'sumida_shelters',
                             'Exact school-name match to Sumida 2022 shelter '
                             'column; coordinate from OSM. Entrance, opening '
                             'and capacity unverified. Not fire evacuation '
                             'designation.'))

        events = {
            'kochi': [('Kerala floods 2018', '2018-08-16',
                       'Historical context; no fabricated loss or depth totals.',
                       'ksdma_flood')],
            'kathmandu': [('Gorkha earthquake', '2015-04-25',
                           'USGS historical shaking model; not a future forecast.',
                           'usgs_gorkha')],
            'tokyo': [('Tohoku earthquake liquefaction', '2011-03-11',
                       'TMG mapped historical footprint; not a current forecast.',
                       'tmg_ground')]}
        for name, date, note, src in events[region]:
            c.execute(
                'INSERT INTO hazard_history(region_id,name,event_date,'
                'description,source_id) VALUES(%s,%s,%s,%s,%s)',
                (region, name, date, note, src))
        c.close()

    invalidate(region)
    print('IMPORTED', region, len(data['edges']), 'edges', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--region', choices=REGIONS, required=True)
    import_region(p.parse_args().region)
