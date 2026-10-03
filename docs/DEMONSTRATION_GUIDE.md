# Five-minute demonstration

1. Start WAYOUT and open the homepage. Explain that this is educational decision support, built with Python and MySQL.
2. Open the risk map and choose eastern Tokyo. Press **Load a demonstration**. The input points are real OSM junctions; the destination is explicitly a simulation.
3. Read the shortest and risk-adjusted distances, model index, terrain index and coverage. Explain why a small numeric difference is not proof of real-world safety.
4. Expand **Select a route road for simulation**, choose a road, then apply **Blocked** in the simulation lab. The app recalculates both objectives using the same exclusion. A no-route response is valid if the graph disconnects.
5. Clear simulated conditions. Show the source-backed destination list: historical designation and present operational status are separate facts.
6. Open **Our data**, then **Methodology**. Show a source URL, its year and transformation rule.
7. Open the dashboard to show stored route history. In the code, show `db.py`, the SQL schema, and `routing/dijkstra.py`.
8. Conclude by showing Kochi's evidence limitation: unresolved raw flood units mean footprint-only scoring. The system reports what it cannot establish.

If the database is unavailable, use the launcher or README; do not present a screenshot as a live result. If internet tiles are unavailable, enable the local road layer. Never claim the prototype is ready for real evacuation instructions.
