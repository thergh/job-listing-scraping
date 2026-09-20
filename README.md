# Job listings scraping

Scrape filtered offers from Just Join IT or No Fluff Jobs, analyse them, retain
historical snapshots, and generate a PDF report.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m playwright install chromium
```

Make the workflow script executable:

```bash
chmod +x run.sh
```

## Full workflow

Run the default Just Join IT workflow:

```bash
./run.sh
```

Run the default No Fluff Jobs workflow:

```bash
./run.sh -s nfj
```

Run a custom, matched set of scraper, analysis, and report configs:

```bash
./run.sh -s jjit -c path/to/java-scraper.json -a path/to/java-analysis.json -r path/to/java-reporter.json
```

Override only the source URL while keeping the selected workflow's output paths:

```bash
./run.sh -u 'https://justjoin.it/job-offers/all-locations/java?experience-levels=mid'
```

`run.sh` always runs the selected scraper, then its matching analysis and
report config. When the analysis config declares `job_type`, it also generates
the matching history report. Use `./run.sh -h` to see all flags.

The workflow runs:

```bash
python3 src/<source>_scraper.py -c <scraper-config>
python3 src/analyzer.py <analysis-config>
python3 src/reporter.py <reporter-config>
```

## Scrape offers

Default config file:

```text
jjit-scraper-config.json
```

Run with the default config:

```bash
python3 src/jjit_scraper.py
```

Run with a custom config path:

```bash
python3 src/jjit_scraper.py -c path/to/custom-config.json
```

Run with the default config but override the URL:

```bash
python3 src/jjit_scraper.py -u 'https://justjoin.it/job-offers/all-locations/java?experience-levels=mid'
```

Use both flags together in any order:

```bash
python3 src/jjit_scraper.py -c path/to/custom-config.json -u 'https://justjoin.it/job-offers/all-locations/java?experience-levels=mid'
python3 src/jjit_scraper.py -u 'https://justjoin.it/job-offers/all-locations/java?experience-levels=mid' -c path/to/custom-config.json
```

The scraper writes structured job postings to the configured file in `data/`.

Exported fields include:

* `job_name`
* `salary`
* `required_skills`
* `type_of_contract`

The output also includes:

* `filtered_total_offers`
* `embedded_offers_total`
* `offers_count`

## Analyse data

```bash
python src/analyzer.py
```

Configuration:

```text
analysis-config.json
```

The analyser accepts either scraper JSON documents or JSON Lines exports. It
validates the input before calculating aggregates and carries source and
collection metadata into the analysis output.

Default example:

```text
res/analysis.json
```

The output contains:

* posting count
* salary coverage
* salary statistics
* job-title keyword frequencies
* skill and technology frequencies
* counts and percentages

Each analysis also appends a snapshot to `history/<job-type>.csv`. A row records
the scraper's UTC collection time, source, posting and salary coverage totals,
the top 25 skills, and salary statistics. Set `job_type` or `history_dir` in an
analysis config to override the inferred CSV name or destination. Relative
`history_dir` values are resolved from the repository root.

Backfill CSV history from reports already generated in `res/`:

```bash
python src/backfill_history.py
```

Generate a date-sorted trend report for one job type:

```bash
python src/history_reporter.py java-mid
python src/history_reporter.py cpp-mid --source 'Just Join IT'
```

The report charts posting count, salary coverage, and available PLN monthly
salary averages. Same-source snapshots from the same day are consolidated,
with scraper data preferred to PDF backfills.

## Generate PDF report

```bash
python src/reporter.py
```

Configuration:

```text
reporter-config.json
```

Default example:

```text
res/report.pdf
```

The PDF contains:

* posting and salary coverage charts
* skill and technology frequency charts
* job-title keyword charts
* salary range charts

## Custom config paths

```bash
python src/analyzer.py analysis-config.json
python src/reporter.py reporter-config.json
```
