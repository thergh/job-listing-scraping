"""Read and validate scraper output before it enters the analysis pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class InputDataError(ValueError):
    """Raised when scraper output does not follow the supported data contract."""


def load_document(path: Path) -> dict[str, Any]:
    """Load JSON documents and JSON Lines exports into one document shape."""
    try:
        if path.suffix.casefold() == ".jsonl":
            offers = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            document: dict[str, Any] = {"offers": offers}
        else:
            raw = json.loads(path.read_text(encoding="utf-8"))
            document = {"offers": raw} if isinstance(raw, list) else raw
    except FileNotFoundError as exc:
        raise InputDataError(f"Input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputDataError(f"Invalid JSON in {path}: {exc.msg}") from exc

    if not isinstance(document, dict):
        raise InputDataError("Input JSON must be an array or an object with an 'offers' array.")
    offers = document.get("offers")
    if not isinstance(offers, list):
        raise InputDataError("Input JSON must contain an 'offers' array.")
    for index, offer in enumerate(offers, start=1):
        if not isinstance(offer, dict):
            raise InputDataError(f"Offer {index} must be a JSON object.")
    return document


def collection_metadata(document: dict[str, Any]) -> dict[str, Any]:
    """Keep source metadata available without treating site totals as offer counts."""
    return {
        key: document[key]
        for key in (
            "source_url",
            "scraped_at_utc",
            "filtered_total_offers",
            "embedded_offers_total",
            "offers_count",
        )
        if key in document
    }
