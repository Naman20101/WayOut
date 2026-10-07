"""Rule-based route explainer. Deterministic, no external services.

Given a compare() result, produce plain-English guidance, a step summary,
and answers to common questions. Not an LLM — every sentence traces to
a number in the result payload.
"""

def _fmt_km(m):
    return f"{m/1000:.2f} km"

def _pct(a, b):
    if not b: return "0%"
    return f"{abs(a-b)/b*100:.1f}%"


def guide(region, has_origin, has_destination, origin_text, destination_text):
    """Step-by-step prompt shown before a route is calculated."""
    steps = []
    if not has_origin:
        steps.append({
            "state": "await-origin",
            "title": "Step 1 of 3",
            "body": "Click anywhere on the map to place your starting point A.",
            "hint": "Or search above, or use 'Use my location'.",
        })
    elif not has_destination:
        steps.append({
            "state": "await-destination",
            "title": "Step 2 of 3",
            "body": f"Starting point set at {origin_text}. Now click the map to place destination B.",
            "hint": "The destination is a SIMULATION point, not a verified shelter.",
        })
    else:
        steps.append({
            "state": "ready",
            "title": "Step 3 of 3",
            "body": "Both points are set. Click 'Compare routes' to see the two options.",
            "hint": "Shortest distance vs. risk-adjusted — same start and end.",
        })
    return {"region": region, "steps": steps}


def explain(result):
    """Turn a compare() result into a short readable summary + Q&A."""
    short = result["shortest"]
    rec = result["recommended"]
    region = result["region"]
    mode = result["mode"]
    terrain = rec.get("terrain_index") or 0
    coverage = rec.get("coverage") or 0
    same_route = (abs(short["distance_m"] - rec["distance_m"]) < 1
                  and short.get("coordinates") == rec.get("coordinates"))

    if same_route:
        headline = (f"Both objectives chose the same route. It covers "
                    f"{_fmt_km(rec['distance_m'])} at a model index of "
                    f"{rec['risk_index']}/100.")
    else:
        extra = rec["distance_m"] - short["distance_m"]
        headline = (f"The risk-adjusted route is {_fmt_km(rec['distance_m'])} — "
                    f"{_pct(rec['distance_m'], short['distance_m'])} "
                    f"{'longer' if extra > 0 else 'shorter'} than the shortest — "
                    f"at a model index of {rec['risk_index']}/100 "
                    f"vs {short['risk_index']}/100.")

    bullets = []
    bullets.append(f"Travel mode: {mode}. Region: {region}.")
    if terrain > 0:
        bullets.append(f"NASA SRTM terrain contributed +{terrain} to the "
                       f"recommended index (elevation band and slope, additive).")
    if coverage < 1:
        bullets.append(f"Only {coverage*100:.0f}% of the recommended route length "
                       f"has primary hazard data. The unknown portions carry a "
                       f"100/100 planning penalty, not a measured hazard value.")
    else:
        bullets.append("Every metre of the recommended route has primary hazard data.")

    # Collapse consecutive unnamed segments.
    waypoints = []
    prev_name = None
    accumulated = 0.0
    for w in rec.get("ways", []):
        name = w.get("name") or "Unnamed road"
        length = w.get("length_m") or 0
        if name == prev_name:
            accumulated += length
            continue
        if prev_name is not None:
            waypoints.append({"name": prev_name, "length_m": accumulated})
        prev_name = name
        accumulated = length
    if prev_name is not None:
        waypoints.append({"name": prev_name, "length_m": accumulated})
    waypoints.sort(key=lambda x: -x["length_m"])
    waypoints = waypoints[:8]

    return {
        "headline": headline,
        "bullets": bullets,
        "directions": waypoints,
        "same_route": same_route,
    }


def answer(question, result):
    """Preset Q&A. Each answer is grounded in the result payload."""
    q = (question or "").strip().lower()
    if not result:
        return "Calculate a route first, then I can explain it."

    short = result["shortest"]
    rec = result["recommended"]
    coverage = rec.get("coverage") or 0
    terrain = rec.get("terrain_index") or 0
    same = (abs(short["distance_m"] - rec["distance_m"]) < 1
            and short.get("coordinates") == rec.get("coordinates"))
    region = result.get("region", "")

    if "why" in q and ("safer" in q or "risk" in q or "low" in q):
        if same:
            return ("The two objectives chose the same route. With the current "
                    "data, the risk-adjusted objective cannot find a lower-cost "
                    "alternative — every available path has the same effective penalty.")
        return (f"The risk-adjusted route costs less under the stated model. "
                f"Its index is {rec['risk_index']}/100 vs {short['risk_index']}/100. "
                f"The trade-off is {_pct(rec['distance_m'], short['distance_m'])} "
                f"extra distance. Whether that's worth it depends on how you weigh "
                f"a few hundred metres against the modelled exposure.")

    if "coverage" in q or "unknown" in q:
        return (f"Coverage means the fraction of the route length where the source "
                f"hazard actually has data. Here it's {coverage*100:.0f}%. The model "
                f"applies a 100-point penalty on uncovered stretches — a planning "
                f"preference, not a measured hazard. Blank areas on the map are "
                f"unknown, not safe.")

    if "terrain" in q or "srtm" in q or "elevation" in q or "slope" in q:
        if terrain == 0:
            return ("No terrain contribution is applied to this route. That usually "
                    "means the SRTM samples were flat enough to score zero, or "
                    "terrain is not yet wired for this region.")
        return (f"NASA SRTM adds {terrain} points to the recommended index. It "
                f"combines a region-banded elevation indicator (relative low-lying) "
                f"and a slope indicator (0 below 2°, 100 above 15°). It is a "
                f"relative-terrain signal, not a flood depth.")

    if "flood" in q or "river" in q:
        if region.startswith("custom_"):
            return ("This custom area uses the JRC Global River Flood Hazard Map "
                    "(50-year return period) sampled as depth in metres. The score "
                    "is a planning index, not a forecast. It does not reflect "
                    "real-time rainfall or reservoir release.")
        return ("For fixed study regions, the flood score comes from a jurisdiction "
                "dataset: KSDMA for Kochi, USGS ShakeMap for Kathmandu, TMG for Tokyo. "
                "Each has its own unit convention — see the methodology page.")

    if "landslide" in q:
        if region.startswith("custom_"):
            return ("Landslide risk uses the NASA SEDAC Global Landslide Hazard "
                    "Distribution, class 1 to 10, rescaled to 0–100. It is a "
                    "long-term susceptibility indicator, not a rainfall-triggered "
                    "warning.")
        return ("Landslide scoring applies to custom global regions only. The three "
                "fixed study regions use their own primary hazards.")

    if "shelter" in q or "destination" in q:
        return ("Shelters shown for custom regions come from OpenStreetMap tags "
                "(amenity=shelter, emergency=shelter, social_facility=shelter). "
                "They are candidates, not officially verified emergency "
                "designations. Opening, capacity and entrance have not been "
                "checked against any municipal register.")

    if "same" in q or "identical" in q:
        if same:
            return ("Yes — both objectives selected the same path.")
        return ("No — they differ. The recommended route is longer but has a "
                "lower model index under the stated weights.")

    if "safe" in q:
        return ("The system cannot certify safety. Indices are relative model "
                "outputs, not probabilities. During an emergency, follow official "
                "instructions.")

    if "distance" in q:
        return (f"Shortest: {_fmt_km(short['distance_m'])}. "
                f"Risk-adjusted: {_fmt_km(rec['distance_m'])}.")

    if "direction" in q or "turn" in q or "street" in q or "road" in q:
        return ("See the Directions list above. It summarises the longest segments "
                "of the recommended route. It is not turn-by-turn guidance.")

    return ("I can explain: why the risk route was chosen, what coverage means, "
            "how NASA SRTM terrain contributes, how flood or landslide scoring "
            "works, whether both routes are identical, and the distances involved.")