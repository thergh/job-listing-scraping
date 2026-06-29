#!/usr/bin/env python3
"""Scrape Just Join IT offer lists into simple database-friendly files.

The scraper starts with the server-rendered page payload to get the first batch
of offers and the normalized filter state. If more offers exist, it falls back
to a slow Playwright-driven scroll so the website can load the remaining chunks
through its own frontend flow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
NEXT_CHUNK_PATTERN = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>')


class ScrapeError(RuntimeError):
    """Raised when the page structure cannot be parsed reliably."""


@dataclass
class BootstrapState:
    offers: list[dict[str, Any]]
    total_items: int
    filters: dict[str, Any]
    embedded_offers_total: int
    filtered_offers_count: int | None = None


@dataclass
class ScraperConfig:
    url: str
    output: str = "data/offers.json"
    format: str | None = None
    delay_seconds: float = 1.5
    max_idle_scrolls: int = 10
    headful: bool = False


LEVEL_LABELS = {"Internship", "Junior", "Mid", "Senior", "Lead", "C-level"}
CONTRACT_LABELS = {
    "B2B",
    "Permanent",
    "Mandate Contract",
    "Specific-task Contract",
    "Internship",
    "Temporary Staffing Agreement",
    "Substitution Agreement",
    "Contract of Employment",
}
SKIP_CARD_LINES = {"Super offer", "1-click Apply", "Apply"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape a filtered Just Join IT offers page from a JSON config file."
    )
    parser.add_argument(
        "--config",
        default="jjit-scraper-config.json",
        help="Path to scraper config JSON. Default: jit-scraper-config.json",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> ScraperConfig:
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScrapeError(
            f"Config file not found: {config_path}. Create it from config.example.json."
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
        delay_seconds=float(raw_config.get("delay_seconds", 1.5)),
        max_idle_scrolls=int(raw_config.get("max_idle_scrolls", 10)),
        headful=bool(raw_config.get("headful", False)),
    )


def infer_format(output_path: Path, explicit_format: str | None) -> str:
    if explicit_format:
        return explicit_format
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in {"json", "jsonl", "md"}:
        return suffix
    return "json"


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def decode_next_chunks(html: str) -> list[str]:
    encoded_chunks = NEXT_CHUNK_PATTERN.findall(html)
    if not encoded_chunks:
        raise ScrapeError("Could not find embedded Next.js payload in page HTML.")
    return [bytes(chunk, "utf-8").decode("unicode_escape") for chunk in encoded_chunks]


def find_balanced_json_object(text: str, start_index: int) -> str:
    depth = 0
    in_string = False
    escape = False
    start = -1

    for index in range(start_index, len(text)):
        char = text[index]

        if start == -1:
            if char == "{":
                start = index
                depth = 1
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ScrapeError("Could not isolate the embedded OFFERS query object.")


def extract_query_object(decoded_chunks: list[str], query_hash_prefix: str) -> dict[str, Any]:
    matching_chunk = next(
        (chunk for chunk in decoded_chunks if query_hash_prefix in chunk),
        None,
    )
    if matching_chunk is None:
        raise ScrapeError(f"Could not find embedded query object for prefix: {query_hash_prefix}")

    marker_index = matching_chunk.find(query_hash_prefix)
    object_start = matching_chunk.rfind('{"state":', 0, marker_index)
    if object_start == -1:
        raise ScrapeError(f"Could not locate the query object boundary for: {query_hash_prefix}")

    return json.loads(find_balanced_json_object(matching_chunk, object_start))


def parse_bootstrap_state(html: str) -> BootstrapState:
    decoded_chunks = decode_next_chunks(html)

    offers_query = extract_query_object(decoded_chunks, '"queryHash":"[\\"OFFERS\\",')
    offers_count_query = extract_query_object(decoded_chunks, '"queryHash":"[\\"OFFERS_COUNT\\",')

    filters = json.loads(offers_query["queryHash"])[1]
    first_page = offers_query["state"]["data"]["pages"][0]
    embedded_offers_total = int(first_page["meta"]["totalItems"])
    filtered_offers_count = offers_count_query["state"]["data"].get("count")
    total_items = (
        int(filtered_offers_count)
        if isinstance(filtered_offers_count, int)
        else embedded_offers_total
    )

    return BootstrapState(
        offers=first_page["data"],
        total_items=total_items,
        filters=filters,
        embedded_offers_total=embedded_offers_total,
        filtered_offers_count=filtered_offers_count if isinstance(filtered_offers_count, int) else None,
    )


def dedupe_offers(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []

    for offer in offers:
        key = str(
            offer.get("guid")
            or offer.get("slug")
            or offer.get("offer_url")
            or offer.get("title")
            or offer.get("job_name")
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(offer)

    return unique


def parse_salary_range(raw_value: str) -> tuple[int | None, int | None]:
    cleaned = raw_value.replace("\xa0", " ")
    parts = [part.strip().replace(" ", "") for part in cleaned.split("-")]
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return int(parts[0]), int(parts[1])
    if len(parts) == 1 and parts[0].isdigit():
        value = int(parts[0])
        return value, value
    return None, None


def normalize_dom_card_text(card_text: str, offer_url: str, job_name: str) -> dict[str, Any]:
    lines = [
        line.strip()
        for line in card_text.replace("\xa0", " ").splitlines()
        if line.strip() and line.strip() not in SKIP_CARD_LINES
    ]

    salary_index = None
    salary_line = None
    salary_unit_line = None
    for index, line in enumerate(lines):
        if re.fullmatch(r"[\d\s]+(?:-\s*[\d\s]+)?", line) and index + 1 < len(lines):
            next_line = lines[index + 1]
            if re.fullmatch(r"[A-Z]{3}/(month|h)", next_line):
                salary_index = index
                salary_line = line
                salary_unit_line = next_line
                break

    deadline_index = next(
        (index for index, line in enumerate(lines) if re.fullmatch(r"\d+d left", line)),
        None,
    )

    skill_start_index = 0
    if salary_index is not None:
        skill_start_index = salary_index + 2
    elif deadline_index is not None:
        skill_start_index = deadline_index + 1

    marker_indices = [
        index
        for index, line in enumerate(lines[skill_start_index:], start=skill_start_index)
        if line in LEVEL_LABELS or line in CONTRACT_LABELS
    ]
    skill_end_index = marker_indices[0] if marker_indices else len(lines)
    required_skills = [
        line
        for line in lines[skill_start_index:skill_end_index]
        if line != job_name and line not in LEVEL_LABELS and line not in CONTRACT_LABELS
    ]

    contract_types = [line for line in lines if line in CONTRACT_LABELS]
    salary_items: list[dict[str, Any]] = []
    if salary_line and salary_unit_line:
        amount_from, amount_to = parse_salary_range(salary_line)
        currency, unit = salary_unit_line.split("/", 1)
        salary_items.append(
            {
                "contract_type": contract_types[0] if contract_types else None,
                "from": amount_from,
                "to": amount_to,
                "currency": currency,
                "unit": unit,
                "gross": None,
                "currency_source": "card_text",
                "raw_text": f"{salary_line} {salary_unit_line}",
            }
        )

    return {
        "offer_url": offer_url,
        "job_name": job_name,
        "salary": salary_items,
        "required_skills": required_skills,
        "type_of_contract": contract_types,
    }


def scrape_remaining_offers_with_playwright(
    url: str,
    initial_rows: list[dict[str, Any]],
    total_items: int,
    delay_seconds: float,
    max_idle_scrolls: int,
    headless: bool,
) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise ScrapeError(
            "More offers exist than were embedded in the initial HTML, but Playwright "
            "is not installed. Install it with `pip install -r requirements.txt` and "
            "`python3 -m playwright install chromium`."
        ) from exc

    rows_by_url: dict[str, dict[str, Any]] = {}
    initial_rows_by_url = {row["offer_url"]: row for row in initial_rows if row.get("offer_url")}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 2000},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        page.wait_for_timeout(1_500)

        for label in ("Accept all", "Accept", "Akceptuj wszystkie", "Allow all"):
            button = page.get_by_role("button", name=label)
            if button.count():
                try:
                    button.first.click(timeout=2_000)
                    page.wait_for_timeout(500)
                    break
                except PlaywrightTimeoutError:
                    pass

        try:
            page.wait_for_selector("a.offer-card", timeout=20_000)
        except PlaywrightTimeoutError as exc:
            browser.close()
            raise ScrapeError("The offers list did not appear in the browser.") from exc

        def harvest_visible_cards() -> None:
            cards = page.evaluate(
                """
                () => Array.from(document.querySelectorAll('a.offer-card')).map((anchor) => {
                  const card = anchor.parentElement;
                  return {
                    url: anchor.href,
                    jobName: (anchor.getAttribute('title') || '').replace(/^View offer\\s+/, '').trim(),
                    text: card ? card.innerText : ''
                  };
                })
                """
            )
            for card in cards:
                offer_url = card.get("url")
                job_name = card.get("jobName")
                card_text = card.get("text") or ""
                if not offer_url or not job_name or not card_text:
                    continue
                rows_by_url[offer_url] = normalize_dom_card_text(card_text, offer_url, job_name)

        idle_scrolls = 0
        previous_count = len(rows_by_url)
        harvest_visible_cards()
        previous_count = len(rows_by_url)

        while len(rows_by_url) < total_items and idle_scrolls < max_idle_scrolls:
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(int(delay_seconds * 1000))
            harvest_visible_cards()

            current_count = len(rows_by_url)
            if current_count > previous_count:
                previous_count = current_count
                idle_scrolls = 0
            else:
                idle_scrolls += 1

        browser.close()

    for offer_url, row in initial_rows_by_url.items():
        rows_by_url.setdefault(offer_url, row)

    return list(rows_by_url.values())


def format_salary_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_type": item.get("type"),
        "from": item.get("from"),
        "to": item.get("to"),
        "currency": item.get("currency"),
        "unit": item.get("unit"),
        "gross": item.get("gross"),
        "currency_source": item.get("currencySource"),
    }


def normalize_offer(offer: dict[str, Any]) -> dict[str, Any]:
    employment_types = offer.get("employmentTypes") or []
    original_salary_items = [
        format_salary_item(item)
        for item in employment_types
        if item.get("currencySource") == "original"
    ]
    salary_items = original_salary_items or [format_salary_item(item) for item in employment_types]

    contract_types = sorted(
        {
            str(item.get("type"))
            for item in employment_types
            if item.get("type") not in (None, "")
        }
    )

    return {
        "offer_url": f"https://justjoin.it/job-offer/{offer.get('slug')}" if offer.get("slug") else None,
        "job_name": offer.get("title"),
        "salary": salary_items,
        "required_skills": offer.get("requiredSkills") or [],
        "type_of_contract": contract_types,
    }


def build_output_document(
    source_url: str,
    offers: list[dict[str, Any]],
    filtered_total_offers: int,
    embedded_offers_total: int,
) -> dict[str, Any]:
    normalized = [
        {key: value for key, value in offer.items() if key != "offer_url"}
        for offer in offers
    ]
    return {
        "source_url": source_url,
        "scraped_at_utc": datetime.now(UTC).isoformat(),
        "filtered_total_offers": filtered_total_offers,
        "embedded_offers_total": embedded_offers_total,
        "offers_count": len(normalized),
        "offers": normalized,
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
        "# Just Join IT offers",
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


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in {"justjoin.it", "www.justjoin.it"}:
        raise ScrapeError("Please pass a Just Join IT offers URL from justjoin.it.")


def main() -> int:
    args = parse_args()

    try:
        config = load_config(Path(args.config))
        validate_url(config.url)
        output_path = Path(config.output)
        output_format = infer_format(output_path, config.format)
        session = build_session()
        html = fetch_html(session, config.url)
        bootstrap = parse_bootstrap_state(html)

        normalized_rows = [normalize_offer(offer) for offer in dedupe_offers(bootstrap.offers)]
        if len(normalized_rows) < bootstrap.total_items:
            normalized_rows = dedupe_offers(
                scrape_remaining_offers_with_playwright(
                    url=config.url,
                    initial_rows=normalized_rows,
                    total_items=bootstrap.total_items,
                    delay_seconds=config.delay_seconds,
                    max_idle_scrolls=config.max_idle_scrolls,
                    headless=not config.headful,
                )
            )

        document = build_output_document(
            config.url,
            normalized_rows,
            filtered_total_offers=bootstrap.total_items,
            embedded_offers_total=bootstrap.embedded_offers_total,
        )
        write_output(output_path, output_format, document)

        print(
            json.dumps(
                {
                    "output": str(output_path),
                    "format": output_format,
                    "offers_count": document["offers_count"],
                    "expected_total": bootstrap.total_items,
                    "embedded_offers_total": bootstrap.embedded_offers_total,
                }
            )
        )
        return 0
    except (requests.RequestException, ScrapeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
