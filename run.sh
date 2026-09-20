#!/usr/bin/env bash
set -euo pipefail

SOURCE="jjit"
SCRAPER_CONFIG="jjit-scraper-config.json"
ANALYSIS_CONFIG="analysis-config.json"
REPORTER_CONFIG="reporter-config.json"
URL_OVERRIDE=""

usage() {
  cat <<'EOF'
Usage:
  ./run.sh
  ./run.sh -s <jjit|nfj>
  ./run.sh -c <scraper config> -a <analysis config> -r <reporter config>
  ./run.sh -u <url>
  ./run.sh -c <conf file path> -u <url>
  ./run.sh -u <url> -c <conf file path>
EOF
}

while getopts ":s:c:a:r:u:h" opt; do
  case "$opt" in
    s)
      SOURCE="$OPTARG"
      ;;
    c)
      SCRAPER_CONFIG="$OPTARG"
      ;;
    a)
      ANALYSIS_CONFIG="$OPTARG"
      ;;
    r)
      REPORTER_CONFIG="$OPTARG"
      ;;
    u)
      URL_OVERRIDE="$OPTARG"
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

if [ "$SOURCE" = "nfj" ]; then
  SCRAPER="src/nfj_scraper.py"
  if [ "$SCRAPER_CONFIG" = "jjit-scraper-config.json" ]; then
    SCRAPER_CONFIG="nfj-scraper-config.json"
  fi
  if [ "$ANALYSIS_CONFIG" = "analysis-config.json" ]; then
    ANALYSIS_CONFIG="nfj-analysis-config.json"
  fi
  if [ "$REPORTER_CONFIG" = "reporter-config.json" ]; then
    REPORTER_CONFIG="nfj-reporter-config.json"
  fi
elif [ "$SOURCE" = "jjit" ]; then
  SCRAPER="src/jjit_scraper.py"
else
  echo "error: source must be jjit or nfj" >&2
  exit 1
fi

SCRAPER_ARGS=("-c" "$SCRAPER_CONFIG")
if [ -n "$URL_OVERRIDE" ]; then
  SCRAPER_ARGS+=("-u" "$URL_OVERRIDE")
fi

python3 "$SCRAPER" "${SCRAPER_ARGS[@]}"
python3 src/analyzer.py "$ANALYSIS_CONFIG"
python3 src/reporter.py "$REPORTER_CONFIG"

JOB_TYPE="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("job_type", ""))' "$ANALYSIS_CONFIG")"
if [ -n "$JOB_TYPE" ]; then
  python3 src/history_reporter.py "$JOB_TYPE"
fi
