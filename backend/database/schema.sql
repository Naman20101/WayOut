CREATE TABLE IF NOT EXISTS regions (
 id VARCHAR(20) PRIMARY KEY, name VARCHAR(100) NOT NULL,
 latitude DOUBLE NOT NULL, longitude DOUBLE NOT NULL, radius_m INT NOT NULL DEFAULT 15000,
 primary_hazard VARCHAR(20) NOT NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS data_sources (
 id VARCHAR(60) PRIMARY KEY, region_id VARCHAR(20), dataset_name VARCHAR(250) NOT NULL,
 organisation VARCHAR(200), url TEXT, accessed_at DATE, observation_year VARCHAR(80),
 coverage TEXT, variables_used TEXT, format VARCHAR(60), licence VARCHAR(200),
 official BOOLEAN NOT NULL DEFAULT FALSE, status VARCHAR(60), preprocessing TEXT,
 sha256 CHAR(64), FOREIGN KEY(region_id) REFERENCES regions(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS road_nodes (
 region_id VARCHAR(20) NOT NULL, id BIGINT NOT NULL, latitude DOUBLE NOT NULL, longitude DOUBLE NOT NULL,
 PRIMARY KEY(region_id,id), FOREIGN KEY(region_id) REFERENCES regions(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS road_edges (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, region_id VARCHAR(20) NOT NULL,
 osm_way_id BIGINT NOT NULL, from_node BIGINT NOT NULL, to_node BIGINT NOT NULL,
 distance_m DOUBLE NOT NULL, name VARCHAR(250), highway VARCHAR(60),
 walk BOOLEAN NOT NULL, bicycle BOOLEAN NOT NULL, car BOOLEAN NOT NULL,
 oneway SMALLINT NOT NULL DEFAULT 0, tags JSON,
 FOREIGN KEY(region_id,from_node) REFERENCES road_nodes(region_id,id),
 FOREIGN KEY(region_id,to_node) REFERENCES road_nodes(region_id,id),
 INDEX(region_id), INDEX(region_id,distance_m), INDEX(osm_way_id), CHECK(distance_m>0)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS risk_scores (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, edge_id BIGINT NOT NULL, source_id VARCHAR(60) NOT NULL,
 hazard VARCHAR(40) NOT NULL, original_value DOUBLE, normalised_value DOUBLE,
 coverage_fraction DOUBLE NOT NULL DEFAULT 0, rule_version VARCHAR(100),
 FOREIGN KEY(edge_id) REFERENCES road_edges(id) ON DELETE CASCADE,
 FOREIGN KEY(source_id) REFERENCES data_sources(id), UNIQUE(edge_id,hazard),
 CHECK(normalised_value IS NULL OR normalised_value BETWEEN 0 AND 100),
 CHECK(coverage_fraction BETWEEN 0 AND 1)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS locations (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, region_id VARCHAR(20) NOT NULL,
 osm_id BIGINT, name VARCHAR(250) NOT NULL, kind VARCHAR(60), latitude DOUBLE NOT NULL,
 longitude DOUBLE NOT NULL, source_id VARCHAR(60),
 FOREIGN KEY(region_id) REFERENCES regions(id), FOREIGN KEY(source_id) REFERENCES data_sources(id),
 INDEX(region_id,name)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS shelters (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, region_id VARCHAR(20) NOT NULL, name VARCHAR(250) NOT NULL,
 kind VARCHAR(80), latitude DOUBLE NOT NULL, longitude DOUBLE NOT NULL,
 hazard VARCHAR(30) NOT NULL, verified_designation BOOLEAN NOT NULL DEFAULT FALSE,
 simulated BOOLEAN NOT NULL DEFAULT FALSE, capacity INT NULL, accessibility TEXT,
 operational_status VARCHAR(100) DEFAULT 'Current opening not verified', source_id VARCHAR(60),
 notes TEXT, FOREIGN KEY(region_id) REFERENCES regions(id), FOREIGN KEY(source_id) REFERENCES data_sources(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS hazard_history (
 id INT AUTO_INCREMENT PRIMARY KEY, region_id VARCHAR(20) NOT NULL, name VARCHAR(200),
 event_date DATE, description TEXT, source_id VARCHAR(60),
 FOREIGN KEY(region_id) REFERENCES regions(id), FOREIGN KEY(source_id) REFERENCES data_sources(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS hazard_zones (
 id INT AUTO_INCREMENT PRIMARY KEY, region_id VARCHAR(20), hazard VARCHAR(40),
 original_value VARCHAR(100), normalised_value DOUBLE, geometry_json JSON,
 source_id VARCHAR(60), FOREIGN KEY(region_id) REFERENCES regions(id), FOREIGN KEY(source_id) REFERENCES data_sources(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS buildings (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, region_id VARCHAR(20), source_id VARCHAR(60),
 geometry_json JSON, material VARCHAR(100), age_years INT NULL,
 FOREIGN KEY(region_id) REFERENCES regions(id), FOREIGN KEY(source_id) REFERENCES data_sources(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS structural_risk (
 building_id BIGINT PRIMARY KEY, original_value VARCHAR(100), score DOUBLE NULL,
 rule_version VARCHAR(100), FOREIGN KEY(building_id) REFERENCES buildings(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS route_history (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 session_id VARCHAR(80) NOT NULL, region_id VARCHAR(20) NOT NULL, mode VARCHAR(20), hazard VARCHAR(20),
 simulated BOOLEAN NOT NULL, shortest_distance_m DOUBLE, recommended_distance_m DOUBLE,
 observed_risk DOUBLE NULL, coverage_fraction DOUBLE, result_summary JSON,
 FOREIGN KEY(region_id) REFERENCES regions(id), INDEX(session_id,created_at)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS admin_simulations (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, session_id VARCHAR(80) NOT NULL, region_id VARCHAR(20) NOT NULL,
 osm_way_id BIGINT NOT NULL, condition_name VARCHAR(30) NOT NULL,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(region_id) REFERENCES regions(id), UNIQUE(session_id,region_id,osm_way_id)
) ENGINE=InnoDB;
