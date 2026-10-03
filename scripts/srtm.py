"""NASA SRTMGL1 v003 tile helper.

1 arc-second global elevation distributed by NASA LP DAAC / USGS EROS.
Each tile is a 3601x3601 int16 big-endian .hgt inside a .zip, named by
the lower-left integer degree corner (e.g. N10E076 covers 10..11 N, 76..77 E).

Void value is -32768. Vertical datum is EGM96 (geoid); we do not correct
to ellipsoidal height because slope and relative low-lying indicators are
insensitive to a smooth geoid offset at this scale.

Authentication: NASA Earthdata bearer token via EARTHDATA_TOKEN.
"""
import io, math, zipfile
import numpy as np

EARTHDATA_BASE = ('https://e4ftl01.cr.usgs.gov/MEASURES/'
                  'SRTMGL1.003/2000.02.11')


def tile_name(lat_int, lon_int):
    ns = 'N' if lat_int >= 0 else 'S'
    ew = 'E' if lon_int >= 0 else 'W'
    return f'{ns}{abs(lat_int):02d}{ew}{abs(lon_int):03d}'


def filename(tile):
    return f'{tile}.SRTMGL1.hgt.zip'


def url_for(tile):
    return f'{EARTHDATA_BASE}/{filename(tile)}'


def tiles_for(lat, lon, radius_m=15000):
    """Return the sorted 1x1 degree tile names intersecting a geodesic circle."""
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(lat)))
    s = int(math.floor(lat - dlat))
    n = int(math.floor(lat + dlat))
    w = int(math.floor(lon - dlon))
    e = int(math.floor(lon + dlon))
    return sorted({tile_name(la, lo) for la in range(s, n + 1)
                                     for lo in range(w, e + 1)})


def read_hgt_zip(zip_bytes):
    """Return a float32 elevation grid (void -> NaN) from an SRTMGL1 .hgt.zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith('.hgt'))
        raw = z.read(name)
    side = int(math.isqrt(len(raw) // 2))
    if side * side * 2 != len(raw):
        raise ValueError(f'Unexpected HGT byte length: {len(raw)}')
    data = np.frombuffer(raw, dtype='>i2').reshape(side, side).astype('float32')
    data[data == -32768] = np.nan
    return data


def slope_grid(elev, tile):
    """Per-cell slope in degrees from an elevation grid (30 m nominal cell)."""
    lat_i = int(tile[1:3]) * (1 if tile[0] == 'N' else -1)
    lat_c = lat_i + 0.5
    dy = 30.0
    dx = 30.0 * math.cos(math.radians(lat_c))
    gy, gx = np.gradient(elev)
    slope = np.degrees(np.arctan(np.sqrt((gy / dy) ** 2 + (gx / dx) ** 2)))
    return slope.astype('float32')


def lookup(grids, lat, lon):
    """Nearest-cell sample from a tile grid dict."""
    lat_i = int(math.floor(lat))
    lon_i = int(math.floor(lon))
    grid = grids.get(tile_name(lat_i, lon_i))
    if grid is None:
        return None
    side = grid.shape[0]
    r = int(round((lat_i + 1 - lat) * (side - 1)))
    c = int(round((lon - lon_i) * (side - 1)))
    if not (0 <= r < side and 0 <= c < side):
        return None
    v = float(grid[r, c])
    return v if math.isfinite(v) else None


def load_region_tiles(raw_dir):
    """Load every .SRTMGL1.hgt.zip under raw_dir. Returns (elev, slope) dicts."""
    elev, slope = {}, {}
    for z in sorted(raw_dir.glob('*.SRTMGL1.hgt.zip')):
        tile = z.name.split('.')[0]
        grid = read_hgt_zip(z.read_bytes())
        elev[tile] = grid
        slope[tile] = slope_grid(grid, tile)
    return elev, slope
