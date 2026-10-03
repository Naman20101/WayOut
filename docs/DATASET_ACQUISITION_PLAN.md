# WAYOUT — Dataset Acquisition Plan

**Phase 1 research • 17 September 2026**  
Safer Routes. Brighter Tomorrows.

## Decision

Retain all three requested study regions. Start implementation with Kochi once its flood files and at least one eligible destination pass inspection. Tokyo has the strongest identified combination of official hazard and evacuation sources. Kathmandu is feasible for historical earthquake planning, but building-level routing remains conditional on obtaining spatially usable records.

**Research is complete at source-identification level; the data foundation has not yet passed file-level validation.** This package does not claim that a published download link means a usable dataset has been acquired. No road network, shelter inventory, hazard raster or building microdata has been imported. No route results have been generated. Full website implementation has therefore not begun.

The companion [source register](data_sources.md) records formats, dates, licensing evidence, access methods and limitations. The [region report](REGION_SELECTION_REPORT.md) explains the proposed centres.

> WAYOUT is an educational disaster-planning prototype. Risk calculations are based on historical and publicly available datasets and may be incomplete, outdated, or inaccurate. During an actual emergency, always follow instructions from official authorities.

## What the research established

| Region | Core sources to acquire | Principal unresolved issue | Proposed initial scope |
|---|---|---|---|
| Kochi / northern Ernakulam | KSDMA historical flood rasters; local OSM graph; official destination evidence; NASA SRTM | Flood archive contents, licence and current destination designation need verification | Historical flood exposure routing with terrain; no structural-safety claims |
| Kathmandu | USGS historical shaking; IOM humanitarian open spaces; local OSM graph; NSO building survey if accessible; NASA SRTM | Survey coordinates/access and biased damaged-house coverage | Historical earthquake scenario; structural layer only where evidence supports it |
| Eastern Tokyo | TMG neighbourhood risk; GSI hazard-specific evacuation sites; TMG ground layers; local OSM graph; NASA SRTM | Boundary join, file access and vintage alignment | Earthquake, collapse/fire and separately supported ground exposure with terrain |

KSDMA publishes historical flood raster links and an Ernakulam exposure map. These are better candidates than estimating flood risk from distance to a river alone. [KSDMA hazard catalogue](https://sdma.kerala.gov.in/hazard-maps/)

Nepal's official HRHRS catalogue distinguishes complete enumeration in 11 districts from damaged-house verification in 20, including Kathmandu, Lalitpur and Bhaktapur. An absent record cannot be treated as an undamaged building. [NSO survey description](https://microdata.nsonepal.gov.np/index.php/catalog/69/study-description)

Tokyo's current liquefaction landing page identifies a March 2026 revision; older references to 2023 are not the current edition. A map revision date does not prove every underlying observation was collected that year. [TMG liquefaction map](https://doboku.metro.tokyo.lg.jp/start/03-jyouhou/ekijyoukaEn/top.aspx)

NASA SRTMGL1 v003 provides globally consistent 1 arc-second elevation. It is not a flood depth model and does not supersede local hydrology; it supports a relative low-lying indicator and slope for walking accessibility. Registration at https://urs.earthdata.nasa.gov/ is required.

## Acquisition order

1. **Freeze the proposed study circles and source manifest.** Store WGS84 centres, a 15,000 m radius, source URLs and a version identifier. Inspect actual spatial coverage before treating the centres as final.
2. **Kochi first:** acquire the two historical return-period archives, Ernakulam map, NASA SRTM tiles and an OSM road extract. Inspect raster units, bands, resolution, CRS, NoData and coverage. Establish one officially evidenced destination and its accessible entrance. If none qualifies, retain the map and an explicitly labelled simulation; do not manufacture a shelter.
3. **Complete one real routing proof:** test two connected points and an eligible destination using the inspected Kochi graph, hazard data and SRTM terrain. Compare distance-only and risk-adjusted cost. Identical paths are a legitimate outcome.
4. **Kathmandu:** obtain the IOM report, select a reproducible USGS shaking product, download NASA SRTM tiles, and resolve NSO microdata access. Test geographic identifiers before designing a building-to-road join. Historical open spaces need current-status checks.
5. **Tokyo:** acquire neighbourhood risk tables and compatible polygons, evacuation sites, ground shapefiles and NASA SRTM tiles. Inspect joining keys, Japanese text encoding, source units and hazard-specific destination eligibility.
6. **Only after acceptance:** implement the MySQL schema and pipeline, then graph/routing, Flask, UI, other regions and simulations in the requested sequence. Optional ML comes last and may remain omitted.

## Exact acquisition and manual-access handoff

Paths below are proposed locations relative to the future `wayout/` project root. Retain publisher filenames inside these folders. Do not overwrite raw files. The folders are instructions, not claims that files already exist.

| Item | Source and file to select | Save under | Access finding / next action |
|---|---|---|---|
| Kochi flood rasters | [KSDMA hazard maps](https://sdma.kerala.gov.in/hazard-maps/): under **Historic Data**, both "Flood Return Probability (10, 25, 50 years)" and "(100, 200, 500 years)" archives | `data/raw/kochi/ksdma_flood_historical/` | Links published; research fetch failed. Use these exact link labels; archive filenames and internal formats remain unverified. Do not substitute the RCP8.5 archives. |
| Kochi exposure map | [Ernakulam_Hist.pdf](https://sdma.kerala.gov.in/wp-content/uploads/2022/05/Ernakulam_Hist.pdf) | `data/raw/kochi/ksdma_reference/` | Reference map/table; verify map edition and legend. Exposed schools/hospitals are not designated shelters. |
| 2018 depth observations | [KSDMA crowd-source page](https://sdma.kerala.gov.in/crowd-sourcing-flood-2018/), linked `CROWD_INUNDATION.pdf` | `data/raw/kochi/flood_2018/` | PDF identified. Original point CSV/SHP with depth units, dates and quality flags still needed for numerical analysis; request from KSDMA if not supplied publicly. |
| 2018–2020 flood footprints | [Event-specific maps](https://sdma.kerala.gov.in/event-specific-maps/), Floods rows for each year; 2019 `Flood_2019-1.pdf`, 2020 `Flood-Inundation-Map_2020.pdf` | `data/raw/kochi/historical_events/` | Map PDFs available as evidence; native inundation polygons/rasters not verified. Ask KSDMA/NRSC for GIS originals before road scoring. |
| Landslide susceptibility | [KSDMA hazard maps](https://sdma.kerala.gov.in/hazard-maps/), **GSI 2022 shapefiles → Ernakulam** | `data/raw/kochi/gsi_landslide/` | Link identified; archive retrieval failed. Keep optional unless it overlaps the study graph. |
| Kochi destinations | [Ernakulam district flood relief](https://ernakulam.nic.in/en/district-news/) and [2015 district plan](https://sdma.kerala.gov.in/wp-content/uploads/2018/11/7-Ernakulam-Final.pdf) | `data/raw/kochi/destinations/` | Current geocoded designated list not verified. Needed: DDMA/municipal facility list with name, address/coordinates, disaster applicability and date. Historical beneficiary lists are not a current inventory; do not import household personal details. |
| Kathmandu survey | [NSO HRHRS catalogue 69](https://microdata.nsonepal.gov.np/index.php/catalog/69/study-description); [related materials](https://microdata.nsonepal.gov.np/index.php/catalog/69/related-materials), English questionnaire `989`, key findings `991` | `data/raw/kathmandu/hrhrs/` | Original `eq2015.npc.gov.np` failed to load; NSO documentation is discoverable. Need authorised building structure/damage records, data dictionary and geographic lookup. Actual microdata filenames/formats/licence and coordinate availability not verified. Do not mistake questionnaire downloads for microdata. |
| Kathmandu open spaces | [IOM 2020 report](https://publications.iom.int/books/updated-report-83-open-spaces-identified-humanitarian-purposes-kathmandu-valley), `Update_Report_On_83_Open_Spaces_Identified_for_Humanitarian_Purposes_in_Kathmandu_Valley.pdf` | `data/raw/kathmandu/iom_open_spaces/` | Download linked PDF; transcribe only supported fields with page references. Need current designation/accessibility corroboration. No invented capacities. |
| Historical shaking | [USGS ShakeMap Atlas](https://earthquake.usgs.gov/data/shakemap/atlas/), select the **25 April 2015 Gorkha event** and inspect its downloadable numerical products | `data/raw/kathmandu/usgs_gorkha/` | Event-specific grid URL/version not fixed here. Save product metadata, contributor, timestamp, grid and uncertainty if available. Do not download an unrelated example event. |
| NASA SRTM elevation | [LP DAAC SRTMGL1 v003](https://lpdaac.usgs.gov/products/srtmgl1v003/), Earthdata bearer token | `data/raw/<region>/srtm/` | Required tiles: Kochi `N09E076`, `N10E076`; Kathmandu `N27E085`; Tokyo `N35E139`. Save per-tile sidecars. Vertical datum EGM96 (geoid), void −32768. |
| Tokyo regional risk | [Official API catalogue entry](https://spec.api.metro.tokyo.lg.jp/spec/t000008d0000000012-5611a503ba1c2785d49d69234d168148-0?lang=en): advertised `all2.csv`; [current ward tables](https://www.funenka.metro.tokyo.lg.jp/area-hazard-level/regional-risk-list/index.html) | `data/raw/tokyo/tmg_regional_risk/` | Catalogue advertises legacy CSV path; current ward pages provide fallback reference. CSV payload/encoding and reuse terms still need inspection. |
| Tokyo evacuation sites | [GSI designated sites](https://www.gsi.go.jp/bousaichiri/hinanbasho), CSV/GeoJSON download for relevant municipalities | `data/raw/tokyo/gsi_evacuation/` | Select both emergency evacuation sites and shelters as separate datasets; preserve earthquake/fire applicability and source update dates. |
| Sumida cross-check | [Sumida facility list](https://www.city.sumida.lg.jp/kuseijoho/sumida_info/opendata/opendata_ichiran/bosai_data/hinan_data.html), `hinan_20220301.csv` | `data/raw/tokyo/sumida/` | March 2022 list; published link found, payload fetch failed. Historical cross-check, not proof of 2026 opening. |
| Tokyo ground layers | Enter through [TMG liquefaction homepage](https://doboku.metro.tokyo.lg.jp/start/03-jyouhou/ekijyoukaEn/top.aspx), then **Public Data (Map Information)**; select PL distribution, groundwater distribution, liquefaction history and landfill-material **Shape File** links | `data/raw/tokyo/tmg_ground/` | Download links and CC BY 2.1 JP identified. PL archive fetch failed; internal fields/CRS still unverified. Do not infer a prediction-grid download from a borehole-point file. |

## Road, building and infrastructure extraction

Use [OSM data](https://www.openstreetmap.org/copyright) through a bounded [Overpass query](https://wiki.openstreetmap.org/wiki/Overpass_API). Save the query and snapshot timestamp. OSM data uses ODbL, with contributor attribution and applicable database obligations. It does not certify road passability or shelter status.

Proposed extraction specification:

- Query road ways intersecting a small bounding rectangle around each circle; retrieve referenced nodes and applicable restriction relations. Clip geometries to the actual circle while retaining valid boundary endpoints and topology. Download buildings separately in tiles if needed.
- Keep `highway`, `oneway`, `access`, `foot`, `bicycle`, `motor_vehicle`, `surface`, `bridge`, `tunnel`, `layer`, and restrictions where present. A missing tag is unknown, not permission inferred without a documented default.
- Keep hospitals, clinics, police and fire facilities as infrastructure categories. Schools, parks and open spaces remain ordinary features until an independent designation supports evacuation use.
- Never join crossing roads solely because their drawn lines intersect: bridges and tunnels may be grade-separated. Validate components and entrance connections for each transport mode.
- Use the same origin and destination for shortest/recommended route comparison. If choosing among destinations, state the eligible set and selection rule separately.

## Planned preprocessing and acceptance checks

These are proposed engineering rules; no processing has been performed yet.

| Check | Acceptance evidence required |
|---|---|
| Provenance | Original bytes, source URL, retrieved UTC time, SHA-256, publisher, dataset edition, licence text/reference and processing log |
| Spatial validity | CRS confirmed from metadata, plausible bounds, valid geometry, units, 15 km intersection, and an explicit coverage mask |
| Raster meaning | Band descriptions, cell size, NoData handling, physical units and return-period/scenario identity established |
| Tabular joins | Stable IDs, duplicate audit, unmatched rows and boundary-vintage conflicts reported; no guessed geographic joins |
| Destinations | Source-backed designation, applicable hazard, date, location confidence and reachable entrance; capacity nullable |
| Routing | Nonnegative costs; modes/access respected; no-route handling; blocked edges removed; results reproducible from source and scoring versions |
| Missingness | Unknown remains NULL/NoData. Report supported distance fraction; no default zero-risk substitution |
| SRTM terrain | Tile-level SHA-256, EGM96 datum acknowledged, void −32768 handled as NaN, slope derived from numpy gradient of projected grid. Missing terrain is a pipeline failure, never 100. |
| Representation | Historical, modelled, observed and simulated data visibly distinguished; no fabricated dashboard counts |

Do not convert return period directly into road flood severity. For example, `1/T` may express annual exceedance probability under a model's assumptions; it is not water depth, and a 100-year event is not a scheduled event. Inspect whether the rasters encode depth, extent or another quantity before specifying a 0–100 conversion.

Tokyo's rank categories are ordinal. A future mapping such as category-to-score would be a WAYOUT modelling choice, not a collapse probability; validate it against the source definitions and label it accordingly. Avoid adding overall earthquake risk to its component collapse/fire terms and counting the same evidence twice.

Distance-weighted exposure should use edge length inside each zone or sampled raster segment, not one sample at an entire road's midpoint. Preserve original values and transformation version. Reproject into appropriate metric CRSs for processing (Kochi UTM 43N; Kathmandu UTM 45N; Tokyo UTM 54N or a documented local Japanese CRS); serve map geometries in WGS84.

## Unresolved features and release gate

No verified local Kochi building-material/age inventory, street-scale Kathmandu soil/liquefaction layer, or current Kochi shelter operating-status feed was established. Rainfall, coastal, industrial and tsunami features remain optional; a source's existence does not justify enabling every layer. The source register identifies reference-only candidates.

No ML training is justified yet. Later modelling would require legal access, meaningful labels, spatially separated validation, and a check for post-disaster leakage and selection bias. A deterministic project remains a valid result.

Advance beyond the data gate only after at least one Kochi hazard dataset, connected road extract, source-backed destination and SRTM terrain pass the checks above. Source discovery supports acquisition work; it does not justify presenting a working evacuation recommendation yet. No approval request is implied by this gate—the outstanding work is evidence collection and validation.

## Research access log

- Government/UN source pages and indexed publication descriptions were reviewed on 2026-09-17; dataset observation years are recorded separately.
- The original Nepal earthquake portal and several archive/CSV links returned research-tool retrieval errors. This does **not** establish a permanent outage or an authentication requirement.
- A local Python network probe failed DNS resolution; no source files were silently substituted.
- Binary archive contents, checksums, feature counts, complete geographic coverage and current operational facility status remain unverified. No uninspected file is labelled acquisition-complete.
