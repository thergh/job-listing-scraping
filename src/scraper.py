#!/usr/bin/env python3
"""Scrape every job search in the universal jobs configuration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

import jjit_scraper
import nfj_scraper
from config_entries import load_config_entries, require_unique_values
from workflow_config import data_output_for, source_slug_for


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape all Just Join IT and No Fluff Jobs searches in one config."
    )
    parser.add_argument(
        "-c",
        "--config",
        default="jobs-config.json",
        help="Path to the universal jobs config. Default: jobs-config.json",
    )
    return parser.parse_args()


def resolved_entries(config_path: Path) -> list[dict]:
    config_directory = config_path.resolve().parent
    entries = []
    for entry in load_config_entries(config_path):
        output_path = Path(data_output_for(entry))
        if not output_path.is_absolute():
            output_path = config_directory / output_path
        entries.append({**entry, "data_output": str(output_path)})
    require_unique_values(entries, "data_output")
    return entries


def process_entry(entry: dict) -> None:
    raw_config = {**entry, "output": entry["data_output"]}
    source = source_slug_for(entry)
    if source == "jjit":
        jjit_scraper.process_config(jjit_scraper.parse_config(raw_config))
    elif source == "nfj":
        nfj_scraper.process_config(nfj_scraper.parse_config(raw_config))
    else:  # source_slug_for validates this; keep dispatch exhaustive.
        raise ValueError(f"Unsupported source: {source}")


def main() -> int:
    args = parse_args()
    try:
        entries = resolved_entries(Path(args.config))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    failures = 0
    for index, entry in enumerate(entries, start=1):
        try:
            process_entry(entry)
        except (
            requests.RequestException,
            jjit_scraper.ScrapeError,
            nfj_scraper.ScrapeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            failures += 1
            print(f"error: listing {index}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
