"""Load one or more independently processed entries from a JSON config file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config_entries(path: Path) -> list[dict[str, Any]]:
    """Return the entries in a universal ``listings`` config.

    Fields beside ``listings`` are shared by every entry, and fields on an
    individual listing take precedence.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a JSON object.")

    listings = raw.get("listings")
    if not isinstance(listings, list) or not listings:
        raise ValueError("Config field `listings` must be a non-empty array.")

    shared = {
        key: value
        for key, value in raw.items()
        if key != "listings"
    }

    entries: list[dict[str, Any]] = []
    for index, listing in enumerate(listings, start=1):
        if not isinstance(listing, dict):
            raise ValueError(f"Config listing {index} must be a JSON object.")
        entries.append({**shared, **listing})
    return entries


def require_unique_values(entries: list[dict[str, Any]], field: str) -> None:
    """Prevent one listing from silently overwriting another listing's result."""
    values = [str(entry[field]) for entry in entries]
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(
            f"Each listing must have a distinct `{field}`; duplicated: "
            + ", ".join(duplicates)
        )
