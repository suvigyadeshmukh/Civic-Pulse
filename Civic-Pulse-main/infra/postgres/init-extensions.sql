-- Civic Pulse — Digital Governance & Public Information
-- PostgreSQL Extension Initialization Script
-- Mounted into /docker-entrypoint-initdb.d/01-init-extensions.sql for automated bootstrap

-- Enable UUID generation support
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable cryptographic functions (e.g. hashing, digest, encryption)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable pgvector for embedding storage and similarity search (Policy Explainer RAG & Fact Verification)
CREATE EXTENSION IF NOT EXISTS "vector";

-- Enable PostGIS for geospatial queries, location-based triage, and grievance deduplication
CREATE EXTENSION IF NOT EXISTS "postgis";

