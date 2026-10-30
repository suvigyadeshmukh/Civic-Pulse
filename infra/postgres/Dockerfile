# Civic Pulse — PostgreSQL 16 with PostGIS 3.4 and pgvector
FROM postgis/postgis:16-3.4

LABEL maintainer="Civic Pulse Core Team"
LABEL description="PostgreSQL 16 with PostGIS and pgvector extensions for Civic Pulse"

# Install postgresql-16-pgvector package from Debian/PostgreSQL repository
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-16-pgvector && \
    rm -rf /var/lib/apt/lists/*

