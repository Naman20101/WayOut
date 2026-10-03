# Verification record — 18 September 2026

## Automated checks

`python -m pytest tests -q`: **13 passed**. Covers Dijkstra optimality and closure exclusion, negative-cost rejection, one-way/mode filtering, missing-data penalties, malformed/out-of-region coordinates, HTML page rendering, CSRF enforcement, controlled database-failure response, and a test-only graph where risk weighting intentionally selects a longer path.

Actual MySQL INSERT, SELECT, UPDATE and DELETE were exercised inside a rolled-back transaction. No mock geographic rows were imported. Actual Tokyo road closure simulation was applied, rerouted, checked for exclusion from both returned paths, and cleared. A separate HTTP session could not see those simulated conditions or saved route results.

## Live routes

`scripts/verify_live.py` generated `docs/live_validation.json` using real imported endpoints and the Flask HTTP API. Eight of nine region/mode comparisons returned routes. Kochi cycling returned an explicit disconnected-graph response; no fallback path was generated. Every successful response satisfied:

- shortest distance ≤ risk-adjusted distance;
- risk-adjusted cost ≤ the shortest path evaluated using the same risk objective;
- saved result available in its own browser session and unavailable in another.

Cold graph load plus route time was approximately 2.6 s for Kochi, 4.3 s for Kathmandu and 78.4 s for Tokyo on this machine. Warm comparisons ranged approximately 0.2–2.6 s. These are observations from this run, not performance guarantees. The larger Tokyo graph is memory-intensive; the application is scoped to local classroom use.

Tokyo walking used 1,273.5 m shortest and 1,276.4 m weighted paths; cycling used 1,275.8 m and 1,279.2 m. The illustrated walking model index decreased from 40.0 to 39.7. This small model improvement is not a measured real-world safety benefit. Kochi and Kathmandu's illustrated walking routes were identical under both objectives.

## Browser verification

The homepage and planner were inspected in the in-app browser. Kochi and Tokyo demonstrations displayed real paths, comparisons, source coverage, simulation labels and limitations. Tokyo exposes collapse, fire, emergency activity difficulty, ground observations and liquefaction-history toggles. Brand markers use green/sand and the supplied logo remains unchanged. The homepage was checked at a 390 × 844 mobile viewport; responsive layout and navigation were visible without horizontal overflow.

An initial restrictive referrer policy caused OSM tile requests to be denied. It was corrected to `strict-origin-when-cross-origin`, consistent with the provider's required browser referrer behaviour, and maps rendered successfully on recheck. Attribution was moved above overlaid footer notices. Tile availability is external and not guaranteed; local graph data remains independent of the basemap.

## Remaining limits

No live emergency validation, audited road passability, shelter opening checks, measured forecast accuracy, accessibility certification or professional structural assessment is claimed. The missing building dataset, historical shelter status and unresolved flood units are deliberate visible limitations. NASA SRTM terrain is a relative-terrain indicator, not a flood depth. See `DATA_STATUS.md` and the methodology page.

Final dashboard regression: the expensive edge-risk aggregation was replaced with a labelled source-polygon distribution, and a covering region/distance index was added for road totals. Tokyo statistics returned HTTP 200 in 0.6 s after the change. Shelter and history APIs also returned HTTP 200.
