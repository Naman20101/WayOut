window.WAYOUT={
  escape(value){const e=document.createElement('span');e.textContent=String(value??'');return e.innerHTML;},
  async api(url,options={}){const r=await fetch(url,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content,...options.headers}});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed. Please try again.');return d;},
  colour(v){return v==null?'#9ba49a':v<=20?'#547b66':v<=40?'#95a87b':v<=60?'#d9c779':v<=80?'#b87342':'#9b4d3e';},
  terrainColour(slopeDeg){return slopeDeg==null?'#c9cfc2':slopeDeg<=2?'#e8efe2':slopeDeg<=5?'#dfe6cf':slopeDeg<=10?'#d3c9a4':'#c4a98a';},
  km(v){return(Number(v)/1000).toFixed(2);},
  number(v){return v==null?'Data unavailable':Number(v).toLocaleString();},
  /* MapLibre vector basemap via the Leaflet bridge. Smooth at every zoom. */
  tile(map){
    const style = 'https://tiles.openfreemap.org/styles/liberty';
    if (typeof L.maplibreGL === 'function') {
      return L.maplibreGL({ style }).addTo(map);
    }
    /* Fallback: raster tiles if the MapLibre bridge failed to load. */
    return L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
  }
};