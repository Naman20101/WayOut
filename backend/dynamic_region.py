"""On-demand region preparation for any location on Earth.

Downloads a small OSM extract, the containing SRTM tile and the global
JRC flood raster around a user-supplied point. Landslide is optional and
requires a one-time manual download from NASA SEDAC.

Registers the result in MySQL under a deterministic synthetic region_id.

Jurisdiction-specific datasets (KSDMA flood, USGS ShakeMap, TMG risk) are
not available for arbitrary locations. Custom regions use only global
sources: NASA SRTM terrain and JRC flood depth (plus landslide if present).
"""
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

from backend.config import BASE_DIR, REGIONS, earthdata_token


CUSTOM_RADIUS_M = 3000
_jobs = {}
_lock = threading.Lock()


def region_id_for(lat, lon):
    key = f'{round(lat, 4)},{round(lon, 4)}'
    return 'custom_' + hashlib.sha1(key.encode()).hexdigest()[:10]


def _db_region_exists(region_id):
    try:
        from backend.db import query
        return bool(query('SELECT id FROM regions WHERE id=%s LIMIT 1',
                          (region_id,)))
    except Exception:
        return False


def get_job(region_id):
    with _lock:
        job = dict(_jobs.get(region_id) or {})
    if not job and _db_region_exists(region_id):
        job = {'state': 'ready', 'progress': 100,
               'message': 'Already prepared', 'region_id': region_id}
    if job:
        job['region_id'] = region_id
    return job


def start_job(lat, lon):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid coordinates.')
    region_id = region_id_for(lat, lon)
    with _lock:
        existing = _jobs.get(region_id)
    if existing and existing.get('state') in ('queued', 'running'):
        return region_id, get_job(region_id)
    if _db_region_exists(region_id) and not existing:
        _set(region_id, state='ready', progress=100, message='Already prepared',
             lat=lat, lon=lon, error=None, started_at=None)
        return region_id, get_job(region_id)
    _set(region_id, state='queued', progress=0, message='Queued',
         lat=lat, lon=lon, error=None, started_at=None)
    t = threading.Thread(target=_run, args=(region_id, lat, lon), daemon=True)
    t.start()
    return region_id, get_job(region_id)


def _set(region_id, **kw):
    with _lock:
        _jobs.setdefault(region_id, {}).update(kw)


def _run(region_id, lat, lon):
    _set(region_id, state='running', progress=5, message='Fetching roads…',
         started_at=datetime.now(timezone.utc).isoformat())
    try:
        _register_config(region_id, lat, lon)
        _fetch_osm(region_id, lat, lon)
        _set(region_id, progress=30, message='Fetching SRTM tile…')
        _fetch_srtm(region_id, lat, lon)
        _set(region_id, progress=45, message='Fetching global flood raster…')
        _fetch_flood_cache()
        _set(region_id, progress=60, message='Processing road graph…')
        _preprocess(region_id)
        _set(region_id, progress=80, message='Importing road network…')
        _import(region_id, lat, lon)
        _set(region_id, progress=92, message='Fetching shelter candidates…')
        try:
            from backend.shelters_global import import_for_region
            import_for_region(region_id, lat, lon, CUSTOM_RADIUS_M)
        except Exception as exc:
            print(f'[dynamic] shelter fetch failed: {exc}', flush=True)
        _set(region_id, state='ready', progress=100, message='Ready')
    except Exception as exc:
        _set(region_id, state='failed', message='Failed',
             error=str(exc)[:400])


def _register_config(region_id, lat, lon):
    REGIONS[region_id] = {
        'name': f'Custom ({lat:.3f}, {lon:.3f})',
        'short': 'Custom',
        'country': '',
        'lat': lat, 'lon': lon,
        'hazard': 'flood',
        'subtitle': 'User-selected area',
        'epsg': _utm_epsg(lat, lon),
        'srtm_tiles': [],
        'radius_m': CUSTOM_RADIUS_M,
    }


def _utm_epsg(lat, lon):
    zone = int((lon + 180) / 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _raw_dir(region_id):
    d = BASE_DIR / 'data/raw' / region_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fetch_osm(region_id, lat, lon):
    target = _raw_dir(region_id) / 'osm.json'
    if target.exists():
        return
    query = (f'[out:json][timeout:180];'
             f'(way["highway"](around:{CUSTOM_RADIUS_M},{lat},{lon});'
             f'nwr["amenity"~"hospital|clinic|fire_station|police|school|shelter"]'
             f'(around:{CUSTOM_RADIUS_M},{lat},{lon});'
             f'node["place"](around:{CUSTOM_RADIUS_M},{lat},{lon}););'
             f'out body center;>;out skel qt;')
    last_error = None
    for endpoint in ['https://overpass-api.de/api/interpreter',
                     'https://overpass.kumi.systems/api/interpreter']:
        try:
            r = requests.post(endpoint, data={'data': query},
                              headers={'User-Agent': 'WAYOUT-Educational-Research/1.0'},
                              timeout=(30, 180))
            r.raise_for_status()
            obj = r.json()
            if 'elements' not in obj:
                raise RuntimeError('Overpass returned no elements.')
            target.write_text(json.dumps(obj), encoding='utf8')
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f'Both Overpass endpoints failed: {last_error}')


def _fetch_srtm(region_id, lat, lon):
    from backend.scripts.srtm import tile_name, filename, url_for
    tile = tile_name(int(lat // 1), int(lon // 1))
    target = _raw_dir(region_id) / 'srtm' / filename(tile)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    token = earthdata_token()
    if not token:
        raise RuntimeError('EARTHDATA_TOKEN is not set. Add it to .env.')
    headers = {'Authorization': f'Bearer {token}',
               'User-Agent': 'WAYOUT-Educational-Research/1.0'}
    r = requests.get(url_for(tile), headers=headers, timeout=(30, 300), stream=True)
    r.raise_for_status()
    with target.open('wb') as f:
        for chunk in r.iter_content(1024 * 1024):
            f.write(chunk)
    target.with_suffix(target.suffix + '.metadata.json').write_text(
        json.dumps({'url': url_for(tile), 'tile': tile,
                    'downloaded_at': datetime.now(timezone.utc).isoformat()},
                   indent=2), encoding='utf8')


def _fetch_flood_cache():
    """Ensure the JRC flood raster is cached. Idempotent."""
    try:
        from backend.hazards import _open_flood
        ds = _open_flood(50)
        ds.close()
    except Exception as exc:
        print(f'[dynamic] flood raster unavailable: {exc}', flush=True)


def _preprocess(region_id):
    import backend.scripts.preprocess_data as pp
    pp.process(region_id)


def _import(region_id, lat, lon):
    from backend.db import connection
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO regions(id,name,latitude,longitude,radius_m,primary_hazard) '
            'VALUES(%s,%s,%s,%s,%s,%s) '
            'ON DUPLICATE KEY UPDATE name=VALUES(name), '
            'latitude=VALUES(latitude), longitude=VALUES(longitude)',
            (region_id, f'Custom ({lat:.3f}, {lon:.3f})', lat, lon,
             CUSTOM_RADIUS_M, 'flood'))
        cur.close()
    import backend.scripts.import_mysql as im
    im.import_region(region_id)