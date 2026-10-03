"""Small, auditable normalisation functions; missing values stay missing."""
from config import ELEVATION_BANDS

def rank_score(rank):
    if rank is None:
        return None
    if rank not in (1, 2, 3, 4, 5):
        raise ValueError('Expected TMG ordinal rank 1-5')
    return rank * 20.0

def mmi_score(mmi):
    if mmi is None:
        return None
    return max(0, min(100, (float(mmi) - 1) / 9 * 100))

def elevation_score(meters, region='kochi'):
    if meters is None:
        return None
    low, high = ELEVATION_BANDS.get(region, (5.0, 50.0))
    m = float(meters)
    if m <= low:
        return 100.0
    if m >= high:
        return 0.0
    return round((high - m) / (high - low) * 100.0, 1)

def slope_score(degrees):
    if degrees is None:
        return None
    d = float(degrees)
    if d <= 2.0:
        return 0.0
    if d >= 15.0:
        return 100.0
    return round((d - 2.0) / 13.0 * 100.0, 1)
