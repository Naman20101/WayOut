# Acquired data and implementation status — 18 September 2026

The Phase 1 documents describe candidates. This file records what the application actually uses.

| Region | Road nodes | Road edges | Search locations | Routing evidence |
|---|---:|---:|---:|---|
| Kochi | 54,380 | 63,812 | 1,513 | KSDMA historical 50-year mapped flood footprint + NASA SRTM terrain |
| Kathmandu | 69,598 | 84,625 | 4,035 | USGS 2015 Gorkha event, 2020 Atlas ShakeMap MMI + NASA SRTM terrain |
| Tokyo | 439,177 | 635,110 | 7,494 | TMG ninth assessment collapse/fire ranks and activity difficulty + NASA SRTM terrain |

Totals count processed undirected edge records before mode-specific direction expansion, not unique named streets. Search locations are mapped facilities/places, not verified shelters.

Every preserved download has a provenance sidecar with URL, timestamp, byte count and SHA-256. `data/download_manifest.json` consolidates these records and supports re-download. The importer keeps original numeric observations alongside derived scores and coverage. Regional geometry is clipped to a geodesic 15 km circle. Roads crossing the boundary may be shortened or omitted at available source nodes; this is a finite study graph.

## Source handling

- **KSDMA:** the three historical 10/25/50-year rasters were obtained. Only the 50-year valid-data footprint is scored, as 100. Raw units remain unresolved; neither metres nor centimetres are asserted. Missing cells remain unknown. Raw averages are retained for audit, not presented as flood depth.
- **USGS:** the real Gorkha event and Atlas grid are preserved. MMI is normalised with clamp((MMI−1)/9 × 100). Nearest grid cells supply sampled intensity. The timestamp is a historical event, not a forecast.
- **TMG earthquake ranks:** source CP932 shapefile attributes are decoded, transformed from JGD2000 Japan Zone IX to WGS84 and cropped. Invalid polygon geometries are repaired with a zero-distance buffer before intersection. Scores are ordinal rank × 20; difficulty is coefficient × 100, capped at 100. A repaired polygon is a processing result, not a newly surveyed boundary.
- **NASA SRTM:** SRTMGL1 v003 1 arc-second tiles are downloaded with an Earthdata bearer token, mosaicked at load, and sampled at the same 40 m spacing as the primary hazard. Elevation is banded per region (Kochi 5–50 m; Kathmandu 1280–1420 m; Tokyo −2–25 m) into a relative low-lying indicator. Slope is derived via numpy gradient and scored 0 below 2° and 100 above 15°. Both are stored as hazards `elevation` and `slope` under `source_id='nasa_srtm'`. Terrain is globally complete; a missing tile is a pipeline failure, not a route risk.
- **TMG liquefaction:** borehole PL classes and 2011 historical polygons are map layers only. No interpolation or road-risk claim is made from isolated points. Other downloaded ground archives are preserved but not used in routing.
- **Sumida:** exact normalised school-name matches link a 2022 official shelter designation to OSM facility coordinates. This is not an entrance survey or opening feed. Fire evacuation-area designation is not inferred from a shelter listing.
- **IOM:** the open-spaces PDF was obtained and reviewed as historical reference. It is not imported as a coordinate-verified operational shelter layer.
- **OSM:** local Overpass extracts contain road ways and relevant infrastructure/place nodes. Basic access and one-way tags are used. Turn restrictions, conditional access and full building surveys are not collected.

## Unavailable evidence

No verified current shelter opening/capacity/access feed, no live disaster road closures, no credible building-level inspection data and no suitable ML training set were obtained. Kochi and Kathmandu destination selectors therefore report unavailable verified destinations. User-selected endpoints are explicitly simulation points. Reserved building tables remain empty.

## Interpretation and distribution

The model's numeric weights are declared assumptions. Scores must not be interpreted as casualty probabilities or used to compare absolute safety across countries. A 100 unknown-data penalty is a modelling preference, not an observed extreme hazard. In Kochi, it makes the effective model index uniform; the app discloses the resulting inability to distinguish flood severity.

The raw data stays in this local research workspace. The source-code ZIP excludes raw/processed data and credentials. Before redistributing source datasets or publishing the service, resolve the reuse terms flagged in the database source register. OSM attribution and ODbL obligations apply to derived graph data; TMG ground and Sumida datasets retain their listed attribution terms. NASA SRTM is open data but requires product citation. The manifest allows independent acquisition instead of silently redistributing uncertain-licence archives.
