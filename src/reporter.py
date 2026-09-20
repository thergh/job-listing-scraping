#!/usr/bin/env python3

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


DEFAULT_CONFIG = "reporter-config.json"
PAGE_SIZE = (11.69, 8.27)
PRIMARY = "#2563EB"
ACCENT = "#0F766E"
MUTED = "#64748B"


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def top_items(items, limit, excluded):
    excluded = {str(value).strip().lower() for value in excluded}

    return sorted(
        (
            item
            for item in items
            if str(item.get("keyword", "")).strip().lower() not in excluded
        ),
        key=lambda item: (item.get("count", 0), item.get("percentage", 0)),
        reverse=True,
    )[:limit]


def source_label(source_url):
    host = urlparse(source_url or "").netloc
    return host.removeprefix("www.") or "Source not recorded"


def collected_label(value):
    if not value:
        return "Collection time not recorded"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
            "Collected %d %b %Y, %H:%M UTC"
        )
    except ValueError:
        return f"Collected {value}"


def add_footer(fig, data):
    fig.text(
        0.01,
        0.015,
        f"{source_label(data.get('source_url'))}  •  {collected_label(data.get('gathered_at_utc'))}",
        color=MUTED,
        fontsize=8,
    )


def horizontal_bar(pdf, items, title, data):
    if not items:
        return

    items = list(reversed(items))
    labels = [str(item["keyword"]) for item in items]
    counts = [item["count"] for item in items]
    percentages = [item["percentage"] for item in items]

    fig, ax = plt.subplots(figsize=PAGE_SIZE)
    bars = ax.barh(labels, counts, color=PRIMARY)

    ax.set_title(title, fontsize=18, pad=18)
    ax.set_xlabel("Postings")
    ax.grid(axis="x", alpha=0.25)

    maximum = max(counts)
    ax.set_xlim(0, maximum * 1.22 if maximum else 1)

    for bar, count, percentage in zip(bars, counts, percentages):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"  {count} ({percentage:.1f}%)",
            va="center",
            fontsize=9,
        )

    add_footer(fig, data)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    pdf.savefig(fig)
    plt.close(fig)


def overview_page(pdf, data, title):
    total = data.get("postings_total", 0)
    with_salary = data.get("postings_with_salary", 0)
    without_salary = max(total - with_salary, 0)

    fig, axes = plt.subplots(1, 2, figsize=PAGE_SIZE)

    axes[0].axis("off")
    axes[0].text(
        0.5, 0.72, f"{total}",
        ha="center", va="center",
        fontsize=58, fontweight="bold",
    )
    axes[0].text(
        0.5, 0.57, "POSTINGS",
        ha="center", va="center",
        fontsize=18,
    )
    axes[0].text(
        0.5, 0.35, f"{with_salary}",
        ha="center", va="center",
        fontsize=38, fontweight="bold",
    )
    axes[0].text(
        0.5, 0.24, "WITH SALARY",
        ha="center", va="center",
        fontsize=14,
    )

    if total > 0:
        axes[1].pie(
            [with_salary, without_salary],
            labels=["With salary", "Without salary"],
            autopct="%1.1f%%",
            startangle=90,
            colors=[ACCENT, "#E2E8F0"],
        )
    else:
        axes[1].axis("off")

    axes[1].set_title("Salary coverage", fontsize=18, pad=18)

    fig.suptitle(title, fontsize=22, y=0.96, fontweight="bold")
    add_footer(fig, data)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    pdf.savefig(fig)
    plt.close(fig)


def salary_page(pdf, statistics, currency, unit, data):
    rows = [
        row
        for row in statistics
        if row.get("currency") == currency and row.get("unit") == unit
    ]

    if not rows:
        return

    rows.sort(key=lambda row: row.get("avg_salary", 0), reverse=True)

    labels = [
        f'{row.get("contract_type", "unknown")} ({row.get("postings_with_salary", 0)})'
        for row in rows
    ]
    minimums = [row.get("avg_salary_min", 0) for row in rows]
    maximums = [row.get("avg_salary_max", 0) for row in rows]
    widths = [
        max(maximum - minimum, 0)
        for minimum, maximum in zip(minimums, maximums)
    ]

    fig, ax = plt.subplots(figsize=PAGE_SIZE)
    positions = range(len(rows))

    ax.barh(positions, minimums, label="Average minimum", color=PRIMARY)
    ax.barh(
        positions,
        widths,
        left=minimums,
        label="Average maximum range",
        color="#93C5FD",
    )

    ax.set_yticks(list(positions), labels)
    ax.invert_yaxis()
    ax.set_xlabel(f"{currency} / {unit}")
    ax.set_title(
        f"Average salary ranges — {currency} / {unit}",
        fontsize=18,
        pad=18,
    )
    ax.grid(axis="x", alpha=0.25)
    ax.legend()

    maximum_value = max(maximums)
    ax.set_xlim(0, maximum_value * 1.18 if maximum_value else 1)

    for index, row in enumerate(rows):
        minimum = row.get("avg_salary_min", 0)
        maximum = row.get("avg_salary_max", 0)

        ax.text(
            minimum,
            index,
            f" {minimum:,.0f}",
            va="center",
            ha="left",
            fontsize=9,
        )
        ax.text(
            maximum,
            index,
            f" {maximum:,.0f}",
            va="center",
            ha="left",
            fontsize=9,
        )

    add_footer(fig, data)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    pdf.savefig(fig)
    plt.close(fig)


def methodology_page(pdf, data):
    fig, ax = plt.subplots(figsize=PAGE_SIZE)
    ax.axis("off")
    ax.text(0.06, 0.88, "How to read this report", fontsize=24, fontweight="bold")
    lines = [
        "Each posting contributes at most once to a skill frequency.",
        "Salary coverage means that a listing exposed a complete salary range.",
        "Salary ranges are grouped by currency, contract type, and time unit.",
        "Hourly, daily, monthly, and yearly amounts are never converted or compared directly.",
        "Source totals can differ from unique postings when one offer has several locations.",
    ]
    for index, line in enumerate(lines):
        ax.text(0.08, 0.72 - index * 0.11, f"•  {line}", fontsize=13, color="#1E293B")
    add_footer(fig, data)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    pdf.savefig(fig)
    plt.close(fig)


def resolve_path(config_path, value):
    path = Path(value)
    return path if path.is_absolute() else config_path.parent / path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", default=DEFAULT_CONFIG)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path)

    input_path = resolve_path(config_path, config["input"]).resolve()
    output_path = resolve_path(config_path, config["output"]).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = load_json(input_path)
    title = config.get("title") or Path(data.get("source", input_path.stem)).stem

    with PdfPages(output_path) as pdf:
        pdf.infodict().update({"Title": title, "Author": "Job listings scraper"})
        overview_page(pdf, data, title)

        horizontal_bar(
            pdf,
            top_items(
                data.get("skill_keywords", []),
                config.get("top_skills", 25),
                config.get("exclude_skills", []),
            ),
            config.get(
                "skills_title",
                "Most requested skills and technologies",
            ),
            data,
        )

        horizontal_bar(
            pdf,
            top_items(
                data.get("job_title_keywords", []),
                config.get("top_title_keywords", 20),
                config.get("exclude_title_keywords", []),
            ),
            config.get(
                "title_keywords_title",
                "Most common job-title keywords",
            ),
            data,
        )

        for unit in config.get("salary_units", [config.get("salary_unit", "month")]):
            salary_page(
                pdf,
                data.get("salary_statistics", []),
                config.get("salary_currency", "PLN"),
                unit,
                data,
            )

        if config.get("include_methodology", True):
            methodology_page(pdf, data)

    print(output_path)


if __name__ == "__main__":
    main()
