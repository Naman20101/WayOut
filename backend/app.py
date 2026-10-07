"""WAYOUT: global disaster navigation with offline LLM assistance."""
import json, math, os, secrets
from functools import wraps
from pathlib import Path
from flask import (Flask, render_template, request, jsonify, session,
                   redirect, url_for, Response)
import mysql.connector
from pyproj import Geod

from backend.config import BASE_DIR, REGIONS, DISCLAIMER
from backend.db import query, execute
from backend.routing.risk_router import compare, validate_point
import backend.auth as auth

GEOD = Geod(ellps='WGS84')


def create_app(test_config=None):
    _frontend = Path(__file__).resolve().parent.parent / 'frontend'
    app = Flask(__name__,
                template_folder=str(_frontend / 'templates'),
                static_folder=str(_frontend / 'static'),
                static_url_path='/static')
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=500000,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax')
    if test_config:
        app.config.update(test_config)

    auth.init_db()

    # Warm up the LLM in a background thread so the first chat is fast.
    try:
        import threading
        from backend.llm_helper import warmup
        threading.Thread(target=warmup, daemon=True).start()
    except Exception:
        pass

    # ---------------- helpers ----------------
    def _is_custom(rid):
        return isinstance(rid, str) and rid.startswith('custom_')

    def _valid_region(rid):
        return rid in REGIONS or _is_custom(rid)

    def current_user():
        uid = session.get('user_id')
        if not uid:
            return None
        return auth.get_user(uid)

    def login_required(view):
        @wraps(view)
        def wrapper(*a, **kw):
            if not session.get('user_id'):
                if request.path.startswith('/api/'):
                    return jsonify(error='Sign in required.'), 401
                return redirect(url_for('login', next=request.path))
            return view(*a, **kw)
        return wrapper

    def _maybe_float(v):
        try:
            return float(v) if v not in (None, '') else None
        except (TypeError, ValueError):
            return None

    def region_param():
        r = request.args.get('region', 'kochi')
        if not _valid_region(r):
            raise ValueError('Unknown study region.')
        return r

    # ---------------- request lifecycle ----------------
    @app.before_request
    def security():
        if 'sid' not in session:
            session['sid'] = secrets.token_urlsafe(24)
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(24)
        if request.method in ('POST', 'DELETE', 'PUT') and \
           request.path.startswith('/api/') and \
           request.path != '/api/llm/stream' and \
           not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''),
                                      session['csrf']):
            return jsonify(error='This form expired. Refresh the page and try again.'), 403

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def context():
        return {'regions': REGIONS, 'disclaimer': DISCLAIMER,
                'csrf': session.get('csrf'), 'page': request.path,
                'current_user': current_user()}

    # ---------------- error handlers ----------------
    @app.errorhandler(mysql.connector.Error)
    def db_error(error):
        app.logger.error('Database unavailable (%s)',
                         getattr(error, 'errno', 'unknown'))
        if request.path.startswith('/api/'):
            return jsonify(error='MySQL is unavailable. Check .env and start '
                                 'the local database.'), 503
        return render_template('error.html'), 503

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(Exception)
    def any_error(error):
        if isinstance(error, mysql.connector.Error):
            raise error
        app.logger.exception('Unhandled error on %s', request.path)
        if request.path.startswith('/api/'):
            return jsonify(error=f'{type(error).__name__}: {error}'), 500
        return render_template('error.html'), 500

    # ---------------- pages ----------------
    @app.get('/')
    def home():
        return render_template('index.html')

    @app.get('/map')
    def planner():
        return render_template('map3d.html')

    @app.get('/map2d')
    def planner_2d():
        return render_template('map.html')

    @app.get('/map3d')
    def planner_3d():
        return redirect('/map')

    @app.get('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    @app.get('/methodology')
    def methodology():
        return render_template('methodology.html')

    @app.get('/data')
    def sources():
        return render_template('data_sources.html')

    @app.get('/shelters')
    def shelters_page():
        return render_template('shelters.html')

    @app.get('/historical')
    def historical():
        return render_template('historical.html')

    @app.get('/admin')
    def admin():
        return render_template('admin.html')

    @app.get('/about')
    def about():
        return render_template('methodology.html')

    @app.get('/route/<int:route_id>')
    def analysis(route_id):
        rows = query('SELECT result_summary FROM route_history '
                     'WHERE id=%s AND session_id=%s',
                     (route_id, session['sid']))
        if not rows:
            return render_template('route_analysis.html', result=None), 404
        result = rows[0]['result_summary']
        result = json.loads(result) if isinstance(result, str) else result
        return render_template('route_analysis.html', result=result)

    # ---------------- auth ----------------
    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'GET':
            if session.get('user_id'):
                return redirect('/')
            return render_template('signup.html')
        d = request.form or request.get_json(silent=True) or {}
        try:
            uid = auth.create_user(
                d.get('username'), d.get('password'),
                d.get('display_name'),
                _maybe_float(d.get('home_lat')),
                _maybe_float(d.get('home_lon')),
                d.get('home_label'))
        except ValueError as e:
            if request.is_json:
                return jsonify(error=str(e)), 400
            return render_template('signup.html', error=str(e)), 400
        session['user_id'] = uid
        if request.is_json:
            return jsonify(ok=True, user_id=uid)
        return redirect('/')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'GET':
            if session.get('user_id'):
                return redirect('/')
            return render_template('login.html', next=request.args.get('next', '/'))
        d = request.form or request.get_json(silent=True) or {}
        user = auth.verify_user(d.get('username'), d.get('password'))
        if not user:
            if request.is_json:
                return jsonify(error='Incorrect username or password.'), 401
            return render_template('login.html',
                                   error='Incorrect username or password.',
                                   next=d.get('next', '/')), 401
        session['user_id'] = user['id']
        target = d.get('next') or '/'
        if request.is_json:
            return jsonify(ok=True, user=user)
        return redirect(target)

    @app.post('/logout')
    def logout():
        session.pop('user_id', None)
        if request.is_json:
            return jsonify(ok=True)
        return redirect('/')

    # ---------------- user endpoints ----------------
    @app.get('/api/me')
    def api_me():
        u = current_user()
        if not u:
            return jsonify(signed_in=False)
        return jsonify(
            signed_in=True,
            user={'id': u['id'], 'username': u['username'],
                  'display_name': u['display_name'],
                  'home_lat': u['home_lat'], 'home_lon': u['home_lon'],
                  'home_label': u['home_label']},
            saved=auth.list_saved_locations(u['id']))

    @app.post('/api/me/home')
    @login_required
    def api_set_home():
        d = request.get_json(silent=True) or {}
        lat = _maybe_float(d.get('lat'))
        lon = _maybe_float(d.get('lon'))
        if lat is None or lon is None:
            raise ValueError('Provide lat and lon.')
        label = (d.get('label') or '')[:200]
        auth.update_home(session['user_id'], lat, lon, label)
        return jsonify(ok=True)

    @app.post('/api/me/saved')
    @login_required
    def api_add_saved():
        d = request.get_json(silent=True) or {}
        lat = _maybe_float(d.get('lat'))
        lon = _maybe_float(d.get('lon'))
        label = (d.get('label') or '').strip()[:200]
        if lat is None or lon is None or not label:
            raise ValueError('Provide label, lat and lon.')
        auth.add_saved_location(session['user_id'], label, lat, lon)
        return jsonify(ok=True)

    @app.delete('/api/me/saved/<int:loc_id>')
    @login_required
    def api_del_saved(loc_id):
        auth.delete_saved_location(session['user_id'], loc_id)
        return jsonify(ok=True)

    # ---------------- core data ----------------
    @app.get('/api/status')
    def status():
        query('SELECT 1 AS ok')
        return jsonify(database='MySQL connected', regions=REGIONS,
                       csrf=session['csrf'],
                       user=current_user())

    @app.get('/api/regions')
    def regions_api():
        return jsonify({
            'default': next(iter(REGIONS)),
            'order': list(REGIONS.keys()),
            'regions': {k: {
                'name': v['name'], 'short': v['short'],
                'country': v['country'], 'lat': v['lat'], 'lon': v['lon'],
                'hazard': v['hazard'], 'subtitle': v['subtitle'],
                'radius_m': v.get('radius_m', 15000),
            } for k, v in REGIONS.items()},
        })

    @app.get('/api/hazards_here')
    def hazards_here():
        from backend.global_hazards import location_hazard_profile
        try:
            lat = float(request.args.get('lat'))
            lon = float(request.args.get('lon'))
        except (TypeError, ValueError):
            raise ValueError('Provide lat and lon as numbers.')
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Coordinates out of range.')
        return jsonify(location_hazard_profile(lat, lon))

    @app.get('/api/global_alerts')
    def global_alerts():
        from backend.global_hazards import gdacs_global_recent
        try:
            days = min(30, max(1, int(request.args.get('days', '14'))))
        except ValueError:
            days = 14
        events = gdacs_global_recent(days_back=days, limit=30)
        return jsonify({'count': len(events), 'events': events})

    @app.get('/api/safe_nearby')
    def safe_nearby():
        r = region_param()
        try:
            lat = float(request.args.get('lat'))
            lon = float(request.args.get('lon'))
        except (TypeError, ValueError):
            raise ValueError('Provide lat and lon as numbers.')
        try:
            limit = min(20, max(1, int(request.args.get('limit', '8'))))
        except ValueError:
            limit = 8
        rows = query(
            'SELECT sh.id,sh.name,sh.kind,sh.latitude,sh.longitude,sh.hazard,'
            'sh.verified_designation,sh.capacity,sh.accessibility,'
            'sh.operational_status,sh.notes,sh.source_id,'
            's.url,s.organisation '
            'FROM shelters sh '
            'LEFT JOIN data_sources s ON s.id=sh.source_id '
            'WHERE sh.region_id=%s', (r,))
        ranked = []
        for row in rows:
            d = GEOD.inv(lon, lat, row['longitude'], row['latitude'])[2]
            ranked.append({
                'id': row['id'], 'name': row['name'], 'kind': row['kind'],
                'latitude': row['latitude'], 'longitude': row['longitude'],
                'distance_m': round(d, 1),
                'verified': bool(row['verified_designation']),
                'capacity': row['capacity'],
                'accessibility': row['accessibility'],
                'operational_status': row['operational_status'],
                'notes': row['notes'], 'organisation': row['organisation'],
                'url': row['url'], 'source_id': row['source_id'],
            })
        ranked.sort(key=lambda x: (0 if x['verified'] else 1, x['distance_m']))
        return jsonify({'region': r, 'count': len(ranked),
                        'spots': ranked[:limit]})

    @app.get('/api/route_to_nearest')
    def route_to_nearest():
        from backend.routing.risk_router import compare as compare_routes
        r = region_param()
        try:
            lat = float(request.args.get('lat'))
            lon = float(request.args.get('lon'))
        except (TypeError, ValueError):
            raise ValueError('Provide lat and lon as numbers.')
        mode = request.args.get('mode', 'walking')
        hazard = request.args.get('hazard',
                                  REGIONS[r]['hazard'] if r in REGIONS else 'flood')
        rows = query(
            'SELECT id,name,latitude,longitude,verified_designation,'
            'operational_status,source_id '
            'FROM shelters WHERE region_id=%s', (r,))
        if not rows:
            raise ValueError('No source-backed destinations in this region yet.')
        def dist(s):
            dlat = (s['latitude'] - lat) * 111320
            dlon = (s['longitude'] - lon) * 111320 * math.cos(math.radians(lat))
            return math.hypot(dlat, dlon)
        rows.sort(key=lambda s: (0 if s['verified_designation'] else 1, dist(s)))
        target = rows[0]
        conditions = {x['osm_way_id']: x['condition_name'] for x in query(
            'SELECT osm_way_id,condition_name FROM admin_simulations '
            'WHERE session_id=%s AND region_id=%s', (session['sid'], r))}
        result = compare_routes(r, [lat, lon],
                                [target['latitude'], target['longitude']],
                                mode, hazard, conditions)
        result['destination'] = {
            'id': target['id'], 'name': target['name'],
            'verified': bool(target['verified_designation']),
            'operational_status': target['operational_status'],
            'source_id': target['source_id'],
        }
        result['simulated'] = result.get('simulated', False)
        result['destination_name'] = target['name']
        return jsonify(result)

    # ---------------- LLM ----------------
    @app.get('/api/llm/status')
    def llm_status():
        from backend.llm_helper import is_available, list_models, MODEL
        return jsonify(available=is_available(),
                       configured_model=MODEL,
                       installed_models=list_models())

    @app.post('/api/llm/ask')
    def llm_ask():
        from backend.llm_helper import ask
        d = request.get_json(silent=True) or {}
        q = (d.get('question') or '').strip()
        if not q:
            raise ValueError('Ask a question.')
        if len(q) > 500:
            q = q[:500]
        return jsonify(ask(q, context=d.get('context') or {}))

    @app.post('/api/llm/stream')
    def llm_stream():
        from backend.llm_helper import stream
        d = request.get_json(silent=True) or {}
        q = (d.get('question') or '').strip()
        if not q:
            raise ValueError('Ask a question.')
        if len(q) > 500:
            q = q[:500]
        ctx = d.get('context') or {}

        def generate():
            try:
                for chunk in stream(q, context=ctx):
                    payload = json.dumps({'chunk': chunk})
                    yield f'data: {payload}\n\n'
                yield 'data: {"done": true}\n\n'
            except Exception as exc:
                err = json.dumps({'error': str(exc)})
                yield f'data: {err}\n\n'

        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'X-Accel-Buffering': 'no',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
            }
        )

    # ---------------- stats and registers ----------------
    @app.get('/api/stats')
    def stats():
        r = region_param()
        totals = query('SELECT COUNT(*) AS edges,'
                       'ROUND(SUM(distance_m)/1000,1) AS road_km '
                       'FROM road_edges WHERE region_id=%s', (r,))[0]
        totals['shelters'] = query(
            'SELECT COUNT(*) AS n FROM shelters WHERE region_id=%s '
            'AND verified_designation=TRUE', (r,))[0]['n']
        totals['sources'] = query(
            'SELECT COUNT(*) AS n FROM data_sources WHERE region_id=%s',
            (r,))[0]['n']
        totals['events'] = query(
            'SELECT COUNT(*) AS n FROM hazard_history WHERE region_id=%s',
            (r,))[0]['n']
        totals['distribution'] = query(
            'SELECT FLOOR(normalised_value/20) AS bucket,COUNT(*) AS n '
            'FROM hazard_zones WHERE region_id=%s '
            'AND normalised_value IS NOT NULL GROUP BY bucket ORDER BY bucket',
            (r,))
        totals['recent_routes'] = query(
            'SELECT id,created_at,mode,simulated,shortest_distance_m,'
            'recommended_distance_m,observed_risk,coverage_fraction '
            'FROM route_history WHERE region_id=%s AND session_id=%s '
            'ORDER BY id DESC LIMIT 8', (r, session['sid']))
        totals['average_risk'] = query(
            'SELECT ROUND(AVG(observed_risk),1) AS n FROM route_history '
            'WHERE region_id=%s AND session_id=%s',
            (r, session['sid']))[0]['n']
        return jsonify(totals)

    @app.get('/api/sources')
    def source_data():
        return jsonify(query('SELECT * FROM data_sources '
                             'ORDER BY region_id,dataset_name'))

    @app.get('/api/history')
    def history_data():
        return jsonify(query(
            'SELECT h.*,s.url FROM hazard_history h '
            'JOIN data_sources s ON s.id=h.source_id '
            'WHERE h.region_id=%s ORDER BY event_date', (region_param(),)))

    @app.get('/api/shelters')
    def shelters():
        return jsonify(query(
            'SELECT sh.*,s.url,s.organisation FROM shelters sh '
            'LEFT JOIN data_sources s ON s.id=sh.source_id '
            'WHERE sh.region_id=%s ORDER BY sh.name', (region_param(),)))

    @app.get('/api/locations')
    def locations():
        r = region_param()
        q = request.args.get('q', '')[:80].strip()
        return jsonify(query(
            'SELECT id,name,kind,latitude,longitude FROM locations '
            'WHERE region_id=%s AND name LIKE %s ORDER BY name LIMIT 15',
            (r, '%' + q + '%')))

    @app.get('/api/mapdata')
    def mapdata():
        r = region_param()
        rows = query('SELECT geometry_json FROM hazard_zones WHERE region_id=%s',
                     (r,))
        return jsonify(
            type='FeatureCollection',
            features=[json.loads(x['geometry_json'])
                      if isinstance(x['geometry_json'], str)
                      else x['geometry_json'] for x in rows])

    @app.get('/api/roads')
    def roads():
        r = region_param()
        cfg = REGIONS.get(r)
        default_lat = cfg['lat'] if cfg else 0.0
        default_lon = cfg['lon'] if cfg else 0.0
        bounds = request.args.get('bounds')
        if bounds:
            try:
                w, s, e, n = map(float, bounds.split(','))
            except Exception:
                raise ValueError('Invalid map bounds.')
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise ValueError('Invalid map bounds.')
        else:
            w, s, e, n = (default_lon - .04, default_lat - .04,
                          default_lon + .04, default_lat + .04)
        rows = query(
            'SELECT e.osm_way_id,e.name,e.highway,e.tags FROM road_edges e '
            'JOIN road_nodes n ON n.region_id=e.region_id AND n.id=e.from_node '
            'WHERE e.region_id=%s AND n.longitude BETWEEN %s AND %s '
            'AND n.latitude BETWEEN %s AND %s LIMIT 6000',
            (r, w, e, s, n))
        fs = []
        for row in rows:
            tags = json.loads(row['tags']) if isinstance(row['tags'], str) else row['tags']
            fs.append({'type': 'Feature',
                       'geometry': {'type': 'LineString',
                                    'coordinates': tags['_coords']},
                       'properties': {'way': row['osm_way_id'],
                                      'name': row['name'],
                                      'highway': row['highway']}})
        return jsonify(type='FeatureCollection', features=fs,
                       truncated=len(rows) == 6000)

    # ---------------- simulations ----------------
    @app.get('/api/simulations')
    def simulations():
        return jsonify(query(
            'SELECT id,osm_way_id,condition_name FROM admin_simulations '
            'WHERE session_id=%s AND region_id=%s',
            (session['sid'], region_param())))

    @app.post('/api/simulations')
    def add_simulation():
        d = request.get_json(silent=True) or {}
        r = d.get('region')
        condition = d.get('condition')
        if not _valid_region(r) or condition not in (
                'Blocked', 'Closed', 'Unsafe', 'Flooded', 'Unavailable'):
            raise ValueError('Choose a supported region and simulation condition.')
        way = d.get('way_id')
        if type(way) != int or not query(
                'SELECT id FROM road_edges WHERE region_id=%s '
                'AND osm_way_id=%s LIMIT 1', (r, way)):
            raise ValueError('That road is not in the study graph.')
        execute('INSERT INTO admin_simulations(session_id,region_id,osm_way_id,'
                'condition_name) VALUES(%s,%s,%s,%s) '
                'ON DUPLICATE KEY UPDATE condition_name=VALUES(condition_name)',
                (session['sid'], r, way, condition))
        return jsonify(ok=True)

    @app.delete('/api/simulations')
    def clear_simulations():
        r = region_param()
        execute('DELETE FROM admin_simulations WHERE session_id=%s '
                'AND region_id=%s', (session['sid'], r))
        return jsonify(ok=True)

    # ---------------- routing ----------------
    @app.post('/api/route')
    def route():
        d = request.get_json(silent=True) or {}
        r = d.get('region')
        dest = d.get('destination')
        simulated = False
        if not _valid_region(r):
            raise ValueError('Unknown region.')
        shelter_id = d.get('shelter_id')
        if shelter_id is not None:
            sh = query('SELECT * FROM shelters WHERE id=%s AND region_id=%s',
                       (shelter_id, r))
            if not sh:
                raise ValueError('No eligible designated destination is available.')
            dest = [sh[0]['latitude'], sh[0]['longitude']]
            dest_name = sh[0]['name']
        else:
            if d.get('simulation_destination') is not True:
                raise ValueError('A custom point requires explicit SIMULATION mode.')
            simulated = True
            dest_name = 'SIMULATION destination - user-selected point'
        conditions = {x['osm_way_id']: x['condition_name'] for x in query(
            'SELECT osm_way_id,condition_name FROM admin_simulations '
            'WHERE session_id=%s AND region_id=%s', (session['sid'], r))}
        result = compare(r, d.get('origin'), dest, d.get('mode'),
                         d.get('hazard'), conditions)
        result['simulated'] = result['simulated'] or simulated
        result['destination_name'] = dest_name
        result['id'] = execute(
            'INSERT INTO route_history(session_id,region_id,mode,hazard,'
            'simulated,shortest_distance_m,recommended_distance_m,observed_risk,'
            'coverage_fraction,result_summary) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (session['sid'], r, result['mode'], result['hazard'],
             result['simulated'], result['shortest']['distance_m'],
             result['recommended']['distance_m'],
             result['recommended']['source_index'],
             result['recommended']['coverage'], json.dumps(result)))
        return jsonify(result)

    @app.get('/api/demo')
    def demo():
        r = region_param()
        p = BASE_DIR / 'data/processed' / r / 'demo.json'
        if not p.exists():
            raise ValueError('Demo is not prepared yet.')
        return jsonify(json.loads(p.read_text(encoding='utf8')))

    @app.post('/api/guide')
    def guide_endpoint():
        from backend.assistant import guide
        d = request.get_json(silent=True) or {}
        r = d.get('region')
        if not _valid_region(r):
            raise ValueError('Unknown region.')
        return jsonify(guide(r,
                             bool(d.get('has_origin')),
                             bool(d.get('has_destination')),
                             d.get('origin_text') or '',
                             d.get('destination_text') or ''))

    @app.post('/api/explain')
    def explain_endpoint():
        from backend.assistant import explain, answer
        d = request.get_json(silent=True) or {}
        result = d.get('result')
        question = d.get('question')
        if result is None:
            return jsonify(headline='No route calculated yet.',
                           bullets=[], directions=[],
                           same_route=False, answer=answer(question, None))
        if question:
            return jsonify(answer=answer(question, result))
        return jsonify(**explain(result))

    # ---------------- custom region ----------------
    @app.post('/api/region/prepare')
    def region_prepare():
        from backend.dynamic_region import start_job
        d = request.get_json(silent=True) or {}
        try:
            lat = float(d.get('lat'))
            lon = float(d.get('lon'))
        except (TypeError, ValueError):
            raise ValueError('Provide lat and lon as numbers.')
        rid, job = start_job(lat, lon)
        payload = dict(job) if job else {}
        payload['region_id'] = rid
        return jsonify(payload)

    @app.get('/api/region/status')
    def region_status():
        from backend.dynamic_region import get_job
        rid = request.args.get('region_id', '').strip()
        if not _is_custom(rid):
            raise ValueError('Unknown custom region id.')
        job = get_job(rid)
        if not job:
            return jsonify(region_id=rid, state='unknown', progress=0,
                           message='Not started')
        payload = dict(job)
        payload['region_id'] = rid
        return jsonify(payload)

    @app.get('/api/region/custom/list')
    def region_custom_list():
        rows = query("SELECT id,name,latitude,longitude FROM regions "
                     "WHERE id LIKE 'custom_%' ORDER BY name")
        return jsonify(rows)

    return app


app = create_app()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5000')),
            debug=False, threaded=True)