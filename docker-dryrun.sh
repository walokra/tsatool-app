docker run --rm --name tsatool -p 8080:8080 \
  -v $(pwd)/analysis:/app/analysis \
  -v $(pwd)/results:/app/results \
  --network="tsatool-network" \
  --entrypoint '/bin/sh' \
  tsatool:latest -c 'python3 tsabatch.py -i example_data/toimiva.xlsx -n test_analysis --dryvalidate'
