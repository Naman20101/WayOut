"""Choose real connected walking endpoints using the terrain-aware model.

Falls back to pure connectivity only if SRTM is absent. The fallback is
recorded in the demo note so no reader assumes terrain was used.
"""
import sys, json
from pathlib import Path
from collections import deque
from pyproj import Geod
from backend.config import BASE_DIR, REGIONS
from backend.routing.graph_builder import load_graph, adjacency
from backend.routing.dijkstra import shortest_path

GEOD = Geod(ellps='WGS84')


def _slope_by_node(edges):
    by = {}
    for e in edges:
        if not e['walk']:
            continue
        r = e['risks'].get('slope')
        s = (float(r['normalised_value'])
             if r and r['normalised_value'] is not None else None)
        if s is None:
            continue
        for n in (e['from_node'], e['to_node']):
            by.setdefault(n, []).append(s)
    return by


def _largest_component(graph):
    """Scan every seed and return the largest connected node set."""
    seen = set()
    best = set()
    for seed in graph:
        if seed in seen:
            continue
        comp = set()
        q = deque([seed])
        while q:
            u = q.popleft()
            if u in comp:
                continue
            comp.add(u)
            for v, _ in graph.get(u, []):
                if v not in comp:
                    q.append(v)
        seen.update(comp)
        if len(comp) > len(best):
            best = comp
    return best


def prepare(region):
    nodes, edges = load_graph(region)
    g = adjacency(edges, 'walking')
    if not g:
        raise RuntimeError('Walking graph is empty')
    cfg = REGIONS[region]

    def geodesic(n):
        return GEOD.inv(cfg['lon'], cfg['lat'], nodes[n][0], nodes[n][1])[2]

    component = _largest_component(g)
    print(f'[demo] {region}: {len(g)} walking source nodes, '
          f'largest component = {len(component)}', flush=True)
    if len(component) < 50:
        raise RuntimeError(
            f'Largest walking component is only {len(component)} nodes. '
            f'The OSM walking graph may be fragmented; verify the extract '
            f'covers connected streets.')

    slope_by_node = _slope_by_node(edges)

    def walk_score(n):
        vals = slope_by_node.get(n)
        if not vals:
            return 50.0
        return sum(vals) / len(vals)

    local = [n for n in component if geodesic(n) <= 600] or list(component)
    origin = min(local, key=lambda n: (walk_score(n), geodesic(n)))

    def km(n):
        return geodesic(n) / 1000.0

    cand = [n for n in component
            if 1.0 <= km(n) <= 1.8 and n != origin] or list(component)
    dest = min(cand, key=walk_score)

    shortest_path(g, origin, dest, lambda e: e['distance_m'])

    p = BASE_DIR / 'data/processed' / region / 'demo.json'
    srtm_used = bool(slope_by_node)
    note = ('Actual OSM junctions selected from the largest walking component. '
            + ('Endpoints chosen for low NASA SRTM slope.' if srtm_used
               else 'SRTM not available; endpoints chosen by connectivity only. ')
            + 'SIMULATION destination, not a verified shelter.')
    p.write_text(json.dumps({
        'origin': list(reversed(nodes[origin])),
        'destination': list(reversed(nodes[dest])),
        'note': note,
        'srtm_used': srtm_used,
    }, indent=2), encoding='utf8')
    print(region, 'demo ready; srtm_used =', srtm_used, flush=True)


if __name__ == '__main__':
    prepare(sys.argv[1])
