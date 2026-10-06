import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import scraper
import jjit_scraper
import nfj_scraper
from config_entries import load_config_entries, require_unique_values
from workflow_config import load_analysis_entries, load_reporter_entries


class ConfigEntriesTests(unittest.TestCase):
    def write_config(self, directory, document):
        path = Path(directory) / "jobs.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_requires_a_non_empty_listings_array(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {"url": "https://example.com"})
            with self.assertRaisesRegex(ValueError, "non-empty array"):
                load_config_entries(path)

    def test_listings_inherit_shared_settings_and_override_them(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "format": "json",
                "delay_seconds": 0.5,
                "listings": [
                    {"url": "https://example.com/one"},
                    {"url": "https://example.com/two", "delay_seconds": 2},
                ],
            })

            entries = load_config_entries(path)

            self.assertEqual("json", entries[0]["format"])
            self.assertEqual(0.5, entries[0]["delay_seconds"])
            self.assertEqual(2, entries[1]["delay_seconds"])

    def test_duplicate_derived_outputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct `output`"):
            require_unique_values(
                [{"output": "same.json"}, {"output": "same.json"}],
                "output",
            )

    def test_rejects_an_export_format_that_cannot_be_analyzed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "format": "md",
                "listings": [{
                    "url": "https://justjoin.it/job-offers/all-locations/java"
                }],
            })

            with self.assertRaisesRegex(ValueError, "must be `json` or `jsonl`"):
                load_analysis_entries(path)

    def test_downstream_jobs_are_inferred_from_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "salary_units": ["month", "hour"],
                "listings": [
                    {
                        "url": "https://justjoin.it/job-offers/all-locations/c?experience-levels=mid"
                    },
                    {
                        "url": "https://nofluffjobs.com/pl/Python?criteria=seniority%3Djunior"
                    },
                ],
            })

            analyses = load_analysis_entries(path)
            reports = load_reporter_entries(path)

            self.assertEqual("data/jjit-cpp-mid.json", analyses[0]["input"])
            self.assertEqual("res/analysis/jjit-cpp-mid.json", analyses[0]["output"])
            self.assertEqual("cpp-mid", analyses[0]["job_type"])
            self.assertEqual("res/analysis/jjit-cpp-mid.json", reports[0]["input"])
            self.assertEqual("res/reports/jjit-cpp-mid.pdf", reports[0]["output"])
            self.assertEqual("Mid C++ — Just Join IT", reports[0]["title"])
            self.assertEqual(["month", "hour"], reports[0]["salary_units"])
            self.assertEqual("Junior Python — No Fluff Jobs", reports[1]["title"])

    def test_scraper_attempts_later_listing_after_one_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "listings": [
                    {"url": "https://justjoin.it/job-offers/all-locations/java"},
                    {"url": "https://nofluffjobs.com/pl/Python"},
                ],
            })

            with (
                patch.object(sys, "argv", ["scraper.py", "-c", str(path)]),
                patch.object(
                    scraper,
                    "process_entry",
                    side_effect=[ValueError("first failed"), None],
                ) as process,
                redirect_stderr(io.StringIO()),
            ):
                exit_code = scraper.main()

            self.assertEqual(1, exit_code)
            self.assertEqual(2, process.call_count)

    def test_scraper_dispatches_each_url_to_its_site_implementation(self):
        with (
            patch.object(jjit_scraper, "process_config") as process_jjit,
            patch.object(nfj_scraper, "process_config") as process_nfj,
        ):
            scraper.process_entry({
                "url": "https://justjoin.it/job-offers/all-locations/java",
                "data_output": "data/jjit-java.json",
            })
            scraper.process_entry({
                "url": "https://nofluffjobs.com/pl/Python",
                "data_output": "data/nfj-python.json",
            })

        process_jjit.assert_called_once()
        process_nfj.assert_called_once()

    def test_relative_data_output_is_resolved_from_config_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "listings": [{
                    "url": "https://justjoin.it/job-offers/all-locations/java?experience-levels=mid"
                }],
            })

            entry = scraper.resolved_entries(path)[0]

            self.assertEqual(
                str(Path(directory) / "data/jjit-java-mid.json"),
                entry["data_output"],
            )


if __name__ == "__main__":
    unittest.main()
