-- Read summaries from actual imported data.
SELECT region_id, COUNT(*) AS road_segments, ROUND(SUM(distance_m)/1000,2) AS km
FROM road_edges GROUP BY region_id;
SELECT e.region_id, rs.hazard, AVG(rs.normalised_value) AS observed_mean,
AVG(rs.coverage_fraction) AS mean_coverage
FROM risk_scores rs JOIN road_edges e ON e.id=rs.edge_id GROUP BY e.region_id,rs.hazard;
SELECT sh.name, sh.operational_status, s.organisation, s.url
FROM shelters sh JOIN data_sources s ON s.id=sh.source_id WHERE sh.region_id='tokyo';

-- CRUD demonstration only: rolled back so no classroom test record persists.
START TRANSACTION;
INSERT INTO admin_simulations(session_id,region_id,osm_way_id,condition_name)
SELECT 'viva-transaction-demo','kochi',osm_way_id,'Blocked' FROM road_edges WHERE region_id='kochi' LIMIT 1;
SELECT * FROM admin_simulations WHERE session_id='viva-transaction-demo';
UPDATE admin_simulations SET condition_name='Unsafe' WHERE session_id='viva-transaction-demo';
DELETE FROM admin_simulations WHERE session_id='viva-transaction-demo';
ROLLBACK;
