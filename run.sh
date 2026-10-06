#!/usr/bin/env bash
set -euo pipefail

CONFIG="jobs-config.json"
PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

usage() {
  cat <<'EOF'
Usage:
  ./run.sh
  ./run.sh -c <jobs config>
EOF
}

while getopts ":c:h" opt; do
  case "$opt" in
    c)
      CONFIG="$OPTARG"
      ;;
    h)
      usage
      exit 0
      ;;
    :)
      echo "error: option -$OPTARG requires an argument" >&2
      usage >&2
      exit 1
      ;;
    \?)
      echo "error: unknown option -$OPTARG" >&2
      usage >&2
      exit 1
      ;;
  esac
done

shift $((OPTIND - 1))
if [ "$#" -ne 0 ]; then
  echo "error: unexpected positional arguments: $*" >&2
  usage >&2
  exit 1
fi

"$PYTHON_BIN" src/scraper.py -c "$CONFIG"
"$PYTHON_BIN" src/analyzer.py "$CONFIG"
"$PYTHON_BIN" src/reporter.py "$CONFIG"

while IFS= read -r JOB_TYPE; do
  "$PYTHON_BIN" src/history_reporter.py "$JOB_TYPE"
done < <(PYTHONPATH=src "$PYTHON_BIN" -c '
import sys
from pathlib import Path
from workflow_config import load_analysis_entries
entries = load_analysis_entries(Path(sys.argv[1]))
print("\n".join(dict.fromkeys(item["job_type"] for item in entries)))
' "$CONFIG")
