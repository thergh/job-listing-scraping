# Job listings scraping

Scrape searches from Just Join IT and No Fluff Jobs, analyse each result set,
retain historical snapshots, and generate PDF reports.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
chmod +x run.sh
```

## Run the complete workflow

All searches and settings live in one universal config:

```bash
./run.sh
./run.sh -c path/to/jobs-config.json
```

The workflow runs the scraper, analyzer, reporter, and history reporter for
every configured search. Just Join IT and No Fluff Jobs URLs can coexist in the
same `listings` array.

## Configuration

The default file is [jobs-config.json](jobs-config.json). A minimal config is:

```json
{
  "format": "json",
  "delay_seconds": 0.1,
  "listings": [
    {
      "url": "https://justjoin.it/job-offers/all-locations/java?experience-levels=mid"
    },
    {
      "url": "https://nofluffjobs.com/pl/Python?criteria=seniority%3Djunior"
    }
  ]
}
```

Root fields are shared by all listings. A listing can override any shared
field. Entries are processed independently; if one scrape fails, the remaining
entries are still attempted and the scraper exits unsuccessfully afterward.

The application infers source, technology, seniority, and output paths from
each URL:

| Value | Example for a Just Join IT Java mid search |
| --- | --- |
| Scraped data | `data/jjit-java-mid.json` |
| Analysis | `res/analysis/jjit-java-mid.json` |
| PDF report | `res/reports/jjit-java-mid.pdf` |
| History snapshot | `res/history/snapshots/java-mid.csv` |
| History report | `res/history/reports/java-mid.pdf` |
| Report title | `Mid Java — Just Join IT` |

Optional entry overrides are:

- `data_output`
- `analysis_output`
- `report_output`
- `job_type`
- `report_title`

Scraper settings include `format` (`json` or `jsonl`), `delay_seconds`,
`max_idle_scrolls`, and `headful`. Reporter settings include `top_skills`, `top_title_keywords`,
`salary_currency`, `salary_units`, `include_methodology`, `exclude_skills`, and
`exclude_title_keywords`.

Output paths must be distinct after inference or overrides are applied.

## Run individual stages

Each stage consumes the same universal config:

```bash
python3 src/scraper.py -c jobs-config.json
python3 src/analyzer.py jobs-config.json
python3 src/reporter.py jobs-config.json
```

Generated artifacts are grouped by type:

```text
res/
├── analysis/   # analysis JSON
├── reports/    # per-search PDF reports
├── history/
│   ├── snapshots/  # historical CSV data
│   └── reports/    # historical trend PDFs
├── notes/      # report notes
└── configs/    # archived report-specific configs
```

The scraper exports `job_name`, `salary`, `required_skills`, and
`type_of_contract`, plus collection metadata. The analyzer calculates posting
counts, salary coverage and statistics, title keywords, and skill frequencies.
The reporter turns each analysis into a PDF.

## History

Every analysis appends a snapshot to
`res/history/snapshots/<job-type>.csv`. Generate a date-sorted trend report
manually with:

```bash
python3 src/history_reporter.py java-mid
python3 src/history_reporter.py cpp-mid --source 'Just Join IT'
```

Backfill CSV history from reports in `res/reports/` with:

```bash
python3 src/backfill_history.py
```
