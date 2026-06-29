#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="jjit-scraper-config.json"
URL_OVERRIDE=""

usage() {
  cat <<'EOF'
Usage:
  ./run.sh
  ./run.sh -c <conf file path>
  ./run.sh -u <url>
  ./run.sh -c <conf file path> -u <url>
  ./run.sh -u <url> -c <conf file path>
EOF
}

while getopts ":c:u:h" opt; do
  case "$opt" in
    c)
      CONFIG_PATH="$OPTARG"
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

SCRAPER_ARGS=("-c" "$CONFIG_PATH")
if [ -n "$URL_OVERRIDE" ]; then
  SCRAPER_ARGS+=("-u" "$URL_OVERRIDE")
fi

python3 src/jjit_scraper.py "${SCRAPER_ARGS[@]}"
python3 src/analyzer.py
python3 src/reporter.py
