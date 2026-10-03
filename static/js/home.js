/* Home hero map. Region is driven by ?region= or the API default. */
(async () => {
  const params = new URLSearchParams(location.search);
  const requested = params.get('region');
  let regions, order, current;

  try {
    const data = await WAYOUT.api('/api/regions');
    regions = data.regions;
    order = data.order;
    current = (requested && regions[requested]) ? requested : data.default;
  } catch (e) {
    const cap = document.querySelector('.map-caption span:last-child');
    if (cap) cap.textContent = 'Start MySQL to load local data';
    return;
  }

  const cfg = regions[current];

  const map = L.map('hero-map', {
    zoomControl: false, scrollWheelZoom: false, dragging: false,
    doubleClickZoom: false, boxZoom: false, touchZoom: false, keyboard: false,
  }).setView([cfg.lat, cfg.lon], 11);
  WAYOUT.tile(map);

  L.circle([cfg.lat, cfg.lon], {
    radius: 15000, color: '#16352f', weight: 1, dashArray: '5 7',
    fillColor: '#d6c7a1', fillOpacity: .12,
  }).addTo(map);

  const topLabel = document.querySelector('.map-topline b');
  const floatLink = document.querySelector('.map-float a');
  const floatTitle = document.querySelector('.map-float strong');
  if (topLabel) topLabel.textContent = cfg.name.toUpperCase();
  if (floatLink) floatLink.textContent = `Explore ${cfg.short} \u2197`;
  if (floatTitle) floatTitle.textContent = 'Beyond the shortest path.';

  const caption = document.querySelector('.map-caption');
  if (caption && !document.getElementById('hero-region-switch')) {
    const wrap = document.createElement('span');
    wrap.id = 'hero-region-switch';
    wrap.style.marginLeft = 'auto';
    order.forEach(key => {
      const a = document.createElement('a');
      a.href = `/?region=${key}`;
      a.textContent = regions[key].short;
      a.style.marginLeft = '10px';
      a.style.textDecoration = 'underline';
      if (key === current) a.style.fontWeight = '700';
      wrap.appendChild(a);
    });
    caption.appendChild(wrap);
  }

  const dLon = 0.14 / Math.max(0.3, Math.cos(cfg.lat * Math.PI / 180));
  const dLat = 0.13;
  const bounds = [cfg.lon - dLon, cfg.lat - dLat,
                  cfg.lon + dLon, cfg.lat + dLat].join(',');
  try {
    const roads = await WAYOUT.api(
      `/api/roads?region=${current}&bounds=${bounds}`);
    L.geoJSON(roads, {
      style: { color: '#7d907d', weight: .8, opacity: .6 },
    }).addTo(map);
  } catch (e) {
    const cap = document.querySelector('.map-caption span:last-child');
    if (cap) cap.textContent = e.message;
  }
})();
