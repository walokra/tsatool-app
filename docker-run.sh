docker run --rm --name tsatool -p 8080:8080 \
  -e PG_HOST=timescaledb \
  -e PG_PASSWORD=postgres \
  -e PG_USER=tsadash \
  -v $(pwd)/analysis:/app/analysis \
  -v $(pwd)/results:/app/results \
  -v $(pwd)/tsa:/app/tsa \
  --network="tsatool-network" \
  --entrypoint '/bin/sh' \
  tsatool:latest -c 'python3 tsabatch.py -i analysis/porvootest.xlsx -n porvootest --dryvalidate && \
  python3 tsabatch.py -i analysis/porvootest.xlsx -n porvootest'
