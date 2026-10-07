"""Fetch OSM shelter candidates worldwide.

OSM has amenity=shelter, emergency=shelter, social_facility=shelter tags
globally. Coverage varies by country. These are candidates, not verified
emergency destinations — that designation is jurisdiction-specific and
cannot be inferred from a map tag.

Every row inserted by this module carries verified_designation=FALSE and
a note explaining the source.
"""
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

from backend.config import BASE_DIR


OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]

QUERY_TEMPLATE = '''[out:json][timeout:90];
(
  nwr["amenity"="shelter"](around:{r},{lat},{lon});
  nwr["emergency"="shelter"](around:{r},{lat},{lon});
  nwr["social_facility"="shelter"](around:{r},{lat},{lon});
  nwr["shelter_type"](around:{r},{lat},{lon});
);
out body center;'''


def _raw_dir(region_id):
    d = BASE_DIR / 'data/raw' / region_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _kind(tags):
    if not tags:
        return 'shelter'
    if tags.get('emergency') == 'shelter':
        return 'emergency shelter (OSM)'
    if tags.get('amenity') == 'shelter':
        return 'public shelter (OSM)'
    if tags.get('social_facility') == 'shelter':
        return 'social shelter (OSM)'
    if tags.get('shelter_type'):
        return f"{tags['shelter_type']} (OSM)"
    return 'shelter (OSM)'


def fetch(region_id, lat, lon, radius_m=3000, cache=True):
    """Return list of candidate shelter dicts. Caches the raw JSON response."""
    cache_path = _raw_dir(region_id) / 'shelters_osm.json'
    if cache and cache_path.exists():
        try:
            obj = json.loads(cache_path.read_text(encoding='utf8'))
        except Exception:
            obj = None
    else:
        obj = None

    if obj is None:
        query = QUERY_TEMPLATE.format(r=radius_m, lat=lat, lon=lon)
        last_error = None
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                r = requests.post(
                    endpoint,
                    data={'data': query},
                    headers={'User-Agent': 'WAYOUT-Educational-Research/1.0'},
                    timeout=(30, 120),
                )
                r.raise_for_status()
                data = r.json()
                if 'elements' not in data:
                    raise RuntimeError('Overpass returned no elements.')
                cache_path.write_text(
                    json.dumps({
                        'query': query,
                        'fetched_at': datetime.now(timezone.utc).isoformat(),
                        'elements': data['elements'],
                    }, indent=2),
                    encoding='utf8')
                obj = {'elements': data['elements']}
                break
            except Exception as exc:
                last_error = exc
        if obj is None:
            raise RuntimeError(f'Both Overpass endpoints failed: {last_error}')

    shelters = []
    for el in obj.get('elements', []):
        tags = el.get('tags') or {}
        name = tags.get('name:en') or tags.get('name') or tags.get('operator')
        if not name:
            continue
        center = el.get('center') or el
        if 'lat' not in center or 'lon' not in center:
            continue
        capacity = None
        raw_cap = tags.get('capacity')
        if raw_cap:
            try:
                capacity = int(str(raw_cap).split(';')[0].strip())
            except (ValueError, TypeError):
                capacity = None
        accessibility = '; '.join(
            f'{k}={v}' for k, v in tags.items()
            if k in ('wheelchair', 'access', 'entrance', 'toilets', 'opening_hours')
        ) or None
        shelters.append({
            'osm_id': el.get('id'),
            'name': name[:250],
            'kind': _kind(tags),
            'latitude': float(center['lat']),
            'longitude': float(center['lon']),
            'capacity': capacity,
            'accessibility': accessibility,
            'notes': (
                'OSM candidate — not an official emergency designation. '
                'Entrance, opening hours and current capacity have not been '
                'verified against any municipal or national register.'
            ),
        })
    return shelters


def import_for_region(region_id, lat, lon, radius_m=3000):
    """Fetch candidates and insert them into the MySQL shelters table."""
    from backend.db import connection
    candidates = fetch(region_id, lat, lon, radius_m=radius_m)
    if not candidates:
        return 0
    with connection() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM shelters WHERE region_id=%s '
                    'AND source_id=%s', (region_id, 'osm_shelter'))
        cur.execute(
            'INSERT IGNORE INTO data_sources('
            'id,region_id,dataset_name,organisation,url,accessed_at,'
            'observation_year,coverage,variables_used,format,licence,'
            'official,status,preprocessing,sha256) VALUES('
            '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            ('osm_shelter', region_id,
             'OSM shelter candidates', 'OpenStreetMap contributors',
             'https://wiki.openstreetmap.org/wiki/Key:amenity',
             '2026-10-03', 'Live snapshot',
             f'{radius_m/1000:.1f} km around {lat:.3f},{lon:.3f}',
             'name, amenity, emergency, shelter_type, capacity, access',
             'OSM JSON', 'ODbL 1.0', False,
             'Fetched from Overpass; candidates only',
             'Filter and normalise shelter tags',
             None))
        for s in candidates:
            cur.execute(
                'INSERT INTO shelters(region_id,name,kind,latitude,longitude,'
                'hazard,verified_designation,capacity,accessibility,'
                'operational_status,source_id,notes) VALUES('
                '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (region_id, s['name'], s['kind'], s['latitude'], s['longitude'],
                 'all', False, s['capacity'], s['accessibility'],
                 'Current opening not verified', 'osm_shelter', s['notes']))
        cur.close()
    return len(candidates)