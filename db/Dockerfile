# AurasVision DB — PostgreSQL 16 + pgvector + TimescaleDB
# Taban: pgvector resmi imajı (Debian, multi-arch: amd64 + arm64 → GB10/DGX Spark uyumlu).
# Üzerine Timescale'in resmi Debian paketi eklenir.
# Timescale kurulumu sorun çıkarırsa: FROM satırı tek başına da yeter —
# schema.sql timescale yoksa düz tabloya düşer (DO blokları).
FROM pgvector/pgvector:pg16

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg lsb-release \
 && curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey \
      | gpg --dearmor -o /usr/share/keyrings/timescaledb.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -cs) main" \
      > /etc/apt/sources.list.d/timescaledb.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends timescaledb-2-postgresql-16 \
 && apt-get purge -y gnupg lsb-release && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

RUN echo "shared_preload_libraries = 'timescaledb'" >> /usr/share/postgresql/postgresql.conf.sample
