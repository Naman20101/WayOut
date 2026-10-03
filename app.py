"""WAYOUT: local Flask / MySQL educational geospatial decision support."""
import json, os, secrets
from flask import Flask, render_template, request, jsonify, session
import mysql.connector
from config import BASE_DIR, REGIONS, DISCLAIMER
from db import query, execute
from routing.risk_router import compare, validate_point


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=32000,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax')
    if test_config:
        app.config.update(test_config)

    @app.before_request
    def security():
        if 'sid' not in session:
            session['sid'] = secrets.token_urlsafe(24)
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(24)
        if request.method in ('POST', 'DELETE', 'PUT') and \
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
                'csrf': session.get('csrf'), 'page': request.path}

    @app.get('/')
    def home():
        return render_template('index.html')

    @app.get('/map')
    def planner():
        return render_template('map.html')

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

    @app.errorhandler(mysql.connector.Error)
    def db_error(error):
        app.logger.error('Database unavailable (%s)',
                         getattr(error, 'errno', 'unknown'))
        if request.path.startswith('/api/'):
            return jsonify(error='MySQL is unavailable or credentials are '
                                 'incorrect. Start the local database and check '
                                 '.env; no fallback data has been substituted.'), 503
        return render_template('error.html'), 503

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    def region_param():
        r = request.args.get('region', 'kochi')
        if r not in REGIONS:
            raise ValueError('Unknown study region.')
        return r

    @app.get('/api/status')
    def status():
        query('SELECT 1 AS ok')
        return jsonify(database='MySQL connected', regions=REGIONS,
                       csrf=session['csrf'])

    @app.get('/api/regions')
    def regions_api():
        return jsonify({
            'default': next(iter(REGIONS)),
            'order': list(REGIONS.keys()),
            'regions': {k: {
                'name': v['name'], 'short': v['short'],
                'country': v['country'], 'lat': v['lat'], 'lon': v['lon'],
                'hazard': v['hazard'], 'subtitle': v['subtitle'],
                'radius_m': 15000,
            } for k, v in REGIONS.items()},
        })

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
        totals['high_risk_zones'] = query(
            'SELECT COUNT(*) AS n FROM hazard_zones WHERE region_id=%s '
            'AND normalised_value>60', (r,))[0]['n']
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
        cfg = REGIONS[r]
        bounds = request.args.get('bounds')
        if bounds:
            try:
                w, s, e, n = map(float, bounds.split(','))
            except Exception:
                raise ValueError('Invalid map bounds.')
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise ValueError('Invalid map bounds.')
        else:
            w, s, e, n = (cfg['lon'] - .04, cfg['lat'] - .04,
                          cfg['lon'] + .04, cfg['lat'] + .04)
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
        if r not in REGIONS or condition not in (
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

    @app.post('/api/route')
    def route():
        d = request.get_json(silent=True) or {}
        r = d.get('region')
        dest = d.get('destination')
        simulated = False
        if r not in REGIONS:
            raise ValueError('Unknown region.')
        shelter_id = d.get('shelter_id')
        if shelter_id is not None:
            sh = query('SELECT * FROM shelters WHERE id=%s AND region_id=%s '
                       'AND verified_designation=TRUE AND hazard=%s',
                       (shelter_id, r, d.get('hazard')))
            if not sh:
                raise ValueError('No eligible designated destination is available.')
            dest = [sh[0]['latitude'], sh[0]['longitude']]
            dest_name = sh[0]['name']
        else:
            if d.get('simulation_destination') is not True:
                raise ValueError('A custom point requires explicit SIMULATION '
                                 'destination mode. It is not a verified shelter.')
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
            raise ValueError('Demo is not prepared yet. Choose two map points.')
        return jsonify(json.loads(p.read_text(encoding='utf8')))

    return app


app = create_app()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5000')),
            debug=False, threaded=True)
