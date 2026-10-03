"""Load actual MySQL data once per process, with separate adjacency per mode."""
import json
from functools import lru_cache
from db import query

@lru_cache(maxsize=3)
def load_graph(region):
    nodes = {r['id']: (r['longitude'], r['latitude'])
             for r in query('SELECT id,latitude,longitude FROM road_nodes '
                            'WHERE region_id=%s', (region,))}
    edges = query('SELECT * FROM road_edges WHERE region_id=%s', (region,))
    by_id = {e['id']: e for e in edges}
    for e in edges:
        e['tags'] = json.loads(e['tags']) if isinstance(e['tags'], str) else e['tags']
        e['risks'] = {}
    for r in query('SELECT rs.* FROM risk_scores rs '
                   'JOIN road_edges e ON e.id=rs.edge_id '
                   'WHERE e.region_id=%s', (region,)):
        by_id[r['edge_id']]['risks'][r['hazard']] = r
    return nodes, edges

def invalidate(region=None):
    """Drop the cached graph after a re-import. Safe to call from app.py."""
    load_graph.cache_clear()

def adjacency(edges, mode):
    graph = {}
    for e in edges:
        if not e[mode if mode != 'walking' else 'walk']:
            continue
        u, v = e['from_node'], e['to_node']
        one = e['oneway']
        if mode == 'walking' or (mode == 'bicycle' and
                                 e['tags'].get('oneway:bicycle') == 'no'):
            one = 0
        if one != -1:
            graph.setdefault(u, []).append((v, e))
        if one != 1:
            graph.setdefault(v, []).append((u, e))
    return graph
