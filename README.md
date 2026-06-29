# Job listings scraping

Scrapes filtered Just Join IT offers, analyses the exported JSON data, and generates a PDF report.

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

Configure:

* `jjit-scraper-config.json`
* `analysis-config.json`
* `reporter-config.json`

Run the complete workflow:

```bash
./run.sh
```

The script runs:

```bash
python src/jjit_scraper.py
python src/analyzer.py
python src/reporter.py
```

## Scrape offers

```bash
python src/jjit_scraper.py
```

Configuration:

```text
jjit-scraper-config.json
```

The scraper writes structured job postings to the configured file in `data/`.

Default example:

```text
data/scraped.json
```

Exported fields include:

* `job_name`
* `salary`
* `required_skills`
* `type_of_contract`

## Analyse data

```bash
python src/analyzer.py
```

Configuration:

```text
analysis-config.json
```

The analyser reads scraped postings and generates aggregated JSON data.

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
python src/jjit_scraper.py jjit-scraper-config.json
python src/analyzer.py analysis-config.json
python src/reporter.py reporter-config.json
```
