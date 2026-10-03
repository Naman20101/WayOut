# WAYOUT

**Safer Routes. Brighter Tomorrows.**

A Python and MySQL-based geospatial decision-support system that combines historical hazard data, infrastructure information and risk-weighted graph routing to recommend lower-risk evacuation paths.

This is a Grade 12 CBSE educational prototype, not operational emergency navigation. Follow official authorities during an emergency. Route indices are model outputs, not probabilities or guarantees of safety.

## Open this prepared installation

Run `Start-WAYOUT.ps1` in PowerShell, then open http://127.0.0.1:5000. The prepared database runs separately on localhost port 3307; the existing MySQL service is not modified. The launcher uses the virtual environment and isolated database in the workspace's `work` folder. Keep those folders together. Local credentials are in `.env`; never publish that file or the `work` folder.

The demo button selects actual connected OpenStreetMap junctions. Its destination is explicitly a **SIMULATION**, not a shelter. The first route in a region loads its graph into memory; Tokyo can take a minute or more and requires substantially more memory than Kochi. Allow roughly 4 GB free memory when using all three regions.

## Install on another computer

1. Install Python 3.12 and MySQL 8.0 or newer.
2. In this project folder: `python -m venv .venv`, then `.venv\Scripts\python -m pip install -r requirements.txt`.
3. Create an empty MySQL database `wayout` using UTF-8 (`utf8mb4`), and a local application account with privileges on that database only. Choose your own password.
4. Copy `.env.example` to `.env`, enter your connection details and a random secret. Use port 3306 for a normal MySQL installation, or your actual configured port.
5. Run `python database_setup.py` with the virtual environment activated.
6. If raw/processed data are not supplied, run `python scripts/fetch_manifest.py`, then `python scripts/preprocess_data.py --region kochi`, repeating for `kathmandu` and `tokyo`.
7. Run `python scripts/import_mysql.py --region kochi`, repeating for each region. Imports replace that region's source graph and simulations transactionally. They preserve historical result snapshots. Stop Flask before reimporting to avoid stale graph caches.
8. Run `python scripts/prepare_demo.py kochi`, repeating for each region.
9. Run `python app.py`, and open http://127.0.0.1:5000.

The app binds to localhost with debug disabled. This is a local classroom deployment. Public hosting requires production serving, operational security review and source licence review; no public deployment is included.

## NASA SRTM terrain

WAYOUT integrates NASA SRTMGL1 v003 1 arc-second elevation as an additive terrain modifier on top of each region's primary hazard index. Two components are sampled at 40 m spacing along each road edge:

- **Elevation band** — a relative low-lying indicator, banded per region (e.g. Kochi coastal: 5–50 m; Kathmandu valley floor: 1280–1420 m; Tokyo reclaimed waterfront: −2–25 m).
- **Slope** — derived from the SRTM grid via numpy gradient, scored 0 below 2° and 100 above 15°. Walking-accessibility indicator only, not a landslide classifier.

Both are stored in the existing `risk_scores` table as hazards `elevation` and `slope`, with `source_id='nasa_srtm'`, and contribute through `TERRAIN_WEIGHTS` in `routing/risk_router.py`. Terrain is globally complete, so a missing tile is a pipeline failure — not a reason to apply the pessimistic 100-point unknown penalty. This differs from the primary hazard, which uses the 100-point penalty for uncovered stretches.

Registration at https://urs.earthdata.nasa.gov/ is required. Add the bearer token to `.env` as `EARTHDATA_TOKEN=`. Without it, SRTM downloads fail explicitly with a clear message; no substitute elevation source is silently used.

## What is implemented

- Three 15 km study regions: Kochi, Kathmandu and eastern Tokyo.
- Real OSM graph topology, mode restrictions and basic one-way rules, imported into MySQL.
- Preserved official hazard sources with source registry and hash manifests.
- NASA SRTMGL1 v003 elevation and derived slope, sampled at the same 40 m cadence as the primary hazard.
- Custom heap-based Dijkstra for shortest and risk-adjusted routes with identical endpoints.
- Search, map selection, optional device location, source overlays and route comparison.
- Session-isolated simulated road conditions and route history; source-backed Tokyo shelter designations.
- Dashboard, historical events, methodology, source register and clear unavailable-data states.
- Parameterised SQL, transactions, validation, CSRF protection and session-private result pages.

## Evidence limits

Kochi uses a flood-footprint indicator, not depth, because raw raster units could not be verified. Its unknown-data penalty equals its mapped-footprint indicator, so the flood model alone cannot favour a different path. Kathmandu uses one historical 2015 ShakeMap; it is not a forecast. Tokyo uses neighbourhood ranks, not building inspections. Liquefaction points and history are map-only evidence. Kochi and Kathmandu do not have sufficiently verified geolocated shelter records imported; use explicitly marked simulation points there. Current shelter opening, entrances and capacities are unverified everywhere.

SRTM elevation is a relative-terrain indicator, not a flood depth. Its bands are a WAYOUT modelling choice documented in methodology, not an official classification.

No building-level structural dataset or suitable verified training set was obtained. The relevant schema tables are empty; ML is deliberately omitted. Do not fill these gaps with invented records.

## Project guide

| Location | Purpose |
|---|---|
| `app.py`, `db.py`, `config.py` | Flask routes, parameterised MySQL access, configuration |
| `database/schema.sql` | Relational schema and integrity constraints |
| `routing/` | Graph loading, modes, Dijkstra, scoring and comparison |
| `scripts/` | Downloads (including NASA SRTM), cropping, source joins, import, demos, live checks |
| `data/raw/` | Preserved downloads and provenance sidecars |
| `data/processed/` | Inspectable graph, hazard layers and regional summaries |
| `templates/`, `static/` | Jinja, CSS, JavaScript, local Leaflet and official logo |
| `tests/` | Isolated algorithm, API and validation tests |
| `docs/` | Research, report, viva, test evidence and limitations |

Run `python -m pytest tests -q`. With the server and database running, run `python scripts/verify_live.py`; this writes `docs/live_validation.json` and creates test route snapshots in an isolated HTTP session. Synthetic test graphs exist only in tests, never in the app database.

Basemap tiles require internet and are best-effort. If the provider is unavailable, enable the local Road network layer; local graph routing does not require a tile service. Do not bulk-download OpenStreetMap tiles. See https://operations.osmfoundation.org/policies/tiles/. The original logo is retained unchanged. Leaflet attribution and OSM attribution remain visible.
