/* All map coordinates and comparisons come from the imported sources/API. */
const $ = id => document.getElementById(id), W = WAYOUT;
const map = L.map('map', {
  zoomControl: false,
  preferCanvas: true,
  zoomAnimation: true,
});
W.tile(map);
L.control.zoom({ position: 'bottomright' }).addTo(map);

let region, boundary, selectedWay = null, requestVersion = 0;
let pendingPick = 'origin';
let lastResult = null;
let is3D = false;

const points = {}, routes = L.featureGroup().addTo(map),
      facilities = L.layerGroup().addTo(map),
      roads = L.geoJSON(null, {
        style: { color: '#668578', weight: 3 },
        onEachFeature: (f, l) => l.on('click',
          () => selectRoad(f.properties.way, f.properties.name))
      }),
      hazardLayers = [];

const status = t => $('planner-status').textContent = t || '';
const assistant = document.getElementById('assistant-body');
const assistantTitle = document.getElementById('assistant-title');

function assistantHtml(title, body) {
  assistantTitle.textContent = title;
  assistant.innerHTML = body;
}

async function refreshGuide() {
  if (lastResult) return;
  const hasA = !!points.origin, hasB = !!points.destination;
  try {
    const d = await W.api('/api/guide', {
      method: 'POST',
      body: JSON.stringify({
        region, has_origin: hasA, has_destination: hasB,
        origin_text: hasA ? $('origin').value : '',
        destination_text: hasB ? $('destination').value : ''
      })
    });
    const s = d.steps[0];
    assistantHtml(s.title,
      `<p>${W.escape(s.body)}</p><p class="fine-print">${W.escape(s.hint)}</p>`);
  } catch (e) {
    assistantHtml('Ready', '<p>Pick a starting point and destination to begin.</p>');
  }
}

function showExplainer(result) {
  assistantTitle.textContent = 'Route explained';
  assistant.innerHTML = `
    <p class="assistant-headline">${W.escape(result.headline)}</p>
    <ul class="assistant-bullets">
      ${result.bullets.map(b => `<li>${W.escape(b)}</li>`).join('')}
    </ul>
    ${result.directions.length ? `
      <details open>
        <summary>Directions (top segments)</summary>
        <ol class="directions">
          ${result.directions.map(w => `
            <li>
              <span class="dir-name">${W.escape(w.name)}</span>
              <span class="dir-len">${(w.length_m/1000).toFixed(2)} km</span>
            </li>`).join('')}
        </ol>
      </details>` : ''}
    <div class="assistant-ask">
      <button data-q="Why is this route safer?">Why safer?</button>
      <button data-q="What does coverage mean?">Coverage</button>
      <button data-q="How does NASA SRTM terrain contribute?">Terrain</button>
      <button data-q="How does flood scoring work?">Flood</button>
      <button data-q="What about landslide?">Landslide</button>
      <button data-q="Are both routes the same?">Same route?</button>
      <button data-q="Is this safe?">Safe?</button>
    </div>
    <div class="assistant-answer" id="assistant-answer" hidden></div>
  `;
  assistant.querySelectorAll('.assistant-ask button').forEach(b => {
    b.onclick = async () => {
      const out = $('assistant-answer');
      out.hidden = false;
      out.textContent = '…';
      try {
        const r = await W.api('/api/explain', {
          method: 'POST',
          body: JSON.stringify({ result, question: b.dataset.q })
        });
        out.textContent = r.answer;
      } catch (e) { out.textContent = 'Could not load answer.'; }
    };
  });
}

function premiumPin(which) {
  const label = which === 'origin' ? 'A' : 'B';
  const variant = which === 'origin' ? 'a' : 'b';
  return L.divIcon({
    className: 'premium-pin premium-pin-' + variant,
    html: `<div class="pin-shadow"></div>
           <div class="pin-head">${label}</div>
           <div class="pin-tail"></div>`,
    iconSize: [40, 56],
    iconAnchor: [20, 52],
    popupAnchor: [0, -50]
  });
}

function point(which, p) {
  $(which).value = p.map(v => Number(v).toFixed(6)).join(', ');
  if (points[which]) map.removeLayer(points[which]);
  points[which] = L.marker(p, { icon: premiumPin(which) })
    .addTo(map)
    .bindPopup(which === 'origin'
      ? '<b>Starting point A</b>'
      : '<b>Destination B</b><br><span style="font-size:11px;color:#718079">SIMULATION point — not a verified shelter</span>');
  pendingPick = which === 'origin'
    ? (points.destination ? null : 'destination')
    : (points.origin ? null : 'origin');
  updatePickHint();
  refreshGuide();
  lastResult = null;
  /* Clear stale error text on successful placement — fixes the
     "outside supported study area" message that lingered from a
     previous click. */
  status('');
  if (points.origin && points.destination) $('calculate').classList.add('ready');
  else $('calculate').classList.remove('ready');
}

function updatePickHint() {
  const banner = $('pick-hint');
  if (!banner) return;
  if (pendingPick && points.origin && !points.destination) {
    banner.textContent = 'Click the map to place B (destination).';
    banner.hidden = false;
  } else if (pendingPick && !points.origin) {
    banner.textContent = 'Click the map to place A (starting point).';
    banner.hidden = false;
  } else if (points.origin && points.destination) {
    banner.textContent = 'Both points set. Press Compare routes.';
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }
}

function parse(which) { return $(which).value.split(',').map(Number); }

map.on('click', e => {
  const which = pendingPick || (!points.origin ? 'origin' : 'destination');
  point(which, [e.latlng.lat, e.latlng.lng]);
});

for (const k of ['origin', 'destination']) {
  $(k).onchange = () => {
    const p = parse(k);
    if (p.length === 2 && p.every(Number.isFinite)) point(k, p);
  };
}

$('destination-type').onchange = () => {
  $('custom-destination').hidden = false;
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
  if (d.truncated) status('Road display capped at 6,000 segments. Zoom in for more.');
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

function selectRoad(id, name) {
  selectedWay = id;
  $('selected-road').textContent = `${name || 'Unnamed road'} · OSM ${id}`;
  $('apply-condition').disabled = false;
  $('simulation-controls').open = true;
}

async function changeRegion(targetRegion) {
  const version = ++requestVersion;
  region = targetRegion || $('region').value;
  const c = WAYOUT_REGIONS[region] || {
    name: 'Custom area', lat: map.getCenter().lat, lon: map.getCenter().lng,
    hazard: 'earthquake', radius_m: 3000
  };
  $('hazard').value = c.hazard || 'earthquake';
  $('hazard').disabled = true;
  $('map-title').textContent = c.name;
  $('map-radius-label').textContent =
    `${((c.radius_m || 15000)/1000).toFixed(0)} km radius`;
  map.setView([c.lat, c.lon], c.radius_m === 3000 ? 14 : 12);
  if (boundary) map.removeLayer(boundary);
  boundary = L.circle([c.lat, c.lon], {
    radius: c.radius_m || 15000, color: '#16352f', weight: 1.5,
    dashArray: '6 8', fill: false
  }).addTo(map);
  routes.clearLayers();
  facilities.clearLayers();
  roads.clearLayers();
  hazardLayers.splice(0).forEach(l => map.removeLayer(l));
  $('layers').replaceChildren();
  $('results').hidden = true;
  lastResult = null;
  for (const k of Object.keys(points)) {
    map.removeLayer(points[k]);
    delete points[k];
    $(k).value = '';
  }
  pendingPick = 'origin';
  updatePickHint();
  selectedWay = null;
  $('apply-condition').disabled = true;
  $('calculate').classList.remove('ready');
  status('Loading source layers…');
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
        style: f => ({ color: W.colour(f.properties.score ?? f.properties.normalised_value),
                       weight: 1, fillOpacity: .3 }),
        pointToLayer: (f, p) => L.circleMarker(p, { radius: 3, color: '#7b715c' }),
        onEachFeature: (f, l) => l.bindPopup(Object.entries(f.properties).map(([k, v]) =>
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
      : 'No verified destination imported here. Use simulation mode.');
    await conditions();
    await refreshGuide();
  } catch (e) {
    status(e.message);
  }
}
$('region').onchange = () => changeRegion($('region').value);

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

function drawRoute(coords, options, duration = 900) {
  const poly = L.polyline([], options).addTo(routes);
  const total = coords.length;
  let i = 1;
  const step = () => {
    const slice = coords.slice(0, i).map(p => [p[1], p[0]]);
    poly.setLatLngs(slice);
    i++;
    if (i <= total) requestAnimationFrame(step);
  };
  step();
  return poly;
}

async function calculate() {
  if (!points.origin || !points.destination) {
    status('Place both points on the map first.');
    return;
  }
  const routeVersion = requestVersion;
  const button = $('calculate');
  button.disabled = true;
  button.textContent = 'Working…';
  status(`Searching the road graph… first use of ${region} can take a minute.`);
  $('results').hidden = true;
  routes.clearLayers();
  try {
    const d = await W.api('/api/route', {
      method: 'POST',
      body: JSON.stringify({
        region,
        origin: parse('origin'),
        destination: parse('destination'),
        shelter_id: Number($('shelter').value) || null,
        simulation_destination: true,
        mode: $('mode').value,
        hazard: $('hazard').value
      })
    });
    if (routeVersion !== requestVersion) return;
    lastResult = d;
    drawRoute(d.shortest.coordinates,
      { color: '#a48e60', weight: 7, opacity: .85 });
    drawRoute(d.recommended.coordinates,
      { color: '#16352f', weight: 4 });
    const endpoints = d.input_points || [parse('origin'), parse('destination')];
    d.snapped_points.forEach((p, i) =>
      L.polyline([endpoints[i], p],
        { color: '#555', weight: 2, dashArray: '4 6' }).addTo(routes));
    map.fitBounds(routes.getBounds(), { padding: [80, 100], animate: true });
    $('results').innerHTML =
      `<button class="result-close" aria-label="Close results">×</button>
      ${d.simulated ? '<span class="badge">SIMULATION</span>' : ''}
      <h2>Route comparison</h2>
      <p class="fine-print">Not a guarantee of safety. Follow official guidance.</p>
      <div class="compare-grid">
        ${card('SHORTEST · SAND', d.shortest)}
        ${card('RISK-ADJUSTED · GREEN', d.recommended, 'recommended')}
      </div>
      <a class="text-link" href="/route/${d.id}">Open route analysis ↗</a>
      <details><summary>Simulate a road condition</summary>
      ${d.recommended.ways.map(w =>
        `<button class="road-choice" data-way="${w.id}">${W.escape(w.name || 'Unnamed road')} · ${w.id}</button>`
      ).join('')}</details>`;
    $('results').hidden = false;
    requestAnimationFrame(() => $('results').classList.add('slide-in'));
    $('results').querySelector('.result-close').onclick = () => {
      $('results').hidden = true;
      $('results').classList.remove('slide-in');
    };
    $('results').querySelectorAll('[data-way]').forEach(
      b => b.onclick = () => selectRoad(Number(b.dataset.way), b.textContent));
    try {
      const ex = await W.api('/api/explain', {
        method: 'POST',
        body: JSON.stringify({ result: d })
      });
      showExplainer(ex);
    } catch (e) { assistantHtml('Route explained', '<p>Could not load explanation.</p>'); }
    status('Comparison complete. Check the assistant panel.');
  } catch (e) {
    status(e.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Compare routes <span>↗</span>';
  }
}
$('calculate').onclick = calculate;

$('demo').onclick = async () => {
  try {
    const d = await W.api('/api/demo?region=' + region);
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
      body: JSON.stringify({ region, way_id: selectedWay, condition: $('condition').value })
    });
    await conditions();
    await calculate();
  } catch (e) { status(e.message); }
};

$('reset-conditions').onclick = async () => {
  try {
    await W.api('/api/simulations?region=' + region, { method: 'DELETE' });
    await conditions();
    status('Simulated conditions cleared.');
  } catch (e) { status(e.message); }
};

$('locate').onclick = () => {
  if (!navigator.geolocation) { status('Geolocation is unavailable.'); return; }
  status('Requesting your location…');
  navigator.geolocation.getCurrentPosition(
    p => {
      const lat = p.coords.latitude, lon = p.coords.longitude;
      point('origin', [lat, lon]);
      map.setView([lat, lon], 15);
    },
    err => status('Location failed: ' + (err.message || 'unknown')),
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
  );
};

/* ---------------- Explore the world ---------------- */
let progressTimer = null;

async function exploreHere() {
  if (!navigator.geolocation) { status('Geolocation is unavailable.'); return; }
  $('explore-here').disabled = true;
  $('explore-here').textContent = 'Requesting location…';
  navigator.geolocation.getCurrentPosition(async p => {
    const lat = p.coords.latitude, lon = p.coords.longitude;
    $('explore-here').textContent = 'Preparing your area…';
    try {
      const start = await W.api('/api/region/prepare', {
        method: 'POST',
        body: JSON.stringify({ lat, lon })
      });
      const rid = start.region_id;
      showProgress(start);
      clearInterval(progressTimer);
      progressTimer = setInterval(async () => {
        try {
          const s = await W.api('/api/region/status?region_id=' + rid);
          showProgress(s);
          if (s.state === 'ready') {
            clearInterval(progressTimer);
            const shortName = `Custom (${lat.toFixed(2)}, ${lon.toFixed(2)})`;
            WAYOUT_REGIONS[rid] = {
              name: shortName, short: 'Custom', country: '',
              lat, lon, hazard: 'flood', radius_m: 3000
            };
            const opt = document.createElement('option');
            opt.value = rid; opt.textContent = shortName;
            $('region').appendChild(opt);
            $('region').value = rid;
            $('custom-progress').hidden = true;
            await changeRegion(rid);
            assistantHtml('Custom region ready',
              `<p>Global flood, landslide and NASA SRTM terrain are active
               for ${W.escape(shortName)}.</p>
               <p class="fine-print">Jurisdiction-specific datasets are not
               available for arbitrary locations. This area uses the global
               sources only.</p>`);
            $('explore-here').disabled = false;
            $('explore-here').textContent = '📍 Explore the world around me';
          } else if (s.state === 'failed') {
            clearInterval(progressTimer);
            $('custom-progress').hidden = true;
            status('Preparation failed: ' + (s.error || s.message || 'unknown'));
            $('explore-here').disabled = false;
            $('explore-here').textContent = '📍 Explore the world around me';
          }
        } catch (e) {
          clearInterval(progressTimer);
          status('Status check failed: ' + e.message);
        }
      }, 1500);
    } catch (e) {
      status('Prepare failed: ' + e.message);
      $('explore-here').disabled = false;
      $('explore-here').textContent = '📍 Explore the world around me';
    }
  }, () => {
    status('Location required to explore your area.');
    $('explore-here').disabled = false;
    $('explore-here').textContent = '📍 Explore the world around me';
  }, { enableHighAccuracy: false, timeout: 10000 });
}

function showProgress(job) {
  $('custom-progress').hidden = false;
  const pct = Math.max(0, Math.min(100, job.progress || 0));
  $('progress-fill').style.width = pct + '%';
  $('progress-message').textContent = `${job.message || 'Working…'} (${pct}%)`;
}

$('explore-here').onclick = exploreHere;

/* ---------------- Search (Nominatim) ---------------- */
let timer, searchVersion = 0;
$('search').oninput = () => {
  clearTimeout(timer);
  const version = ++searchVersion;
  const q = $('search').value.trim();
  if (q.length < 3) { $('suggestions').replaceChildren(); return; }
  timer = setTimeout(async () => {
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&limit=8&addressdetails=0&q=${encodeURIComponent(q)}`;
      const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
      const rows = await res.json();
      if (version !== searchVersion) return;
      $('suggestions').replaceChildren();
      if (!rows.length) {
        const none = document.createElement('div');
        none.className = 'suggestion';
        none.style.cursor = 'default';
        none.textContent = 'No matches.';
        $('suggestions').append(none);
        return;
      }
      rows.forEach(r => {
        const b = document.createElement('button');
        b.className = 'suggestion';
        b.textContent = r.display_name;
        b.onclick = () => {
          const lat = Number(r.lat), lon = Number(r.lon);
          const which = pendingPick || (!points.origin ? 'origin' : 'destination');
          point(which, [lat, lon]);
          map.setView([lat, lon], 15);
          $('suggestions').replaceChildren();
        };
        $('suggestions').append(b);
      });
    } catch (e) { status('Search unavailable: ' + e.message); }
  }, 400);
};

/* ---------------- 3D tilt toggle ---------------- */
const tiltBtn = document.getElementById('tilt-toggle');
if (tiltBtn) {
  tiltBtn.onclick = () => {
    is3D = !is3D;
    document.querySelector('.map-stage').classList.toggle('perspective', is3D);
    tiltBtn.textContent = is3D ? 'Flat view' : '3D view';
    /* Leaflet needs a nudge when its container transform changes. */
    setTimeout(() => map.invalidateSize(), 400);
  };
}

const initial = new URLSearchParams(location.search).get('region');
if (WAYOUT_REGIONS[initial]) $('region').value = initial;
changeRegion($('region').value);