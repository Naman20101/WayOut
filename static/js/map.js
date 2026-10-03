/* All map coordinates and comparisons come from the imported sources/API. */
const $ = id => document.getElementById(id), W = WAYOUT;
const map = L.map('map', { zoomControl: false });
W.tile(map);
L.control.zoom({ position: 'bottomright' }).addTo(map);

let region, boundary, picking = 'origin', selectedWay = null, requestVersion = 0;
const points = {}, routes = L.featureGroup().addTo(map),
      facilities = L.layerGroup().addTo(map),
      roads = L.geoJSON(null, {
        style: { color: '#668578', weight: 3 },
        onEachFeature: (f, l) => l.on('click',
          () => selectRoad(f.properties.way, f.properties.name))
      }),
      hazardLayers = [];
const status = t => $('planner-status').textContent = t;

function selectRoad(id, name) {
  selectedWay = id;
  $('selected-road').textContent = `${name || 'Unnamed road'} \u00b7 OSM ${id}`;
  $('apply-condition').disabled = false;
  $('simulation-controls').open = true;
}

function point(which, p) {
  $(which).value = p.map(v => Number(v).toFixed(6)).join(', ');
  if (points[which]) map.removeLayer(points[which]);
  points[which] = L.marker(p, {
    icon: L.divIcon({
      className: 'wayout-pin',
      html: which === 'origin' ? 'A' : 'B',
      iconSize: [28, 28], iconAnchor: [14, 14]
    })
  }).addTo(map).bindPopup(
    which === 'origin' ? 'Starting point' : 'SIMULATION destination');
}

function parse(which) {
  return $(which).value.split(',').map(Number);
}

map.on('click', e => {
  if (picking === 'destination' &&
      $('destination-type').value !== 'simulation') return;
  point(picking, [e.latlng.lat, e.latlng.lng]);
  status(`${picking === 'origin' ? 'Starting point' : 'Simulation destination'} selected.`);
});

for (const k of ['origin', 'destination']) {
  $('pick-' + k).onclick = () => {
    picking = k;
    status('Click the map to choose ' + k + '.');
  };
  $(k).onchange = () => {
    const p = parse(k);
    if (p.length === 2 && p.every(Number.isFinite)) point(k, p);
  };
}

$('destination-type').onchange = () => {
  $('custom-destination').hidden = $('destination-type').value !== 'simulation';
  $('shelter').hidden = $('destination-type').value === 'simulation';
};

async function conditions() {
  const rows = await W.api('/api/simulations?region=' + region);
  $('conditions').innerHTML = rows.map(r =>
    `<div class="condition-row">OSM ${r.osm_way_id}: SIMULATION ${W.escape(r.condition_name)}</div>`
  ).join('');
}

async function roadRefresh() {
  if (!$('road-layer').checked) return;
  const b = map.getBounds();
  const d = await W.api(
    `/api/roads?region=${region}&bounds=${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`);
  roads.clearLayers().addData(d);
  if (d.truncated)
    status('Road display capped at 6,000 segments. Zoom in to inspect roads. Routing uses the complete graph.');
}

map.on('moveend', () => roadRefresh().catch(e => status(e.message)));
$('road-layer').onchange = () => {
  if ($('road-layer').checked) {
    roads.addTo(map);
    roadRefresh().catch(e => status(e.message));
  } else map.removeLayer(roads);
};
$('facility-layer').onchange = () => {
  $('facility-layer').checked ? facilities.addTo(map) : map.removeLayer(facilities);
};

async function changeRegion() {
  const version = ++requestVersion;
  region = $('region').value;
  const c = WAYOUT_REGIONS[region];
  $('hazard').value = c.hazard;
  $('hazard').disabled = true;
  $('map-title').textContent = c.name;
  map.setView([c.lat, c.lon], 12);
  if (boundary) map.removeLayer(boundary);
  boundary = L.circle([c.lat, c.lon], {
    radius: 15000, color: '#16352f', weight: 1, dashArray: '6 8', fill: false
  }).addTo(map);
  routes.clearLayers();
  facilities.clearLayers();
  roads.clearLayers();
  hazardLayers.splice(0).forEach(l => map.removeLayer(l));
  $('layers').replaceChildren();
  $('results').hidden = true;
  for (const k of Object.keys(points)) {
    map.removeLayer(points[k]);
    delete points[k];
    $(k).value = '';
  }
  selectedWay = null;
  $('apply-condition').disabled = true;
  status('Loading source layers\u2026');
  try {
    const [dest, data] = await Promise.all([
      W.api('/api/shelters?region=' + region),
      W.api('/api/mapdata?region=' + region)
    ]);
    if (version !== requestVersion) return;
    $('shelter').innerHTML = '<option value="">Choose a designated destination</option>' +
      dest.map(s => `<option value="${s.id}">${W.escape(s.name)}</option>`).join('');
    if (!dest.length)
      $('shelter').innerHTML = '<option value="">No verified designation imported</option>';
    dest.forEach(s => L.circleMarker([s.latitude, s.longitude], {
      radius: 6, color: '#16352f', fillColor: '#d6c7a1', fillOpacity: 1
    }).bindPopup(`<b>${W.escape(s.name)}</b>${W.escape(s.operational_status)}<br>${W.escape(s.notes)}`)
      .addTo(facilities));

    const extra = [];
    data.features.filter(f => f.properties.layer === 'collapse').forEach(f => {
      for (const [layer, score] of [
        ['fire', Number(f.properties.fire_rank) * 20],
        ['accessibility', Math.min(100, Number(f.properties.accessibility) * 100)]
      ]) extra.push({ ...f, properties: { ...f.properties, layer, score } });
    });
    data.features.push(...extra);

    const groups = {};
    data.features.forEach(f => {
      const key = f.properties.hazard || f.properties.layer || 'Source evidence';
      (groups[key] ??= []).push(f);
    });
    Object.entries(groups).forEach(([key, features], i) => {
      const l = L.geoJSON(features, {
        style: f => ({
          color: W.colour(f.properties.score ?? f.properties.normalised_value),
          weight: 1, fillOpacity: .3
        }),
        pointToLayer: (f, p) => L.circleMarker(p, { radius: 3, color: '#7b715c' }),
        onEachFeature: (f, l) => l.bindPopup(
          Object.entries(f.properties).map(([k, v]) =>
            `${W.escape(k)}: ${W.escape(v)}`).join('<br>'))
      });
      hazardLayers.push(l);
      const label = document.createElement('label');
      label.className = 'checkbox';
      const check = document.createElement('input');
      check.type = 'checkbox';
      check.checked = i === 0;
      if (check.checked) l.addTo(map);
      check.onchange = () => check.checked ? l.addTo(map) : map.removeLayer(l);
      label.append(check, document.createTextNode(key.replaceAll('_', ' ')));
      $('layers').append(label);
    });

    status(dest.length
      ? 'Historical designations only; current opening and access are unverified.'
      : 'No source-backed destination imported here. Use explicitly labelled SIMULATION mode to explore routes.');
    await conditions();
  } catch (e) {
    status(e.message);
  }
}
$('region').onchange = changeRegion;

function card(label, r, cls = '') {
  const terrain = (r.terrain_index != null && r.terrain_index > 0)
    ? `<p>NASA SRTM terrain +${r.terrain_index}</p>` : '';
  return `<div class="compare-card ${cls}">
    <div class="type">${label}</div>
    <strong>${W.km(r.distance_m)} <small>km</small></strong>
    <p>Model index ${r.risk_index}/100</p>
    <p>Observed index ${r.source_index ?? 'unknown'}</p>
    <p>Source coverage ${(r.coverage * 100).toFixed(0)}%</p>${terrain}</div>`;
}

async function calculate() {
  const routeVersion = requestVersion;
  const button = $('calculate');
  button.disabled = true;
  status('Searching the road graph\u2026 First use of a region can take a minute.');
  $('results').hidden = true;
  routes.clearLayers();
  try {
    const simulated = $('destination-type').value === 'simulation';
    const d = await W.api('/api/route', {
      method: 'POST',
      body: JSON.stringify({
        region,
        origin: parse('origin'),
        destination: parse('destination'),
        shelter_id: simulated ? null : Number($('shelter').value),
        simulation_destination: simulated,
        mode: $('mode').value,
        hazard: $('hazard').value
      })
    });
    if (routeVersion !== requestVersion) return;
    L.polyline(d.shortest.coordinates.map(p => [p[1], p[0]]),
      { color: '#a48e60', weight: 7, opacity: .8 }).addTo(routes);
    L.polyline(d.recommended.coordinates.map(p => [p[1], p[0]]),
      { color: '#16352f', weight: 4 }).addTo(routes);
    const endpoints = d.input_points || [
      parse('origin'), simulated ? parse('destination') : d.snapped_points[1]
    ];
    d.snapped_points.forEach((p, i) =>
      L.polyline([endpoints[i], p],
        { color: '#555', weight: 2, dashArray: '4 6' }).addTo(routes));
    map.fitBounds(routes.getBounds(), { padding: [50, 60] });
    $('results').innerHTML =
      `<button class="result-close" aria-label="Close results">\u00d7</button>
      ${d.simulated ? '<span class="badge">SIMULATION</span>' : ''}
      <h2>Your route comparison</h2>
      <p class="fine-print">Lowest-risk route under the stated model and available data. Not a guarantee of safety.</p>
      <div class="compare-grid">
        ${card('SHORTEST \u00b7 SAND', d.shortest)}
        ${card('RISK-ADJUSTED \u00b7 GREEN', d.recommended, 'recommended')}
      </div>
      <ul class="result-list">${[...d.reasons, ...d.limitations]
        .map(r => `<li>${W.escape(r)}</li>`).join('')}</ul>
      <p class="fine-print">Snap distances: ${d.snap_distances_m.join(' m / ')} m. Indices are not probabilities. Follow official emergency instructions.</p>
      <a class="text-link" href="/route/${d.id}">Open route analysis \u2197</a>
      <details><summary>Select a route road for simulation</summary>
      ${d.recommended.ways.map(w =>
        `<button class="road-choice" data-way="${w.id}">${W.escape(w.name || 'Unnamed road')} \u00b7 ${w.id}</button>`
      ).join('')}</details>`;
    $('results').hidden = false;
    $('results').querySelector('.result-close').onclick = () => $('results').hidden = true;
    $('results').querySelectorAll('[data-way]').forEach(
      b => b.onclick = () => selectRoad(Number(b.dataset.way), b.textContent));
    status('Comparison complete. Review data coverage and access limitations.');
  } catch (e) {
    status(e.message);
  } finally {
    button.disabled = false;
  }
}
$('calculate').onclick = calculate;

$('demo').onclick = async () => {
  try {
    const d = await W.api('/api/demo?region=' + region);
    $('destination-type').value = 'simulation';
    $('destination-type').onchange();
    $('mode').value = 'walking';
    point('origin', d.origin);
    point('destination', d.destination);
    await calculate();
  } catch (e) { status(e.message); }
};

$('apply-condition').onclick = async () => {
  try {
    await W.api('/api/simulations', {
      method: 'POST',
      body: JSON.stringify({
        region, way_id: selectedWay, condition: $('condition').value
      })
    });
    await conditions();
    await calculate();
  } catch (e) { status(e.message); }
};

$('reset-conditions').onclick = async () => {
  try {
    await W.api('/api/simulations?region=' + region, { method: 'DELETE' });
    await conditions();
    status('Simulated conditions cleared. Recompare your route.');
  } catch (e) { status(e.message); }
};

$('locate').onclick = () => navigator.geolocation
  ? navigator.geolocation.getCurrentPosition(
      p => {
        point('origin', [p.coords.latitude, p.coords.longitude]);
        map.panTo(points.origin.getLatLng());
        status('Location selected; the server will verify study-area coverage.');
      },
      () => status('Location permission was unavailable. Search or click the map.'))
  : status('Geolocation is unavailable.');

let timer, searchVersion = 0;
$('search').oninput = () => {
  clearTimeout(timer);
  const version = ++searchVersion;
  timer = setTimeout(async () => {
    try {
      const rows = await W.api(
        `/api/locations?region=${region}&q=${encodeURIComponent($('search').value)}`);
      if (version !== searchVersion) return;
      $('suggestions').replaceChildren();
      rows.forEach(r => {
        const b = document.createElement('button');
        b.className = 'suggestion';
        b.textContent = `${r.name} \u00b7 ${r.kind}`;
        b.onclick = () => {
          point('origin', [r.latitude, r.longitude]);
          map.setView([r.latitude, r.longitude], 15);
          $('suggestions').replaceChildren();
        };
        $('suggestions').append(b);
      });
    } catch (e) { status(e.message); }
  }, 250);
};

const initial = new URLSearchParams(location.search).get('region');
if (WAYOUT_REGIONS[initial]) $('region').value = initial;
changeRegion();
