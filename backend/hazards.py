"""Global hazard rasters for custom regions.

Two sources that work today:

  flood    — JRC Global River Flood Hazard Maps, 100 m, 50-year return period.
             Public download, no registration.
  landslide — NASA SEDAC Global Landslide Hazard Distribution, 4.6 km.
             Requires free registration to obtain the GeoTIFF. If the file
             is not present in data/hazards/landslide/, the module prints a
             clear instruction and skips.

Each hazard is sampled at the same 40 m spacing as SRTM and written to the
risk_scores table with the region's edges.
"""
import io
import math
import zipfile
from pathlib import Path

import numpy as np
import requests
import rasterio
from rasterio.mask import mask
from rasterio.features import shapes
from shapely.geometry import shape, mapping

from backend.config import BASE_DIR


HAZARD_CACHE = BASE_DIR / 'data' / 'hazards'

FLOOD_URLS = {
    10: 'https://cidportal.jrc.ec.europa.eu/ftp/jrc-opendata/FLOODS/GlobalMaps/floodMapGL_rp10y.zip',
    50: 'https://cidportal.jrc.ec.europa.eu/ftp/jrc-opendata/FLOODS/GlobalMaps/floodMapGL_rp50y.zip',
    100: 'https://cidportal.jrc.ec.europa.eu/ftp/jrc-opendata/FLOODS/GlobalMaps/floodMapGL_rp100y.zip',
}

LANDSLIDE_LOCAL = HAZARD_CACHE / 'landslide' / 'global_landslide_hazard.tif'


def _ensure_dir(p):
    p.mkdir(parents=True, exist_ok=True)
    return p


def _download(url, target, timeout=(30, 600)):
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers={'User-Agent': 'WAYOUT-Educational-Research/1.0'},
                     timeout=timeout, stream=True)
    r.raise_for_status()
    tmp = target.with_suffix(target.suffix + '.part')
    with tmp.open('wb') as f:
        for chunk in r.iter_content(1024 * 1024):
            f.write(chunk)
    tmp.rename(target)
    return target


def _open_flood(return_period=50):
    """Return an open rasterio dataset for the global flood map."""
    _ensure_dir(HAZARD_CACHE / 'flood')
    target = HAZARD_CACHE / 'flood' / f'floodMapGL_rp{return_period}y.zip'
    _download(FLOOD_URLS[return_period], target)
    with zipfile.ZipFile(target) as z:
        inner = next(n for n in z.namelist() if n.lower().endswith('.tif'))
        data = z.read(inner)
    return rasterio.open(io.BytesIO(data))


def _open_landslide():
    """Return an open rasterio dataset for the global landslide map, or None."""
    if not LANDSLIDE_LOCAL.exists():
        print('[hazards] landslide raster not found at '
              f'{LANDSLIDE_LOCAL}.', flush=True)
        print('[hazards] Download from https://sedac.ciesin.columbia.edu/data/'
              'set/ndh-landslide-hazard-distribution '
              '(free registration) and place the .tif there.', flush=True)
        return None
    return rasterio.open(LANDSLIDE_LOCAL)


def sample_flood(boundary_geojson, lat, lon, return_period=50):
    """Sample flood depth in metres along a WGS84 point list.

    Returns a callable matching the SRTM sampler signature:
    (coords) -> {'flood': [values or None, ...]}
    """
    ds = _open_flood(return_period)
    try:
        clipped, affine = mask(ds, [boundary_geojson], crop=True, filled=False)
    except Exception as exc:
        print(f'[hazards] flood clip failed: {exc}', flush=True)
        ds.close()
        return None
    band = clipped[0]
    valid = ~np.ma.getmaskarray(band)
    ds.close()

    def sampler(coords):
        vals = []
        for x, y in coords:
            try:
                col, row = ~affine * (x, y)
                row, col = int(math.floor(row)), int(math.floor(col))
            except Exception:
                vals.append(None)
                continue
            if (0 <= row < band.shape[0] and 0 <= col < band.shape[1]
                    and valid[row, col]):
                v = float(band[row, col])
                vals.append(v if math.isfinite(v) else None)
            else:
                vals.append(None)
        return {'flood': vals}
    return sampler


def sample_landslide(boundary_geojson, lat, lon):
    """Sample landslide hazard class (1-10) along a WGS84 point list."""
    ds = _open_landslide()
    if ds is None:
        return None
    try:
        clipped, affine = mask(ds, [boundary_geojson], crop=True, filled=False)
    except Exception as exc:
        print(f'[hazards] landslide clip failed: {exc}', flush=True)
        ds.close()
        return None
    band = clipped[0]
    valid = ~np.ma.getmaskarray(band)
    ds.close()

    def sampler(coords):
        vals = []
        for x, y in coords:
            try:
                col, row = ~affine * (x, y)
                row, col = int(math.floor(row)), int(math.floor(col))
            except Exception:
                vals.append(None)
                continue
            if (0 <= row < band.shape[0] and 0 <= col < band.shape[1]
                    and valid[row, col]):
                v = float(band[row, col])
                vals.append(v if math.isfinite(v) else None)
            else:
                vals.append(None)
        return {'landslide': vals}
    return sampler


def build_sampler(boundary_geojson, lat, lon, hazards=('flood', 'landslide')):
    """Compose one sampler covering the requested global hazards."""
    subs = []
    if 'flood' in hazards:
        s = sample_flood(boundary_geojson, lat, lon)
        if s:
            subs.append(s)
    if 'landslide' in hazards:
        s = sample_landslide(boundary_geojson, lat, lon)
        if s:
            subs.append(s)
    if not subs:
        return None
    if len(subs) == 1:
        return subs[0]

    def combined(coords):
        out = {}
        for s in subs:
            out.update(s(coords))
        return out
    return combined


def flood_score(depth_m):
    """Global flood depth in metres -> 0..100 planning index.

    0    below 0.05 m  (no mapped depth)
    100  at 3.0 m or deeper

    This is a relative planning index, not a probability or a
    calibrated risk of casualty. Depth classes follow the JRC map's
    own encoding; values above 3 m are clamped.
    """
    if depth_m is None:
        return None
    d = float(depth_m)
    if d <= 0.05:
        return 0.0
    if d >= 3.0:
        return 100.0
    return round((d - 0.05) / 2.95 * 100.0, 1)


def landslide_score(hazard_class):
    """NASA SEDAC landslide hazard class (1..10) -> 0..100 planning index."""
    if hazard_class is None:
        return None
    c = float(hazard_class)
    if c <= 0:
        return 0.0
    if c >= 10:
        return 100.0
    return round(c * 10.0, 1)