"""Reproducible, bounded downloads. Raw bytes are never overwritten."""
import argparse, hashlib, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import REGIONS, earthdata_token

SOURCES = {
 'flood': ('kochi','flood_10_25_50.zip',
   'https://sdma.kerala.gov.in/wp-content/uploads/2026/06/1.-Flood-Return-Probability-Historical-10-25-50-years.zip'),
 'flood2': ('kochi','flood_100_200_500.zip',
   'https://sdma.kerala.gov.in/wp-content/uploads/2026/06/2.Flood-Return-Probability-Historical-100-200-500-years.zip'),
 'kochi_reference': ('kochi','Ernakulam_Hist.pdf',
   'https://sdma.kerala.gov.in/wp-content/uploads/2022/05/Ernakulam_Hist.pdf'),
 'iom': ('kathmandu','iom_open_spaces.pdf',
   'https://nepal.iom.int/sites/g/files/tmzbdl1116/files/documents/Update_Report_On_83_Open_Spaces_Identified_for_Humanitarian_Purposes_in_Kathmandu_Valley.pdf'),
 'sumida': ('tokyo','hinan_20220301.csv',
   'https://www.city.sumida.lg.jp/kuseijoho/sumida_info/opendata/opendata_ichiran/bosai_data/hinan_data.files/hinan_20220301.csv'),
 'tokyo_risk': ('tokyo','all2.csv',
   'https://www.toshiseibi.metro.tokyo.lg.jp/bosai/chousa_6/download/all2.csv?2209='),
}

def _auth_headers(url):
    if 'e4ftl01.cr.usgs.gov' in url or 'data.lpdaac.earthdatacloud.nasa.gov' in url:
        token = earthdata_token()
        if not token:
            raise RuntimeError(
                'EARTHDATA_TOKEN is not set. Register at '
                'https://urs.earthdata.nasa.gov/ and add the token to .env. '
                'No substitute elevation source is silently used.')
        return {'Authorization': f'Bearer {token}'}
    return {}

def download(url, path, query=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print('PRESERVED', path.name, flush=True)
        return path
    error = None
    for attempt in range(4):
        try:
            method = requests.post if query else requests.get
            kwargs = {'data': {'data': query}} if query else {}
            headers = {'User-Agent': 'WAYOUT-Educational-Research/1.0'}
            headers.update(_auth_headers(url))
            with method(url, timeout=(30, 240), stream=True,
                        headers=headers, **kwargs) as response:
                response.raise_for_status()
                temp = path.with_suffix(path.suffix + '.part')
                h = hashlib.sha256(); size = 0
                with temp.open('wb') as f:
                    for chunk in response.iter_content(1024 * 1024):
                        f.write(chunk); h.update(chunk); size += len(chunk)
                if query:
                    obj = json.loads(temp.read_text(encoding='utf8'))
                    if 'remark' in obj or 'elements' not in obj:
                        raise ValueError('Incomplete Overpass response: '
                                         + str(obj.get('remark')))
                if path.suffix == '.zip' and temp.read_bytes()[:2] != b'PK':
                    raise ValueError('Expected ZIP, received another format')
                temp.rename(path)
                metadata = {
                    'url': url,
                    'downloaded_at': datetime.now(timezone.utc).isoformat(),
                    'sha256': h.hexdigest(),
                    'bytes': size,
                    'content_type': response.headers.get('Content-Type'),
                    'query': query,
                }
                path.with_suffix(path.suffix + '.metadata.json').write_text(
                    json.dumps(metadata, indent=2), encoding='utf8')
                print('DOWNLOADED', path.name, size, flush=True)
                return path
        except Exception as exc:
            error = exc
            print('RETRY', path.name, attempt + 1, str(exc)[:150], flush=True)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'{url}: {error}')

def osm(region):
    lat, lon = REGIONS[region]['lat'], REGIONS[region]['lon']
    query = (f'[out:json][timeout:180];'
             f'(way["highway"](around:15000,{lat},{lon});'
             f'nwr["amenity"~"hospital|clinic|fire_station|police|school|shelter"]'
             f'(around:15000,{lat},{lon});'
             f'node["place"](around:15000,{lat},{lon}););'
             f'out body center;>;out skel qt;')
    path = ROOT / 'data/raw' / region / 'osm.json'
    for endpoint in ['https://overpass-api.de/api/interpreter',
                     'https://overpass.kumi.systems/api/interpreter']:
        try:
            return download(endpoint, path, query)
        except RuntimeError:
            pass
    raise RuntimeError('Both Overpass endpoints failed; rerun later. '
                       'No substitute data generated.')

def srtm(region):
    from srtm import tiles_for, filename, url_for
    cfg = REGIONS[region]
    tiles = tiles_for(cfg['lat'], cfg['lon'], 15000)
    expected = set(cfg.get('srtm_tiles', []))
    if expected and set(tiles) != expected:
        print(f'[srtm] derived {tiles}; config declared {sorted(expected)}',
              flush=True)
    for tile in tiles:
        path = ROOT / 'data/raw' / region / 'srtm' / filename(tile)
        download(url_for(tile), path)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('dataset', choices=list(SOURCES) + ['osm', 'srtm'])
    p.add_argument('--region', choices=REGIONS, default='kochi')
    a = p.parse_args()
    if a.dataset == 'osm':
        osm(a.region)
    elif a.dataset == 'srtm':
        srtm(a.region)
    else:
        r, name, url = SOURCES[a.dataset]
        download(url, ROOT / 'data/raw' / r / name)
