#!/usr/bin/env bash
set -e

python src/jjit_scraper.py
python src/analyzer.py
python src/reporter.py