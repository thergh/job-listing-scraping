# Job listings scraping

Scrapes filtered Just Join IT offers, analyses the exported JSON data, and generates a PDF report.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Scrape offers

Configure `jjit-scraper-config.json`.

```bash
python src/jjit_scraper.py
```

The scraper exports structured job postings to the configured output file in `data/`.

Example:

```text
data/jjit-java-mid.json
```

Exported fields include:

* `job_name`
* `salary`
* `required_skills`
* `type_of_contract`

## Analyse data

Configure `analysis-config.json`.

```bash
python src/analyzer.py
```

The analyser reads scraped job postings and generates aggregated JSON data.

Example output:

```text
res/jjit-java-mid-analysis.json
```

The analysis contains:

* total posting count
* salary coverage
* salary statistics
* job-title keyword frequencies
* skill and technology frequencies
* counts and percentages

## Generate PDF report

Configure `reporter-config.json`.

```bash
python src/reporter.py
```

Example output:

```text
res/jjit-java-mid-report.pdf
```

The PDF contains charts for:

* posting count and salary coverage
* most frequent skills and technologies
* most frequent job-title keywords
* salary ranges

## Custom config paths

Each script accepts an optional config path:

```bash
python src/jjit_scraper.py jjit-scraper-config.json
python src/analyzer.py analysis-config.json
python src/reporter.py reporter-config.json
```

## Full workflow

```bash
python src/jjit_scraper.py
python src/analyzer.py
python src/reporter.py
```
