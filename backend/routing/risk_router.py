"""Compare identical snapped endpoints; disclose coverage and unknown penalties."""
import math
from backend.config import REGIONS
from backend.routing.graph_builder import load_graph, adjacency
from backend.routing.dijkstra import shortest_path
from pyproj import Geod

GEOD = Geod(ellps='WGS84')

# Region-specific primary hazard weights (sum to 1.0 per region).
WEIGHTS = {
    'kochi': {'flood': 1.0},
    'kathmandu': {'shaking': 1.0},
    'tokyo': {'collapse': 0.5, 'fire': 0.3, 'accessibility': 0.2},
}

# Global fallback for custom regions. Uses global rasters only.
# river_flood is JRC depth (metres), landslide is SEDAC class 1..10.
CUSTOM_WEIGHTS = {'river_flood': 0.5, 'landslide': 0.3, 'flood': 0.2}

# NASA SRTM terrain modifiers, additive on top of primary hazard index.
TERRAIN_WEIGHTS = {
    'kochi':     {'elevation': 0.15, 'slope': 0.10},
    'kathmandu': {'slope': 0.15, 'elevation': 0.05},
    'tokyo':     {'slope': 0.10, 'elevation': 0.05},
}
CUSTOM_TERRAIN_WEIGHTS = {'elevation': 0.10, 'slope': 0.10}

HAZARD_MULTIPLIER = {'flood': 8.0, 'earthquake': 5.0}


def weights_for(region):
    return WEIGHTS.get(region, CUSTOM_WEIGHTS)


def terrain_weights_for(region):
    return TERRAIN_WEIGHTS.get(region, CUSTOM_TERRAIN_WEIGHTS)


def is_custom(region):
    return isinstance(region, str) and region.startswith('custom_')


def validate_point(region, p):
    if not isinstance(p, (list, tuple)) or len(p) != 2 or \
       any(isinstance(x, bool) or not isinstance(x, (int, float)) or
           not math.isfinite(x) for x in p):
        raise ValueError('Use finite latitude and longitude coordinates.')
    lat, lon = p
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid latitude or longitude.')
    cfg = REGIONS.get(region)
    if not cfg:
        return  # custom region has no server-side boundary yet
    radius = cfg.get('radius_m', 15000)
    if GEOD.inv(cfg['lon'], cfg['lat'], lon, lat)[2] > radius:
        raise ValueError('This location is outside the supported study area.')


def exposure(edge, region):
    weighted = 0
    coverage = 0
    observed = 0
    for key, w in weights_for(region).items():
        r = edge['risks'].get(key)
        c = float(r['coverage_fraction']) if r else 0
        s = float(r['normalised_value']) if r and r['normalised_value'] is not None else 0
        weighted += w * (c * s + (1 - c) * 100)
        observed += w * c * s
        coverage += w * c
    return weighted, coverage, observed


def terrain_modifier(edge, region):
    extra = 0.0
    cov = 0.0
    for key, w in terrain_weights_for(region).items():
        r = edge['risks'].get(key)
        if r and r.get('normalised_value') is not None and \
           float(r.get('coverage_fraction', 0)) > 0:
            extra += w * float(r['normalised_value'])
            cov += w
    return round(extra, 4), round(cov, 4)


def effective_index(edge, region):
    primary, cov, obs = exposure(edge, region)
    tmod, _ = terrain_modifier(edge, region)
    return min(100.0, primary + tmod), cov, obs


def compare(region, origin, destination, mode, hazard, overrides=None):
    if not (region in REGIONS or is_custom(region)):
        raise ValueError('Unknown region.')
    if mode not in ('walking', 'car', 'bicycle'):
        raise ValueError('Unknown transport mode.')

    # Only enforce hazard identity for the three fixed study regions.
    if region in REGIONS and hazard != REGIONS[region]['hazard']:
        raise ValueError('That disaster mode has no supported data in this region.')
    if is_custom(region) and hazard not in ('flood', 'earthquake'):
        raise ValueError('Choose flood or earthquake for this area.')

    validate_point(region, origin)
    validate_point(region, destination)

    nodes, edges = load_graph(region)
    if not edges:
        raise ValueError('Road data is unavailable. Run the documented import pipeline.')
    graph = adjacency(edges, mode)
    eligible = set(graph)
    eligible.update(v for adj in graph.values() for v, _ in adj)
    if not eligible:
        raise ValueError('No roads are available for this mode.')

    def snap(p):
        lon, lat = p[1], p[0]
        best = min(eligible,
                   key=lambda n: (nodes[n][0] - lon) ** 2 *
                                 math.cos(math.radians(lat)) ** 2 +
                                 (nodes[n][1] - lat) ** 2)
        dist = GEOD.inv(lon, lat, *nodes[best])[2]
        if dist > 400:
            raise ValueError('No accessible graph junction within 400 m.')
        return best, dist
    start, sd = snap(origin)
    end, ed = snap(destination)
    if start == end:
        raise ValueError('Both points snap to the same junction.')
    overrides = overrides or {}

    def weight(e, risk):
        condition = overrides.get(e['osm_way_id'])
        if condition in ('Blocked', 'Closed', 'Flooded', 'Unavailable'):
            return None
        distance = e['distance_m']
        index, _, _ = effective_index(e, region)
        sim_penalty = 20 if condition == 'Unsafe' else 0
        return distance * (1 + (HAZARD_MULTIPLIER[hazard] * index / 100 + sim_penalty
                                if risk else 0))

    shortest, c1 = shortest_path(graph, start, end, lambda e: weight(e, False))
    recommended, c2 = shortest_path(graph, start, end, lambda e: weight(e, True))

    def summary(path, cost):
        length = 0; known = 0; observed = 0; model = 0
        tmod_sum = 0; tmod_cov = 0
        coords = []; ways = []
        for u, v, e in path:
            index, c, o = effective_index(e, region)
            tmod, tc = terrain_modifier(e, region)
            d = e['distance_m']
            length += d; known += c * d; observed += o * d; model += index * d
            tmod_sum += tmod * d; tmod_cov += tc * d
            ec = e['tags']['_coords']
            ec = ec if u == e['from_node'] else list(reversed(ec))
            coords.extend(ec if not coords else ec[1:])
            ways.append({'id': e['osm_way_id'], 'name': e['name'],
                         'length_m': round(d, 1),
                         'condition': overrides.get(e['osm_way_id'])})
        return {
            'distance_m': round(length, 1),
            'risk_index': round(model / length, 1) if length else 0,
            'source_index': round(observed / known, 1) if known else None,
            'coverage': round(known / length, 4) if length else 0,
            'terrain_index': round(tmod_sum / length, 1) if length else 0,
            'terrain_coverage': round(tmod_cov / length, 4) if length else 0,
            'cost': round(cost, 1),
            'coordinates': coords, 'ways': ways}

    a = summary(shortest, c1)
    b = summary(recommended, c2)
    a['risk_adjusted_cost'] = round(sum(weight(e, True)
                                        for _, _, e in shortest), 1)

    reasons = []
    if c2 < a['risk_adjusted_cost'] - 0.05:
        reasons.append(f"The weighted objective decreased from "
                       f"{a['risk_adjusted_cost']:,.0f} to {c2:,.0f} cost units.")
    if b['risk_index'] < a['risk_index'] - .05:
        reasons.append(f"The length-weighted model index is "
                       f"{a['risk_index'] - b['risk_index']:.1f} points lower.")
    if b['terrain_index'] > 0:
        reasons.append(f"NASA SRTM terrain contributed "
                       f"{b['terrain_index']:.1f} points to the recommended index.")
    if abs(b['distance_m'] - a['distance_m']) < .1 and \
       [e['id'] for _, _, e in shortest] == [e['id'] for _, _, e in recommended]:
        reasons.append('Both objectives selected the same path.')
    if overrides:
        reasons.append('Session-only SIMULATION conditions applied to both searches.')
    if b['coverage'] < 1:
        reasons.append(f"Only {b['coverage']:.0%} of the weighted route length "
                       f"has primary source support.")

    return {
        'shortest': a, 'recommended': b, 'reasons': reasons,
        'input_points': [origin, destination],
        'snap_distances_m': [round(sd, 1), round(ed, 1)],
        'snapped_points': [list(reversed(nodes[start])),
                           list(reversed(nodes[end]))],
        'weights': weights_for(region),
        'terrain_weights': terrain_weights_for(region),
        'simulated': bool(overrides),
        'hazard': hazard, 'mode': mode, 'region': region,
        'limitations': [
            'The route begins and ends at graph junctions.',
            'Historical data; no live closures or shelter opening verification.',
            'Turn restrictions, conditional access and structural inspections '
            'are not included.',
            'SRTM elevation is a relative-terrain indicator, not a flood depth.']}