"""Append analysis snapshots to role-specific historical CSV files."""

from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


FIELDS = [
    "gathered_at_utc",
    "source",
    "job_type",
    "postings_total",
    "postings_with_salary",
    "salary_coverage_percentage",
    "top_skills",
    "salary_statistics",
    "origin",
]


def source_name(source_url: str | None) -> str:
    host = urlparse(source_url or "").netloc.casefold()
    if "justjoin.it" in host:
        return "Just Join IT"
    if "nofluffjobs.com" in host:
        return "No Fluff Jobs"
    return "Unknown"


def job_type_from_url(source_url: str | None, fallback: str = "unknown") -> str:
    parsed = urlparse(source_url or "")
    query = parse_qs(parsed.query)
    category = ""
    path_parts = [part for part in parsed.path.split("/") if part]
    if "job-offers" in path_parts and path_parts:
        category = path_parts[-1]
    elif path_parts:
        category = path_parts[-1]
    category = unquote(category).casefold()
    aliases = {"c": "cpp", "c++": "cpp", "net": "dotnet"}
    category = aliases.get(category, category)
    level = (query.get("experience-levels") or [""])[0]
    if not level:
        criteria = (query.get("criteria") or [""])[0]
        level_match = re.search(r"seniority=([^&]+)", criteria)
        level = level_match.group(1) if level_match else ""
    return "-".join(part for part in (category, level.casefold()) if part) or fallback


def append_row(csv_path: Path, row: dict[str, str]) -> bool:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as file:
            existing = {
                (item["gathered_at_utc"], item["source"], item["job_type"], item["origin"])
                for item in csv.DictReader(file)
            }
    key = (row["gathered_at_utc"], row["source"], row["job_type"], row["origin"])
    if key in existing:
        return False
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return True


def append_analysis_snapshot(
    analysis: dict,
    source_document: dict,
    history_dir: Path,
    job_type: str | None = None,
) -> Path:
    source_url = analysis.get("source_url")
    job_type = job_type or job_type_from_url(source_url, Path(analysis["source"]).stem)
    gathered_at = source_document.get("scraped_at_utc") or datetime.now(UTC).isoformat()
    row = {
        "gathered_at_utc": gathered_at,
        "source": source_name(source_url),
        "job_type": job_type,
        "postings_total": analysis["postings_total"],
        "postings_with_salary": analysis["postings_with_salary"],
        "salary_coverage_percentage": analysis["salary_coverage_percentage"],
        "top_skills": json.dumps(analysis.get("skill_keywords", [])[:25], ensure_ascii=False),
        "salary_statistics": json.dumps(analysis.get("salary_statistics", []), ensure_ascii=False),
        "origin": "scraper",
    }
    csv_path = history_dir / f"{job_type}.csv"
    append_row(csv_path, row)
    return csv_path
