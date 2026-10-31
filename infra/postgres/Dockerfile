# Civic Pulse — PostgreSQL 16 with PostGIS 3.5 and pgvector
FROM postgis/postgis:16-3.5

LABEL maintainer="Civic Pulse Core Team"
LABEL description="PostgreSQL 16 with PostGIS and pgvector extensions for Civic Pulse"

# NOTE: despite the version name, postgis/postgis:16-3.5 is published on
# Debian 11 (bullseye) — there is no bookworm variant of this tag. The live
# PGDG mirror no longer serves the bullseye-pgdg suite (HTTP 404), so retarget
# the image's existing PGDG source at PostgreSQL's official archive before
# installing the PostgreSQL 16-compatible pgvector package.
RUN sed -i \
        's|http://apt.postgresql.org/pub/repos/apt/|https://apt-archive.postgresql.org/pub/repos/apt/|' \
        /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends postgresql-16-pgvector && \
    rm -rf /var/lib/apt/lists/*
