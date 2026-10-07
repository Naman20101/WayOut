"""Global hazard detection for any coordinate on Earth.

Three keyless free sources:

  ThinkHazard!  — World Bank / GFDRR. Baseline hazard assessment per
                  administrative division. 11 hazards including river
                  flood, urban flood, landslide, earthquake, cyclone,
                  tsunami, volcano, wildfire, water scarcity, heat.
  GDACS         — UN / EU live disaster alerts from the last N days.
  NASA EONET    — Satellite-observed natural events.

Honest default: when ThinkHazard! does not return usable data for a
location, the baseline list is left empty. We do NOT substitute a
latitude-based guess — that produced wrong answers like "river flood
in Dubai" and is worse than showing nothing.

Endpoints exposed through Flask:
  /api/hazards_here?lat=&lon=   → baseline + live events near a point
  /api/global_alerts?days=14    → recent GDACS events worldwide
"""
import json
import math
from datetime import datetime, timedelta, timezone

import requests

from backend.config import BASE_DIR

CACHE_DIR = BASE_DIR / 'data' / 'cache' / 'hazards'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

GDACS_SEARCH = 'https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH'
EONET_EVENTS = 'https://eonet.gsfc.nasa.gov/api/v3/events'


def _cache_path(key):
    safe = ''.join(c if c.isalnum() or c in '-_.' else '_' for c in key)
    return CACHE_DIR / f'{safe}.json'


def _read_cache(path, max_age_hours=24):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf8'))
        ts = data.get('_cached_at')
        if not ts:
            return None
        age = datetime.now(timezone.utc) - datetime.fromisoformat(ts)
        if age > timedelta(hours=max_age_hours):
            return None
        return data.get('payload')
    except Exception:
        return None


def _write_cache(path, payload):
    try:
        path.write_text(json.dumps({
            '_cached_at': datetime.now(timezone.utc).isoformat(),
            'payload': payload,
        }, indent=2), encoding='utf8')
    except Exception:
        pass


def thinkhazard_assessment(lat, lon):
    """Baseline hazard classification via ThinkHazard! JSON API.

    ThinkHazard!'s public report URLs are keyed by administrative
    division, not raw coordinates. We attempt the coordinate-based
    JSON endpoint; if ThinkHazard! does not recognise the location
    (offshore, small islands, some desert regions), we return None
    and the caller shows no baseline. That is the honest outcome.
    """
    cache = _cache_path(f'th_{lat:.3f}_{lon:.3f}')
    cached = _read_cache(cache, max_age_hours=24 * 30)
    if cached is not None:
        return cached

    url = f'https://thinkhazard.org/en/report?lat={lat}&lon={lon}&format=json'
    try:
        r = requests.get(url, timeout=20,
                         headers={'User-Agent': 'WAYOUT-Educational/1.0',
                                  'Accept': 'application/json'},
                         allow_redirects=True)
        if r.status_code != 200:
            return None
        payload = r.json()
        _write_cache(cache, payload)
        return payload
    except Exception as exc:
        print(f'[hazards] thinkhazard failed: {exc}', flush=True)
        return None


def gdacs_recent(lat, lon, radius_deg=8.0, days_back=30):
    """Live disaster alerts from GDACS within a box around the point."""
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')
    to_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    url = (f'{GDACS_SEARCH}?eventlist=EQ;FL;TC;VO;WF;DR'
           f'&fromdate={from_date}&todate={to_date}')
    cache = _cache_path(f'gdacs_{from_date}')
    cached = _read_cache(cache, max_age_hours=6)
    if cached is not None:
        events = cached
    else:
        try:
            r = requests.get(url, timeout=20,
                             headers={'User-Agent': 'WAYOUT-Educational/1.0',
                                      'Accept': 'application/json'})
            if r.status_code != 200:
                return []
            events = r.json().get('features', [])
            _write_cache(cache, events)
        except Exception as exc:
            print(f'[hazards] gdacs failed: {exc}', flush=True)
            return []

    out = []
    for ev in events:
        coords = (ev.get('geometry') or {}).get('coordinates')
        if not coords:
            continue
        try:
            if isinstance(coords[0], (int, float)):
                elon, elat = coords[0], coords[1]
            else:
                ring = coords[0]
                elon = sum(p[0] for p in ring) / len(ring)
                elat = sum(p[1] for p in ring) / len(ring)
        except Exception:
            continue
        d = math.hypot(elat - lat, elon - lon)
        if d > radius_deg:
            continue
        props = ev.get('properties') or {}
        out.append({
            'source': 'GDACS',
            'event_type': props.get('eventtype'),
            'name': props.get('eventname') or props.get('name'),
            'alert_level': props.get('alertlevel'),
            'event_date': props.get('fromdate') or props.get('todate'),
            'distance_deg': round(d, 3),
            'latitude': elat,
            'longitude': elon,
        })
    return out


def eonet_recent(lat, lon, radius_deg=8.0, days_back=30):
    """NASA EONET natural events near a point."""
    cache = _cache_path(f'eonet_{days_back}')
    cached = _read_cache(cache, max_age_hours=12)
    if cached is not None:
        events = cached
    else:
        try:
            r = requests.get(EONET_EVENTS,
                             params={'status': 'open', 'days': days_back,
                                     'limit': 500},
                             timeout=20,
                             headers={'User-Agent': 'WAYOUT-Educational/1.0',
                                      'Accept': 'application/json'})
            if r.status_code != 200:
                return []
            events = r.json().get('events', [])
            _write_cache(cache, events)
        except Exception as exc:
            print(f'[hazards] eonet failed: {exc}', flush=True)
            return []

    out = []
    for ev in events:
        for geom in ev.get('geometry', []):
            coords = geom.get('coordinates')
            if not coords or not isinstance(coords[0], (int, float)):
                continue
            elon, elat = coords[0], coords[1]
            d = math.hypot(elat - lat, elon - lon)
            if d > radius_deg:
                continue
            cats = ev.get('categories') or []
            out.append({
                'source': 'NASA EONET',
                'event_type': cats[0].get('title') if cats else 'natural event',
                'name': ev.get('title'),
                'alert_level': None,
                'event_date': geom.get('date'),
                'distance_deg': round(d, 3),
                'latitude': elat,
                'longitude': elon,
            })
            break
    return out


def location_hazard_profile(lat, lon):
    """Combined profile for one coordinate.

    baseline is empty when ThinkHazard! has no data for this location.
    The frontend shows "no baseline assessment available" in that case.
    live_events comes from GDACS + EONET and is always a real list.
    """
    th = thinkhazard_assessment(lat, lon)
    live = gdacs_recent(lat, lon) + eonet_recent(lat, lon)

    baseline = []
    if th:
        for item in (th.get('hazards') or []):
            baseline.append({
                'hazard': item.get('hazard_type') or item.get('hazard'),
                'rating': item.get('hazard_level') or item.get('level'),
            })
        if not baseline:
            for key, val in th.items():
                if isinstance(val, dict) and 'hazard' in val:
                    baseline.append({
                        'hazard': val.get('hazard'),
                        'rating': val.get('hazard_level') or val.get('level'),
                    })

    return {
        'location': {'lat': lat, 'lon': lon},
        'baseline': baseline,
        'live_events': live,
        'baseline_available': bool(baseline),
    }


def gdacs_global_recent(days_back=14, limit=30):
    """Recent GDACS events worldwide, no location filter.

    Used by the landing page and the map's live-alert ticker to show
    what's happening right now, anywhere on Earth.

    Returns a list of dicts with: id, event_type, name, alert_level,
    country, event_date, latitude, longitude. Sorted by alert level
    (red > orange > green) then most recent first.
    """
    from_date = (datetime.now(timezone.utc) -
                 timedelta(days=days_back)).strftime('%Y-%m-%d')
    to_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    url = (f'{GDACS_SEARCH}?eventlist=EQ;FL;TC;VO;WF;DR'
           f'&fromdate={from_date}&todate={to_date}')
    cache = _cache_path(f'gdacs_global_{from_date}')
    cached = _read_cache(cache, max_age_hours=3)
    if cached is not None:
        events = cached
    else:
        try:
            r = requests.get(url, timeout=20,
                             headers={'User-Agent': 'WAYOUT-Educational/1.0',
                                      'Accept': 'application/json'})
            if r.status_code != 200:
                return []
            events = r.json().get('features', [])
            _write_cache(cache, events)
        except Exception as exc:
            print(f'[hazards] gdacs_global failed: {exc}', flush=True)
            return []

    out = []
    for ev in events:
        props = ev.get('properties') or {}
        coords = (ev.get('geometry') or {}).get('coordinates')
        elat = elon = None
        if coords:
            if isinstance(coords[0], (int, float)):
                elon, elat = coords[0], coords[1]
            else:
                try:
                    ring = coords[0]
                    elon = sum(p[0] for p in ring) / len(ring)
                    elat = sum(p[1] for p in ring) / len(ring)
                except Exception:
                    elat = elon = None

        out.append({
            'id': ev.get('id') or props.get('eventid'),
            'event_type': props.get('eventtype'),
            'name': props.get('eventname') or props.get('name') or 'Event',
            'alert_level': (props.get('alertlevel') or 'green').lower(),
            'country': props.get('country'),
            'event_date': (props.get('fromdate') or
                           props.get('todate') or '')[:10],
            'latitude': elat,
            'longitude': elon,
        })

    # Sort: red > orange > green, then most recent first
    level_rank = {'red': 0, 'orange': 1, 'green': 2}
    out.sort(key=lambda e: (
        level_rank.get(e['alert_level'], 3),
        e['event_date'] or '0000-00-00',
    ), reverse=False)
    # Reverse date within level: sort again by date descending
    out.sort(key=lambda e: (
        level_rank.get(e['alert_level'], 3),
    ))
    # Within each level, newest first
    grouped = {}
    for e in out:
        grouped.setdefault(e['alert_level'], []).append(e)
    for lvl in grouped:
        grouped[lvl].sort(key=lambda e: e['event_date'] or '',
                          reverse=True)
    ordered = []
    for lvl in ('red', 'orange', 'green'):
        ordered.extend(grouped.get(lvl, []))

    return ordered[:limit]