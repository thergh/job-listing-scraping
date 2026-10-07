#!/usr/bin/env python3

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from config_entries import require_unique_values
from workflow_config import load_reporter_entries


DEFAULT_CONFIG = "jobs-config.json"
PAGE_SIZE = (11.69, 8.27)
PRIMARY = "#2563EB"
MUTED = "#64748B"
INK = "#0F172A"
LIGHT = "#E2E8F0"


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


def add_footer(fig, data, include_methodology=False):
    if include_methodology:
        fig.text(
            0.04,
            0.052,
            "Method: each posting counts once per skill; salary coverage requires a complete range. "
            "Currencies and time units are not converted; multi-location offers can affect source totals.",
            color=MUTED,
            fontsize=7.5,
        )
    fig.text(
        0.04,
        0.018,
        f"{source_label(data.get('source_url'))}  •  {collected_label(data.get('gathered_at_utc'))}",
        color=MUTED,
        fontsize=8,
    )


def style_axis(ax):
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="both", colors="#475569", labelsize=8)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)


def draw_horizontal_bar(ax, items, title):
    if not items:
        ax.axis("off")
        ax.text(0.5, 0.5, "No keyword data", ha="center", color=MUTED)
        return

    items = list(reversed(items))
    labels = [str(item["keyword"]) for item in items]
    counts = [item["count"] for item in items]
    percentages = [item["percentage"] for item in items]
    bars = ax.barh(labels, counts, color=PRIMARY, height=0.68)
    ax.set_title(title, fontsize=14, pad=10, loc="left", color=INK, fontweight="bold")
    ax.set_xlabel("Postings", fontsize=9, color=MUTED)
    style_axis(ax)

    maximum = max(counts)
    ax.set_xlim(0, maximum * 1.29 if maximum else 1)
    label_size = 7 if len(items) > 18 else 8
    ax.tick_params(axis="y", labelsize=label_size)
    for bar, count, percentage in zip(bars, counts, percentages):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"  {count} · {percentage:.1f}%",
            va="center",
            fontsize=label_size,
            color="#334155",
        )


def salary_rows(statistics, currency, unit):
    rows = [
        row
        for row in statistics
        if row.get("currency") == currency and row.get("unit") == unit
    ]
    return sorted(rows, key=lambda row: row.get("avg_salary", 0), reverse=True)


def draw_salary(ax, rows, currency, unit):
    if not rows:
        ax.axis("off")
        return

    labels = [
        f'{row.get("contract_type", "unknown")} ({row.get("postings_with_salary", 0)})'
        for row in rows
    ]
    minimums = [row.get("avg_salary_min", 0) for row in rows]
    maximums = [row.get("avg_salary_max", 0) for row in rows]
    widths = [max(maximum - minimum, 0) for minimum, maximum in zip(minimums, maximums)]
    positions = range(len(rows))

    ax.barh(positions, minimums, label="Average minimum", color=PRIMARY, height=0.56)
    ax.barh(
        positions,
        widths,
        left=minimums,
        label="Average maximum range",
        color="#93C5FD",
        height=0.56,
    )
    ax.set_yticks(list(positions), labels)
    ax.invert_yaxis()
    ax.set_xlabel(f"{currency} / {unit}", fontsize=9, color=MUTED)
    ax.set_title(
        f"Salary ranges · {currency} / {unit}",
        fontsize=14,
        pad=10,
        loc="left",
        color=INK,
        fontweight="bold",
    )
    style_axis(ax)
    ax.legend(frameon=False, fontsize=8, loc="lower right")

    maximum_value = max(maximums)
    ax.set_xlim(0, maximum_value * 1.24 if maximum_value else 1)
    for index, (minimum, maximum) in enumerate(zip(minimums, maximums)):
        ax.text(minimum, index, f" {minimum:,.0f}", va="center", fontsize=8, color=INK)
        ax.text(maximum, index, f" {maximum:,.0f}", va="center", fontsize=8, color=INK)


def draw_kpis(ax, data):
    ax.axis("off")
    total = data.get("postings_total", 0)
    with_salary = data.get("postings_with_salary", 0)
    coverage = (with_salary / total * 100) if total else 0
    cards = [
        (f"{total:,}", "POSTINGS"),
        (f"{with_salary:,}", "WITH SALARY"),
        (f"{coverage:.1f}%", "SALARY COVERAGE"),
    ]
    for index, (value, label) in enumerate(cards):
        x = 0.02 + index * 0.225
        ax.text(x, 0.63, value, fontsize=24, fontweight="bold", color=INK, va="center")
        ax.text(x, 0.18, label, fontsize=8, color=MUTED, va="center", fontweight="bold")


def dashboard_page(
    pdf,
    data,
    title,
    skills,
    skills_title,
    title_keywords,
    title_keywords_title,
    include_methodology,
):
    fig = plt.figure(figsize=PAGE_SIZE)
    grid = fig.add_gridspec(
        2,
        2,
        height_ratios=(0.18, 0.82),
        width_ratios=(1.2, 1),
        left=0.07,
        right=0.97,
        top=0.87,
        bottom=0.13 if include_methodology else 0.075,
        wspace=0.28,
        hspace=0.18,
    )
    draw_kpis(fig.add_subplot(grid[0, :]), data)
    draw_horizontal_bar(fig.add_subplot(grid[1, 0]), skills, skills_title)
    draw_horizontal_bar(
        fig.add_subplot(grid[1, 1]), title_keywords, title_keywords_title
    )

    fig.suptitle(title, x=0.07, y=0.955, ha="left", fontsize=20, fontweight="bold", color=INK)
    add_footer(fig, data, include_methodology)
    pdf.savefig(fig)
    plt.close(fig)


def chart_pages(pdf, data, charts, include_methodology):
    for offset in range(0, len(charts), 2):
        page_charts = charts[offset : offset + 2]
        # Always retain the two-column grid so a final unpaired salary chart
        # has the same scale as every other salary chart.
        fig, axes = plt.subplots(1, 2, figsize=PAGE_SIZE, squeeze=False)
        for axis, (kind, payload) in zip(axes[0], page_charts):
            if kind == "keywords":
                items, title = payload
                draw_horizontal_bar(axis, items, title)
            else:
                rows, currency, unit = payload
                draw_salary(axis, rows, currency, unit)
        for axis in axes[0][len(page_charts) :]:
            axis.axis("off")
        add_footer(fig, data, include_methodology)
        fig.subplots_adjust(
            left=0.08,
            right=0.97,
            top=0.9,
            bottom=0.13 if include_methodology else 0.08,
            wspace=0.35,
        )
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
    try:
        configs = load_reporter_entries(config_path)
        require_unique_values(configs, "output")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    failures = 0
    for index, config in enumerate(configs, start=1):
        try:
            process_config(config, config_path)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            failures += 1
            print(f"error: listing {index}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def process_config(config, config_path):
    input_path = resolve_path(config_path, config["input"]).resolve()
    output_path = resolve_path(config_path, config["output"]).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = load_json(input_path)
    title = config.get("title") or Path(data.get("source", input_path.stem)).stem
    skills = top_items(
        data.get("skill_keywords", []),
        config.get("top_skills", 25),
        config.get("exclude_skills", []),
    )
    title_keywords = top_items(
        data.get("job_title_keywords", []),
        config.get("top_title_keywords", 20),
        config.get("exclude_title_keywords", []),
    )
    currency = config.get("salary_currency", "PLN")
    skills_title = config.get("skills_title", "Most requested skills and technologies")
    title_keywords_title = config.get(
        "title_keywords_title", "Most common job-title keywords"
    )
    salary_charts = []
    for unit in config.get("salary_units", [config.get("salary_unit", "month")]):
        rows = salary_rows(data.get("salary_statistics", []), currency, unit)
        if rows:
            salary_charts.append(("salary", (rows, currency, unit)))

    include_methodology = config.get("include_methodology", True)
    with PdfPages(output_path) as pdf:
        pdf.infodict().update({"Title": title, "Author": "Job listings scraper"})
        dashboard_page(
            pdf,
            data,
            title,
            skills,
            skills_title,
            title_keywords,
            title_keywords_title,
            include_methodology,
        )
        chart_pages(pdf, data, salary_charts, include_methodology)

    print(output_path)


if __name__ == "__main__":
    raise SystemExit(main())
