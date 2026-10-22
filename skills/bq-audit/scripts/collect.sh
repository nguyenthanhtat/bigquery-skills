#!/usr/bin/env bash
# Read-only BigQuery audit collector.
#
#   collect.sh plan --project P --region R [--days N]
#       Dry-runs every collector and prints the bytes each would bill. Costs nothing.
#   collect.sh run  --project P --region R [--days N] [--max-gb G] [--out DIR]
#       Runs the collectors and writes raw JSON to DIR/raw/.
#
# Safety:
#   * Only the SELECT statements in ../sql/ are ever executed; each is checked
#     for write keywords before it is sent.
#   * Every query is dry-run first and runs with --maximum_bytes_billed.
#   * Every job is labelled tool=bq-audit so the audit never audits itself.
#   * Non-SQL collectors use read-only commands only (bq show / bq ls / gcloud get-iam-policy).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_DIR="$HERE/../sql"

MODE="${1:-}"; shift || true
PROJECT=""; REGION=""; DAYS=30; MAX_GB=50; OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --region)  REGION="$2";  shift 2 ;;
    --days)    DAYS="$2";    shift 2 ;;
    --max-gb)  MAX_GB="$2";  shift 2 ;;
    --out)     OUT="$2";     shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
[[ "$MODE" == plan || "$MODE" == run ]] || die "usage: collect.sh plan|run --project P --region R [--days N] [--max-gb G] [--out DIR]"
[[ -n "$PROJECT" && -n "$REGION" ]] || die "--project and --region are required"
[[ "$PROJECT" =~ ^[a-z0-9:.-]+$ ]] || die "invalid project id: $PROJECT"
[[ "$REGION" =~ ^[A-Za-z0-9-]+$ ]] || die "invalid region: $REGION"
[[ "$DAYS" =~ ^[0-9]+$ && "$DAYS" -ge 1 && "$DAYS" -le 180 ]] || die "--days must be 1..180 (JOBS keeps 180 days)"
[[ "$MAX_GB" =~ ^[0-9]+$ ]] || die "--max-gb must be an integer"
command -v bq >/dev/null || die "bq CLI not found. Install the Google Cloud CLI: https://cloud.google.com/sdk/docs/install"
command -v python3 >/dev/null || die "python3 not found"

REGION_Q="region-$(echo "$REGION" | tr 'A-Z' 'a-z')"
MAX_BYTES=$(( MAX_GB * 1024 * 1024 * 1024 ))
JOBS_FILTER="$(cat "$SQL_DIR/_jobs_filter.inc")"
BQ=(bq --quiet --headless --project_id="$PROJECT" --location="$REGION")

render() {
  python3 - "$1" "$PROJECT" "$REGION_Q" "$DAYS" "$JOBS_FILTER" <<'PY'
import sys
path, project, region_q, days, jobs_filter = sys.argv[1:6]
sql = open(path, encoding="utf-8").read()
sql = sql.replace("{{JOBS_FILTER}}", jobs_filter)
sql = sql.replace("{{PROJECT}}", project).replace("{{REGION_Q}}", region_q).replace("{{DAYS}}", days)
# Drop full-line comments: bq parses a leading "--" as a command-line flag.
sql = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
sys.stdout.write(sql)
PY
}

assert_read_only() {
  # Strip comments, then require a single SELECT/WITH statement with no write keywords.
  local body
  body="$(sed -e 's/--.*$//' <<<"$1" | tr '\n' ' ')"
  grep -qiE '^[[:space:]]*(SELECT|WITH)[[:space:]]' <<<"$body" || die "collector is not a SELECT: $2"
  if grep -qiE '\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|EXPORT|CALL|EXECUTE|DECLARE|SET)\b' <<<"$body"; then
    die "collector contains a write keyword, refusing: $2"
  fi
  [[ "$(tr -cd ';' <<<"$body" | wc -c)" -le 1 ]] || die "collector has multiple statements: $2"
}

dry_run_bytes() {
  # Prints totalBytesProcessed, or "ERR:<message>" when the dry run fails (e.g. missing permission).
  local out
  if out="$("${BQ[@]}" --format=json query --use_legacy_sql=false --dry_run "$1" 2>&1)"; then
    python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d.get("statistics",{}).get("totalBytesProcessed","0"))' "$out" 2>/dev/null \
      || echo "0"
  else
    echo "ERR:$(tr '\n' ' ' <<<"$out" | cut -c1-300)"
  fi
}

human() { python3 -c 'import sys; b=int(sys.argv[1]); print(f"{b/1024**3:.2f} GiB" if b>=1024**3 else f"{b/1024**2:.1f} MiB")' "$1"; }

COLLECTORS=()
for f in "$SQL_DIR"/*.sql; do COLLECTORS+=("$(basename "$f" .sql)"); done

if [[ "$MODE" == run ]]; then
  OUT="${OUT:-./bq-audit-$PROJECT-$(date +%Y%m%d)}"
  mkdir -p "$OUT/raw"
fi

echo "Project: $PROJECT   Region: $REGION ($REGION_Q)   Window: $DAYS days   Per-query cap: ${MAX_GB} GiB"
echo
TOTAL=0
STATUS_FILE="$(mktemp)"; trap 'rm -f "$STATUS_FILE"' EXIT
set_status() { printf '%s\t%s\n' "$1" "$2" >> "$STATUS_FILE"; }
get_status() { awk -F'\t' -v k="$1" '$1==k {v=$2} END {print v}' "$STATUS_FILE"; }
for name in "${COLLECTORS[@]}"; do
  sql="$(render "$SQL_DIR/$name.sql")"
  assert_read_only "$sql" "$name"
  est="$(dry_run_bytes "$sql")"
  if [[ "$est" == ERR:* ]]; then
    printf "  %-20s SKIP  %s\n" "$name" "${est#ERR:}"
    set_status "$name" "skipped: ${est#ERR:}"
    continue
  fi
  TOTAL=$(( TOTAL + est ))
  if [[ "$MODE" == plan ]]; then
    printf "  %-20s %s\n" "$name" "$(human "$est")"
    set_status "$name" "planned"
    continue
  fi
  if (( est > MAX_BYTES )); then
    printf "  %-20s SKIP  would bill %s, above --max-gb\n" "$name" "$(human "$est")"
    set_status "$name" "skipped: above cap ($est bytes)"
    continue
  fi
  if "${BQ[@]}" --format=json query --use_legacy_sql=false --max_rows=10000 \
       --maximum_bytes_billed="$MAX_BYTES" --label=tool:bq-audit \
       "$sql" > "$OUT/raw/$name.json" 2> "$OUT/raw/$name.err"; then
    rm -f "$OUT/raw/$name.err"
    printf "  %-20s ok    %s\n" "$name" "$(human "$est")"
    set_status "$name" "ok"
  else
    printf "  %-20s FAIL  %s\n" "$name" "$(head -c 200 "$OUT/raw/$name.err" | tr '\n' ' ')"
    set_status "$name" "failed"
  fi
done
echo
echo "Estimated bytes for SQL collectors: $(human "$TOTAL")  (on-demand list price ≈ \$$(python3 -c "print(f'{$TOTAL/1024**4*6.25:.4f}')"))"

if [[ "$MODE" == plan ]]; then
  echo "Plan only — nothing was run. Re-run with 'run' to collect."
  exit 0
fi

# Non-SQL collectors (read-only). Failures are recorded, not fatal.
echo
datasets="$(python3 -c 'import json,sys
try: print("\n".join(r["dataset"] for r in json.load(open(sys.argv[1]))))
except Exception: pass' "$OUT/raw/datasets.json")"
{
  echo "["; first=1
  for ds in $(head -n 1000 <<<"$datasets"); do
    if acl="$("${BQ[@]}" --format=json show --dataset "$PROJECT:$ds" 2>/dev/null)"; then
      [[ $first -eq 1 ]] || echo ","; first=0
      python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(json.dumps({"dataset":sys.argv[2],"access":d.get("access",[]),"labels":d.get("labels",{}),"defaultEncryptionConfiguration":d.get("defaultEncryptionConfiguration")}))' "$acl" "$ds"
    fi
  done
  echo "]"
} > "$OUT/raw/dataset_acl.json" && set_status "dataset_acl" "ok"
printf "  %-20s %s\n" dataset_acl "$(s=$(get_status dataset_acl); echo "${s:-failed}")"

if command -v gcloud >/dev/null && gcloud projects get-iam-policy "$PROJECT" --format=json > "$OUT/raw/project_iam.json" 2> "$OUT/raw/project_iam.err"; then
  rm -f "$OUT/raw/project_iam.err"; set_status "project_iam" "ok"
else
  rm -f "$OUT/raw/project_iam.json"; set_status "project_iam" "skipped: no permission or gcloud missing"
fi
printf "  %-20s %s\n" project_iam "$(get_status project_iam)"

if "${BQ[@]}" --format=json ls --transfer_config --transfer_location="$(echo "$REGION" | tr 'A-Z' 'a-z')" > "$OUT/raw/transfer_configs.json" 2> "$OUT/raw/transfer_configs.err"; then
  rm -f "$OUT/raw/transfer_configs.err"; set_status "transfer_configs" "ok"
else
  rm -f "$OUT/raw/transfer_configs.json"; set_status "transfer_configs" "skipped: Data Transfer API disabled or no permission"
fi
printf "  %-20s %s\n" transfer_configs "$(get_status transfer_configs)"

# Manifest for the analyzer.
{
  printf '{"project":"%s","region":"%s","days":%s,"collected_at":"%s","collectors":{' \
    "$PROJECT" "$REGION" "$DAYS" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 -c 'import json,sys
d={}
for line in open(sys.argv[1], encoding="utf-8"):
    k, _, v = line.rstrip("\n").partition("\t")
    d[k] = v
sys.stdout.write(json.dumps(d)[1:-1])' "$STATUS_FILE"
  printf '}}\n'
} > "$OUT/manifest.json"
echo
echo "Raw data written to $OUT"
