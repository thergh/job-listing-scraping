"""Derive analysis and reporting work from scraper configuration entries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config_entries import load_config_entries
from history_csv import job_type_from_url, source_name


def source_slug_for(entry: dict[str, Any]) -> str:
    """Return the supported source slug inferred from a listing URL."""
    source = source_name(str(entry.get("url", "")))
    if source == "Just Join IT":
        return "jjit"
    if source == "No Fluff Jobs":
        return "nfj"
    raise ValueError(f"Unsupported job listing URL: {entry.get('url', '')}")


def data_output_for(entry: dict[str, Any]) -> str:
    """Return an explicit data path or derive one from source and job type."""
    output_format = str(entry.get("format", "json")).casefold()
    if output_format not in {"json", "jsonl"}:
        raise ValueError(
            "Universal workflow field `format` must be `json` or `jsonl` "
            "so the scraped data can be analyzed."
        )
    if entry.get("data_output"):
        output = str(entry["data_output"])
        if Path(output).suffix.casefold() != f".{output_format}":
            raise ValueError(
                f"Data output `{output}` must use the .{output_format} extension."
            )
        return output
    return str(
        Path("data")
        / f"{source_slug_for(entry)}-{job_type_for(entry)}.{output_format}"
    )


def analysis_output_for(entry: dict[str, Any]) -> str:
    """Return an explicit analysis path or derive one from scraped data output."""
    if entry.get("analysis_output"):
        return str(entry["analysis_output"])
    stem = Path(data_output_for(entry)).stem
    return str(Path("res") / "analysis" / f"{stem}.json")


def report_output_for(entry: dict[str, Any]) -> str:
    """Return an explicit report path or derive one from scraped data output."""
    if entry.get("report_output"):
        return str(entry["report_output"])
    stem = Path(data_output_for(entry)).stem
    return str(Path("res") / "reports" / f"{stem}.pdf")


def job_type_for(entry: dict[str, Any]) -> str:
    """Return an explicit job type or infer it from the listing URL."""
    return str(
        entry.get("job_type")
        or job_type_from_url(
            str(entry.get("url", "")),
            "unknown",
        )
    )


def report_title_for(entry: dict[str, Any]) -> str:
    """Build a readable title such as ``Mid Java — Just Join IT``."""
    if entry.get("report_title"):
        return str(entry["report_title"])

    job_type = job_type_for(entry)
    parts = job_type.rsplit("-", 1)
    technology = parts[0]
    seniority = parts[1] if len(parts) == 2 else ""
    technology_label = {"cpp": "C++", "dotnet": ".NET"}.get(
        technology.casefold(), technology.replace("-", " ").title()
    )
    role = " ".join(part for part in (seniority.title(), technology_label) if part)
    source = source_name(str(entry.get("url", "")))
    return f"{role} — {source}" if source != "Unknown" else role


def load_analysis_entries(path: Path) -> list[dict[str, Any]]:
    """Derive every analysis job from the universal jobs config."""
    entries = load_config_entries(path)
    return [
        {
            **entry,
            "input": data_output_for(entry),
            "output": analysis_output_for(entry),
            "job_type": job_type_for(entry),
        }
        for entry in entries
    ]


def load_reporter_entries(path: Path) -> list[dict[str, Any]]:
    """Derive every report job from the universal jobs config."""
    entries = load_config_entries(path)
    return [
        {
            **entry,
            "input": analysis_output_for(entry),
            "output": report_output_for(entry),
            "title": report_title_for(entry),
        }
        for entry in entries
    ]
