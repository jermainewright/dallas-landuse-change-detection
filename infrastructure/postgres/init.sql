-- PostGIS and UUID extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Optimise for raster metadata queries
ALTER DATABASE landuse_db SET search_path TO public, postgis;
