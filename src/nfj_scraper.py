#!/usr/bin/env python3
"""Scrape No Fluff Jobs offer lists into database-friendly files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
class ScrapeError(RuntimeError):
    """Raised when the page structure cannot be parsed reliably."""


@dataclass
class ScraperConfig:
    url: str
    output: str = "data/offers.json"
    format: str | None = None
    delay_seconds: float = 0.1
    max_idle_scrolls: int = 10
    headful: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape a filtered No Fluff Jobs offers page from a JSON config file."
    )
    parser.add_argument(
        "-c",
        "--config",
        default="nfj-scraper-config.json",
        help="Path to scraper config JSON. Default: nfj-scraper-config.json",
    )
    parser.add_argument(
        "-u",
        "--url",
        help="Override the URL from the config file.",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> ScraperConfig:
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScrapeError(
            f"Config file not found: {config_path}. Create it from nfj-scraper-config.json."
        ) from exc

    if not isinstance(raw_config, dict):
        raise ScrapeError("Config file must contain a JSON object.")

    url = raw_config.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ScrapeError("Config field `url` is required and must be a non-empty string.")

    fmt = raw_config.get("format")
    if fmt is not None and fmt not in {"json", "jsonl", "md"}:
        raise ScrapeError("Config field `format` must be one of: json, jsonl, md.")

    return ScraperConfig(
        url=url.strip(),
        output=str(raw_config.get("output", "data/offers.json")),
        format=fmt,
        delay_seconds=float(raw_config.get("delay_seconds", 0.1)),
        max_idle_scrolls=int(raw_config.get("max_idle_scrolls", 10)),
        headful=bool(raw_config.get("headful", False)),
    )


def apply_cli_overrides(config: ScraperConfig, args: argparse.Namespace) -> ScraperConfig:
    return ScraperConfig(
        url=args.url.strip() if isinstance(args.url, str) and args.url.strip() else config.url,
        output=config.output,
        format=config.format,
        delay_seconds=config.delay_seconds,
        max_idle_scrolls=config.max_idle_scrolls,
        headful=config.headful,
    )


def infer_format(output_path: Path, explicit_format: str | None) -> str:
    if explicit_format:
        return explicit_format
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in {"json", "jsonl", "md"}:
        return suffix
    return "json"


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in {"nofluffjobs.com", "www.nofluffjobs.com"}:
        raise ScrapeError("Please pass a No Fluff Jobs offers URL from nofluffjobs.com.")


def scrape_offers(url: str, delay_seconds: float) -> tuple[list[dict[str, Any]], int]:
    """Read exact search matches from the site's server-rendered search state."""
    import time
    from urllib.parse import parse_qsl, urlencode, urlunparse
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    parsed_url = urlparse(url)
    query = dict(parse_qsl(parsed_url.query))
    offers_by_id = {}
    page_number = 1
    expected = None
    while True:
        page_query = {**query, "page": str(page_number)}
        page_url = urlunparse(parsed_url._replace(query=urlencode(page_query)))
        try:
            response = session.get(page_url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ScrapeError(f"Could not fetch search page {page_number}: {exc}") from exc
        match = re.search(
            r'<script[^>]*id="serverApp-state"[^>]*>(.*?)</script>',
            response.text, re.DOTALL,
        )
        if match is None:
            raise ScrapeError("Could not find the server-rendered search state.")
        search = json.loads(match[1])["STORE_KEY"]["searchResponse"]
        if not isinstance(search, dict):
            raise ScrapeError(f"Search page {page_number} did not contain results.")
        if expected is None:
            expected = int(search["divs"])
        for posting in search["postings"]:
            salary = posting.get("salary") or {}
            contract = salary.get("type")
            salaries = []
            if salary.get("from") is not None and salary.get("to") is not None:
                salaries.append({
                    "contract_type": contract,
                    "from": salary["from"], "to": salary["to"],
                    "currency": salary.get("currency"),
                    "unit": str(salary.get("period") or "unknown").lower(),
                    "gross": None,
                    "currency_source": "listing_data",
                })
            offers_by_id[posting["id"]] = {
                "offer_url": urljoin(url, "/pl/job/" + posting["url"]),
                "job_name": posting["title"],
                "salary": salaries,
                "required_skills": [tile["value"] for tile in posting.get("tiles", {}).get("values", []) if tile.get("type") == "requirement"],
                "type_of_contract": [contract] if contract else [],
                "seniority": posting.get("seniority", []),
            }
        print(f"Collected exact-match page {page_number}: {len(offers_by_id)}/{expected} offers", file=sys.stderr)
        if len(offers_by_id) >= expected or page_number >= int(search["exactMatchesPages"]):
            break
        page_number += 1
        time.sleep(delay_seconds)
    if len(offers_by_id) != expected:
        raise ScrapeError(f"Incomplete search: collected {len(offers_by_id)} of {expected} exact matches.")
    return list(offers_by_id.values()), expected


def build_output_document(source_url: str, offers: list[dict[str, Any]], total_offers: int) -> dict[str, Any]:
    return {
        "source_url": source_url,
        "scraped_at_utc": datetime.now(UTC).isoformat(),
        "filtered_total_offers": total_offers,
        "embedded_offers_total": total_offers,
        "offers_count": len(offers),
        "offers": offers,
    }


def write_json(output_path: Path, document: dict[str, Any]) -> None:
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(output_path: Path, document: dict[str, Any]) -> None:
    lines = [json.dumps(offer, ensure_ascii=False) for offer in document["offers"]]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def markdown_escape(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def render_salary_markdown(salary_items: list[dict[str, Any]]) -> str:
    if not salary_items:
        return ""

    parts = []
    for item in salary_items:
        low = item.get("from")
        high = item.get("to")
        currency = item.get("currency") or ""
        unit = item.get("unit") or ""
        contract_type = item.get("contract_type") or ""
        if low is None and high is None:
            range_text = "n/a"
        elif low is None:
            range_text = f"<= {high}"
        elif high is None:
            range_text = f">= {low}"
        else:
            range_text = f"{low}-{high}"
        parts.append(f"{contract_type}: {range_text} {currency}/{unit}".strip())

    return "; ".join(parts)


def write_markdown(output_path: Path, document: dict[str, Any]) -> None:
    lines = [
        "# No Fluff Jobs offers",
        "",
        f"- Source URL: {document['source_url']}",
        f"- Scraped at UTC: {document['scraped_at_utc']}",
        f"- Filtered total offers: {document['filtered_total_offers']}",
        f"- Embedded offers total: {document['embedded_offers_total']}",
        f"- Offers count: {document['offers_count']}",
        "",
        "| job_name | salary | required_skills | type_of_contract |",
        "| --- | --- | --- | --- |",
    ]

    for offer in document["offers"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(offer["job_name"] or ""),
                    markdown_escape(render_salary_markdown(offer["salary"])),
                    markdown_escape(", ".join(offer["required_skills"])),
                    markdown_escape(", ".join(offer["type_of_contract"])),
                ]
            )
            + " |"
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_output(output_path: Path, fmt: str, document: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        write_json(output_path, document)
    elif fmt == "jsonl":
        write_jsonl(output_path, document)
    elif fmt == "md":
        write_markdown(output_path, document)
    else:
        raise ValueError(f"Unsupported output format: {fmt}")


def main() -> int:
    args = parse_args()

    try:
        config = apply_cli_overrides(load_config(Path(args.config)), args)
        validate_url(config.url)
        output_path = Path(config.output)
        output_format = infer_format(output_path, config.format)
        offers, total_items = scrape_offers(
            config.url,
            delay_seconds=config.delay_seconds,
        )
        document = build_output_document(config.url, offers, total_items)
        write_output(output_path, output_format, document)
        print(
            json.dumps(
                {
                    "output": str(output_path),
                    "format": output_format,
                    "offers_count": document["offers_count"],
                    "expected_total": total_items,
                    "embedded_offers_total": total_items,
                }
            )
        )
        return 0
    except (ScrapeError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
