import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from input_data import InputDataError, load_document
from history_csv import job_type_from_url


class InputDataTests(unittest.TestCase):
    def test_loads_json_lines_as_offers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offers.jsonl"
            path.write_text('{"job_name": "Java Developer"}\n{"job_name": "C++ Developer"}\n')
            self.assertEqual(2, len(load_document(path)["offers"]))

    def test_rejects_non_object_offer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offers.json"
            path.write_text(json.dumps(["not an offer"]))
            with self.assertRaises(InputDataError):
                load_document(path)

    def test_decodes_c_plus_plus_url_for_history_filename(self):
        self.assertEqual(
            "cpp-mid",
            job_type_from_url(
                "https://nofluffjobs.com/pl/C%2B%2B?criteria=seniority%3Dmid"
            ),
        )


if __name__ == "__main__":
    unittest.main()
