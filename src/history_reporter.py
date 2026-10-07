#!/usr/bin/env python3
"""Create a time-series PDF report from one historical job-type CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


PAGE_SIZE = (11.69, 8.27)
SOURCE_COLORS = {"Just Join IT": "#2563EB", "No Fluff Jobs": "#0F766E"}
INK = "#0F172A"
MUTED = "#64748B"
LIGHT = "#E2E8F0"


def parse_snapshot(row):
    row = dict(row)
    row["collected_at"] = datetime.fromisoformat(row["gathered_at_utc"])
    for key in ("postings_total", "postings_with_salary", "salary_coverage_percentage"):
        row[key] = float(row[key])
    row["salary_statistics"] = json.loads(row.get("salary_statistics") or "[]")
    row["top_skills"] = json.loads(row.get("top_skills") or "[]")
    return row


def load_snapshots(path, source=None):
    with path.open(encoding="utf-8", newline="") as file:
        rows = [parse_snapshot(row) for row in csv.DictReader(file)]
    if source:
        rows = [row for row in rows if row["source"] == source]

    # A PDF backfill and the original scraper export can describe the same daily
    # collection. Prefer the latter because it retains the complete salary data.
    selected = {}
    priority = {"retroactive_pdf": 0, "scraper": 1}
    for row in rows:
        key = (row["source"], row["collected_at"].date())
        previous = selected.get(key)
        if previous is None or (priority.get(row["origin"], 0), row["collected_at"]) > (
            priority.get(previous["origin"], 0), previous["collected_at"]
        ):
            selected[key] = row
    return sorted(selected.values(), key=lambda row: row["collected_at"])


def source_groups(snapshots):
    groups = defaultdict(list)
    for snapshot in snapshots:
        groups[snapshot["source"]].append(snapshot)
    return groups


def source_color(source, index):
    return SOURCE_COLORS.get(source, plt.get_cmap("tab10")(index))


def add_footer(fig, job_type, snapshots):
    fig.text(
        0.01,
        0.015,
        f"{job_type}  •  {len(snapshots)} dated snapshots  •  scraper rows take precedence over same-day PDF backfills",
        fontsize=8,
        color="#64748B",
    )


def style_axis(ax):
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="both", colors="#475569", labelsize=8)
    ax.set_axisbelow(True)


def draw_line(ax, snapshots, metric, title, ylabel, percent=False):
    for index, (source, rows) in enumerate(source_groups(snapshots).items()):
        ax.plot(
            [row["collected_at"] for row in rows],
            [row[metric] for row in rows],
            marker="o",
            markersize=4,
            linewidth=2.2,
            label=source,
            color=source_color(source, index),
        )
    ax.set_title(title, fontsize=14, pad=10, loc="left", color=INK, fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=9, color=MUTED)
    ax.grid(color=LIGHT, linewidth=0.8)
    ax.legend(frameon=False, fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%Y"))
    if percent:
        ax.set_ylim(0, 100)
    style_axis(ax)


def dashboard_page(pdf, job_type, snapshots):
    latest = snapshots[-1]
    fig = plt.figure(figsize=PAGE_SIZE)
    grid = fig.add_gridspec(
        2,
        2,
        height_ratios=(0.2, 0.8),
        left=0.07,
        right=0.97,
        top=0.86,
        bottom=0.09,
        wspace=0.25,
        hspace=0.22,
    )
    summary = fig.add_subplot(grid[0, :])
    summary.axis("off")
    values = [
        (f"{int(latest['postings_total']):,}", "LATEST POSTINGS"),
        (f"{latest['salary_coverage_percentage']:.1f}%", "SALARY COVERAGE"),
        (latest["collected_at"].strftime("%d %b %Y"), "LATEST COLLECTION"),
        (f"{len(snapshots)}", "DATED SNAPSHOTS"),
    ]
    for index, (value, label) in enumerate(values):
        x = 0.01 + index * 0.245
        summary.text(x, 0.62, value, fontsize=22, fontweight="bold", color=INK, va="center")
        summary.text(x, 0.18, label, fontsize=8, fontweight="bold", color=MUTED, va="center")

    draw_line(
        fig.add_subplot(grid[1, 0]),
        snapshots,
        "postings_total",
        "Posting count over time",
        "Postings",
    )
    draw_line(
        fig.add_subplot(grid[1, 1]),
        snapshots,
        "salary_coverage_percentage",
        "Salary coverage over time",
        "Listings with salary (%)",
        percent=True,
    )
    fig.suptitle(
        f"History — {job_type}",
        x=0.07,
        y=0.95,
        ha="left",
        fontsize=20,
        fontweight="bold",
        color=INK,
    )
    add_footer(fig, job_type, snapshots)
    pdf.savefig(fig)
    plt.close(fig)


def monthly_salary_page(pdf, job_type, snapshots):
    series = defaultdict(list)
    for snapshot in snapshots:
        for statistic in snapshot["salary_statistics"]:
            if statistic.get("currency") != "PLN" or statistic.get("unit") != "month":
                continue
            label = f"{snapshot['source']} — {statistic.get('contract_type', 'unknown')}"
            series[label].append((snapshot["collected_at"], statistic.get("avg_salary", 0)))
    if not series:
        return
    fig, ax = plt.subplots(figsize=PAGE_SIZE)
    for index, (label, points) in enumerate(sorted(series.items())):
        points.sort()
        ax.plot(*zip(*points), marker="o", linewidth=2.5, label=label, color=plt.get_cmap("tab10")(index))
    ax.set_title(
        "Average listed salary — PLN / month",
        fontsize=16,
        pad=12,
        loc="left",
        color=INK,
        fontweight="bold",
    )
    ax.set_ylabel("PLN / month", fontsize=9, color=MUTED)
    ax.grid(color=LIGHT, linewidth=0.8)
    ax.legend(frameon=False, fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%Y"))
    style_axis(ax)
    add_footer(fig, job_type, snapshots)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    pdf.savefig(fig)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Generate a PDF trend report from a job history CSV.")
    parser.add_argument(
        "job_type",
        help="CSV stem in res/history/snapshots/, for example java-mid",
    )
    parser.add_argument("--history-dir", default="res/history/snapshots")
    parser.add_argument("--output", help="Default: res/history/reports/<job_type>.pdf")
    parser.add_argument("--source", help="Only include this source label")
    args = parser.parse_args()

    history_path = Path(args.history_dir) / f"{args.job_type}.csv"
    if not history_path.exists():
        raise SystemExit(f"error: history file not found: {history_path}")
    snapshots = load_snapshots(history_path, args.source)
    if not snapshots:
        raise SystemExit("error: no snapshots match the selected source")
    source_suffix = ""
    if args.source:
        source_suffix = "-" + re.sub(r"[^a-z0-9]+", "-", args.source.casefold()).strip("-")
    output_path = Path(
        args.output or f"res/history/reports/{args.job_type}{source_suffix}.pdf"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(output_path) as pdf:
        pdf.infodict().update({"Title": f"History — {args.job_type}", "Author": "Job listings scraper"})
        dashboard_page(pdf, args.job_type, snapshots)
        monthly_salary_page(pdf, args.job_type, snapshots)
    print(output_path)


if __name__ == "__main__":
    main()
