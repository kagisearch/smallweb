# Maintenance

The scripts in this directory are used for maintenance. Be sure to read and understand them before executing.

## Usage

### Execute [`crawl.sh`](crawl.sh)

This will crawl _all entries_ from [`smallweb.txt`](../smallweb.txt) via curl. Note that this can take a very long time! The results of this expensive operation will be written to `crawl-result.csv`. All further processing will use the results from this file and be much cheaper.

### Execute [`process.sh`](process.sh)

This will run several cleanup steps. The script will pause between each step to give you time to assess the results, commit changes and make adjustments.
