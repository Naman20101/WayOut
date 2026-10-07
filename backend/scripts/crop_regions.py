"""WGS84 geodesic circles, not buffers measured in degrees."""
from pyproj import Geod
from shapely.geometry import Polygon
GEOD=Geod(ellps='WGS84')
def circle(lat,lon,radius=15000):
    return Polygon([GEOD.fwd(lon,lat,a,radius)[:2] for a in range(360)])
def distance(a,b):
    return GEOD.inv(a[0],a[1],b[0],b[1])[2]
