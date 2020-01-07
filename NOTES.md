
# Notes

## Run analysis locally

use virtualenv

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

$ docker network create tsatool-network
$ docker-compose up timescaledb
$ time PG_PASSWORD=postgres PG_USER=tsadash python tsabatch.py -i example_data/toimiva.xlsx -n test_analysis

## Populate database from raw Lotju-data

Get data from <https://tiesaahistoria-jakelu.s3.amazonaws.com/index.html>

Add data to e.g:

1. ./database/data/anturi_arvo-2018_03.csv
1. ./database/data/tiesaa_mittatieto-2018_03.csv

which are mounted inside Docker for later use.

Start timescaledb with `docker-compose up timescaledb`

Run psql with following procedure to insert data:

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
        -c  "BEGIN; \
            COPY tiesaa_mittatieto FROM '/rawdata/tiesaa_mittatieto-2018_03.csv' CSV HEADER DELIMITER '|'; \
            CALL populate_statobs(); \
            TRUNCATE TABLE tiesaa_mittatieto; \
            COPY anturi_arvo FROM '/rawdata/anturi_arvo-2018_03.csv' CSV HEADER DELIMITER '|'; \
            CALL populate_seobs(); \
            TRUNCATE TABLE anturi_arvo; \
            COMMIT;"

This takes a lot of time and space.
For example importing data from 2018_03 (6 GB + 200 MB) import takes 53 to 65 minutes and resulting database is 35 GB.
Note that truncating tiesaa_mittatieto and anturi_arvo might not happen during the copy procedure and you might need to do it afterwards.

    SELECT pg_size_pretty( pg_database_size('tsa') );

    SELECT pg_size_pretty( pg_total_relation_size('stations') );
    SELECT pg_size_pretty( pg_total_relation_size('sensors') );
    SELECT pg_size_pretty( pg_total_relation_size('seobs') );
    SELECT pg_size_pretty( pg_total_relation_size('statobs') );
    SELECT pg_size_pretty( pg_total_relation_size('anturi_arvo') );
    SELECT pg_size_pretty( pg_total_relation_size('tiesaa_mittatieto') );

## Migrating data from CSV

See: <https://docs.timescale.com/latest/getting-started/migrating-data>.

Note: You could be using pigz (multithreaded gzip) instead of gzip for faster compression. Usually gzip is the bottlneck.

1. Start TimescaleDB with docker-compose

    docker-compose up timescaledb

1. Backup data to comma-separated values (CSV) from following tables.

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
            -c  "\COPY (SELECT * FROM sensors) TO processed/sensors_2018-03.csv DELIMITER ',' CSV"

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
            -c  "\COPY (SELECT * FROM stations) TO processed/stations_2018-03.csv DELIMITER ',' CSV"

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
            -c  "\COPY seobs TO program 'gzip > processed/seobs_2018-03.csv.gz' DELIMITER ',' CSV"

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
            -c  "\COPY statobs TO program 'gzip > processed/statobs_2018-03.csv.gz' DELIMITER ',' CSV"

1. Import the data into new TimescaleDB.

Use timescaledb-parallel-copy:

    go get github.com/timescale/timescaledb-parallel-copy/cmd/timescaledb-parallel-copy

Import CSV:

    PGPASSWORD=postgres ~/go/bin/timescaledb-parallel-copy --connection "host=localhost user=tsadash sslmode=disable" --db-name tsa --table sensors \
        --file processed/sensors.csv --workers 4 --copy-options "CSV" --reporting-period 30s

    PGPASSWORD=postgres ~/go/bin/timescaledb-parallel-copy --connection "host=localhost user=tsadash sslmode=disable" --db-name tsa --table stations \
        --file processed/stations.csv --workers 4 --copy-options "CSV" --reporting-period 30s

    cat processed/seobs.csv.gz | \
        gunzip | ~/go/bin/timescaledb-parallel-copy --connection "host=localhost user=tsadash password=postgres sslmode=disable" --db-name tsa --table seobs \
            --verbose --workers 4 --copy-options "CSV" --reporting-period 30s

    cat processed/statobs.csv.gz | \
        gunzip | ~/go/bin/timescaledb-parallel-copy --connection "host=localhost user=tsadash password=postgres sslmode=disable" --db-name tsa --table statobs \
            --verbose --workers 4 --copy-options "CSV" --reporting-period 30s

OR using psql COPY:

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
        -c "\COPY sensors FROM 'processed/sensors.csv' CSV;"

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
        -c "\COPY stations FROM 'processed/stations.csv' CSV";

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
        -c "\COPY seobs FROM program 'zcat processed/seobs.csv.gz' CSV";

    time PGPASSWORD=postgres psql -h localhost -p 5432 -d tsa -U tsadash \
        -c "\COPY statobs FROM program 'zcat processed/statobs.csv.gz' CSV";

### Notes on migrating

For example CSV 2018-03 dumps from database:

    seobs.csv
    COPY 211711191
    real	7m0.305s
    11G
    Gzipped 1,3G

    statobs.csv
    COPY 4796787
    real	0m9.566s
    312M
    Gzipped 33M

Restoring with psql:

    seobs.csv
    COPY 211711191
    real	38m19.651s

Restoring with timescaledb-parallel-copy from gzipped CSV:

    seobs.csv.gz
    COPY 211711191, took 20m36.066938533s with 4 worker(s) (mean rate 171278.095385/sec)

## Migrating data from database backup

## Create db dump

Dump the whole database and e.g. the 2018_03 data takes around 9 minutes and produces datafile of 2 GB.

    time PGPASSWORD=postgres pg_dump -h localhost -p 5432 -U tsadash -Fc -f tsa_2018_03.bak tsa

### Restore backup

Comment out following lines from docker-compose.yml

- ./database/01_init_db.sql:/docker-entrypoint-initdb.d/01_init_db.sql
- ./database/02_rawdata_schema.sql:/docker-entrypoint-initdb.d/02_rawdata_schema.sql
- ./database/03_insert_stations_sensors.sql:/docker-entrypoint-initdb.d/03_insert_stations_sensors.sql

See: <https://docs.timescale.com/latest/using-timescaledb/backup>

Restoring data from a backup currently requires some additional procedures, which need to be run from psql:

    PGPASSWORD=postgres psql -h localhost -p 5432 -U tsadash
    CREATE DATABASE tsa;
    \connect tsa;
    CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
    CREATE EXTENSION IF NOT EXISTS btree_gist CASCADE;

    SELECT timescaledb_pre_restore();

    time PGPASSWORD=postgres pg_restore -h localhost -p 5432 -U tsadash -Fc -d tsa tsa_2018_03.bak

    SELECT timescaledb_post_restore();

Restoring a database dump of 2018_03 takes about 18 minutes.
