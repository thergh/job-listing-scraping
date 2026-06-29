#!/usr/bin/env python3

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean


TITLE_STOP_WORDS = {
    "a", "an", "and", "or", "the", "of", "for", "with", "in", "on",
    "at", "to", "from", "by", "via", "is", "as",
    "senior", "junior", "mid", "middle", "regular", "lead", "level",
    "remote", "hybrid", "onsite", "poland",
    "m", "f", "x", "k", "n", "he", "she", "they"
}

UNIT_ALIASES = {
    "h": "hour",
    "hr": "hour",
    "hourly": "hour",
    "hours": "hour",
    "daily": "day",
    "days": "day",
    "monthly": "month",
    "months": "month",
    "yearly": "year",
    "years": "year"
}


def normalize(value):
    text = html.unescape(str(value or "")).casefold()
    return re.sub(r"\s+", " ", text).strip()


def parse_number(value):
    if value is None:
        return None

    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def extract_title_keywords(title):
    text = normalize(title)
    text = re.sub(r"[-/&|,+(){}\[\]:;–—]", " ", text)

    words = re.findall(
        r"[a-ząćęłńóśźż0-9]+(?:[.#][a-ząćęłńóśźż0-9+]*)*",
        text
    )

    return {
        word
        for word in words
        if len(word) >= 2
        and not word.isdigit()
        and word not in TITLE_STOP_WORDS
    }


def is_skill_noise(skill):
    if not skill or skill == "undisclosed salary":
        return True

    if re.fullmatch(r"[\d\s.,-]+", skill):
        return True

    if re.fullmatch(
        r"[a-z]{3}/(?:h|hour|day|month|year)",
        skill
    ):
        return True

    return False


def normalize_unit(value):
    unit = normalize(value) or "unknown"
    return UNIT_ALIASES.get(unit, unit)


def create_ranking(counter, postings_total):
    return [
        {
            "keyword": keyword,
            "count": count,
            "percentage": round(
                count / postings_total * 100,
                2
            ) if postings_total else 0.0
        }
        for keyword, count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0])
        )
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config",
        nargs="?",
        default="analysis-config.json"
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    project_root = config_path.parent

    config = json.loads(
        config_path.read_text(encoding="utf-8")
    )

    input_path = project_root / config["input"]
    output_path = project_root / config.get(
        "output",
        "res/analysis.json"
    )

    document = json.loads(
        input_path.read_text(encoding="utf-8")
    )

    if isinstance(document, list):
        postings = document
    else:
        postings = document.get("offers")

    if not isinstance(postings, list):
        raise ValueError(
            'Input JSON must be an array or contain an "offers" array'
        )

    title_counts = Counter()
    skill_counts = Counter()

    salary_groups = defaultdict(list)
    salary_posting_ids = defaultdict(set)
    postings_with_any_salary = set()

    for posting_id, posting in enumerate(postings):
        for keyword in extract_title_keywords(
            posting.get("job_name", "")
        ):
            title_counts[keyword] += 1

        skills = posting.get("required_skills", [])

        if not isinstance(skills, list):
            skills = [skills]

        unique_skills = {
            normalize(skill)
            for skill in skills
        }

        for skill in unique_skills:
            if not is_skill_noise(skill):
                skill_counts[skill] += 1

        contracts = posting.get("type_of_contract", [])

        if not isinstance(contracts, list):
            contracts = [contracts]

        salary_entries = posting.get("salary", [])

        if not isinstance(salary_entries, list):
            salary_entries = [salary_entries]

        for salary in salary_entries:
            if not isinstance(salary, dict):
                continue

            salary_min = parse_number(salary.get("from"))
            salary_max = parse_number(salary.get("to"))

            if salary_min is None or salary_max is None:
                continue

            contract_type = salary.get("contract_type")

            if not contract_type and len(contracts) == 1:
                contract_type = contracts[0]

            key = (
                normalize(salary.get("currency") or "unknown").upper(),
                normalize(contract_type or "unknown"),
                normalize_unit(salary.get("unit"))
            )

            salary_groups[key].append(
                (salary_min, salary_max)
            )
            salary_posting_ids[key].add(posting_id)
            postings_with_any_salary.add(posting_id)

    salary_statistics = []

    for key, salaries in sorted(salary_groups.items()):
        currency, contract_type, unit = key

        minimums = [salary[0] for salary in salaries]
        maximums = [salary[1] for salary in salaries]
        averages = [
            (salary_min + salary_max) / 2
            for salary_min, salary_max in salaries
        ]

        salary_statistics.append({
            "currency": currency,
            "contract_type": contract_type,
            "unit": unit,
            "postings_with_salary": len(
                salary_posting_ids[key]
            ),
            "salary_ranges": len(salaries),
            "avg_salary_min": round(fmean(minimums), 2),
            "avg_salary_max": round(fmean(maximums), 2),
            "avg_salary": round(fmean(averages), 2)
        })

    result = {
        "source": config["input"],
        "source_url": document.get("source_url")
        if isinstance(document, dict) else None,
        "postings_total": len(postings),
        "postings_with_salary": len(postings_with_any_salary),
        "salary_coverage_percentage": round(
            len(postings_with_any_salary) / len(postings) * 100,
            2
        ) if postings else 0.0,
        "salary_statistics": salary_statistics,
        "job_title_keywords": create_ranking(
            title_counts,
            len(postings)
        ),
        "skill_keywords": create_ranking(
            skill_counts,
            len(postings)
        )
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Analyzed {len(postings)} postings")
    print(f"Result: {output_path}")


if __name__ == "__main__":
    main()