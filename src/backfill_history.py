#!/usr/bin/env python3
"""Extract historical snapshots from generated PDF reports into CSV files."""

from __future__ import annotations

import argparse
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from history_csv import append_row


def pdf_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", str(path), "-"], check=True, text=True, capture_output=True
    ).stdout


def pdf_created_at(path: Path) -> str:
    output = subprocess.run(
        ["pdfinfo", str(path)], check=True, text=True, capture_output=True
    ).stdout
    match = re.search(r"^CreationDate:\s+(.+)$", output, re.MULTILINE)
    if not match:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
    created = datetime.strptime(match.group(1), "%a %b %d %H:%M:%S %Y %Z")
    return created.astimezone().astimezone(UTC).isoformat()


def metadata(path: Path, title: str) -> tuple[str, str]:
    name = path.stem.casefold()
    source = "Unknown (legacy PDF)"
    if "nofluff" in name or "no fluff jobs" in title.casefold():
        source = "No Fluff Jobs"
    elif "jjit" in name or "just join it" in title.casefold():
        source = "Just Join IT"
    role = re.search(r"(java|c\+\+|cpp|python|dotnet|\.net)[ -]+(junior|mid|senior)", name)
    if role:
        technology = role.group(1).replace("c++", "cpp").replace(".net", "dotnet")
        return source, f"{technology}-{role.group(2)}"
    if name == "report":
        return source, "cpp-mid"
    return source, name.replace("-report", "")


def top_skills(text: str) -> list[dict]:
    sections = text.split("Most requested skills and technologies", 1)
    if len(sections) == 1:
        return []
    page = sections[1].split("\f", 1)[0]
    names, values = [], []
    for line in (line.strip() for line in page.splitlines()):
        match = re.fullmatch(r"(\d+) \(([\d.]+)%\)", line)
        if match:
            values.append({"count": int(match.group(1)), "percentage": float(match.group(2))})
        elif line and not re.fullmatch(r"[\d ]+|Postings", line):
            names.append(line)
    return [dict(keyword=name, **value) for name, value in zip(names, values)]


def parse_pdf(path: Path) -> dict:
    text = pdf_text(path)
    title = next(line.strip() for line in text.splitlines() if line.strip())
    overview = text.split("\f", 1)[0].splitlines()

    def preceding_number(label: str) -> int | None:
        index = next((i for i, line in enumerate(overview) if line.strip() == label), None)
        if index is None:
            return None
        for line in reversed(overview[:index]):
            match = re.fullmatch(r"\s*(\d+)\s*", line)
            if match:
                return int(match.group(1))
        return None

    total = preceding_number("POSTINGS")
    paid = preceding_number("WITH SALARY")
    if total is None or paid is None:
        raise ValueError("overview metrics are missing")
    source, job_type = metadata(path, title)
    return {
        "gathered_at_utc": pdf_created_at(path),
        "source": source,
        "job_type": job_type,
        "postings_total": total,
        "postings_with_salary": paid,
        "salary_coverage_percentage": round(paid / total * 100, 2) if total else 0,
        "top_skills": __import__("json").dumps(top_skills(text), ensure_ascii=False),
        "salary_statistics": "[]",
        "origin": "retroactive_pdf",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports-dir", default="res")
    parser.add_argument("--history-dir", default="history")
    args = parser.parse_args()
    for report in sorted(Path(args.reports_dir).glob("*.pdf")):
        try:
            row = parse_pdf(report)
            destination = Path(args.history_dir) / f"{row['job_type']}.csv"
            status = "added" if append_row(destination, row) else "already present"
            print(f"{report.name}: {status} -> {destination}")
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            print(f"{report.name}: skipped ({exc})")


if __name__ == "__main__":
    main()
