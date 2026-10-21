#!/usr/bin/env bash
# Check that this machine can reach BigQuery.
#
#   bq-preflight.sh [--project P] [--json] [--no-cache] [--quick]
#
# --quick: local checks only (CLI installed, active account, default project);
#          no network calls. Used at session start.
#
# Exit 0 when ready, 1 when setup is missing. Prints a human summary, or with
# --json one object: {"ok", "account", "project", "checks": [...], "fix": [...]}.
# Read-only: runs `gcloud auth list`, `gcloud config get-value`,
# `gcloud auth print-access-token` and `bq ls` (listing is free).
# Results are cached for 10 minutes per project.
set -uo pipefail

PROJECT=""; JSON=0; CACHE=1; QUICK=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --json) JSON=1; shift ;;
    --no-cache) CACHE=0; shift ;;
    --quick) QUICK=1; CACHE=0; shift ;;
    *) shift ;;
  esac
done

CACHE_DIR="${TMPDIR:-/tmp}/bigquery-skills-preflight-$(id -u)"
CACHE_FILE="$CACHE_DIR/${PROJECT:-default}.json"
if [[ $CACHE -eq 1 && -f "$CACHE_FILE" ]] && [[ $(( $(date +%s) - $(stat -c %Y "$CACHE_FILE" 2>/dev/null || stat -f %m "$CACHE_FILE") )) -lt 600 ]]; then
  OUT="$(cat "$CACHE_FILE")"
else
  checks=(); fix=(); ok=1; account=""

  add() { checks+=("$1|$2|$3"); }   # name|pass/fail/warn|detail

  if command -v gcloud >/dev/null 2>&1; then add gcloud pass "$(gcloud --version 2>/dev/null | head -1)"
  else add gcloud fail "not installed"; ok=0
       fix+=("Install the Google Cloud CLI (includes gcloud and bq): https://cloud.google.com/sdk/docs/install")
  fi
  if command -v bq >/dev/null 2>&1; then add bq pass "$(bq version 2>/dev/null | tail -1)"
  elif command -v gcloud >/dev/null 2>&1; then add bq fail "not installed"; ok=0
       fix+=("Install the bq component: gcloud components install bq")
  fi

  if [[ $ok -eq 1 ]]; then
    account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1)"
    if [[ -z "$account" && -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
      account="(service account key: $GOOGLE_APPLICATION_CREDENTIALS)"
    fi
    if [[ -z "$account" ]]; then
      add auth fail "no active account"; ok=0
      fix+=("Log in: gcloud auth login   (or for a service account: gcloud auth activate-service-account --key-file=KEY.json)")
    elif [[ $QUICK -eq 0 ]] && ! gcloud auth print-access-token >/dev/null 2>&1; then
      add auth fail "$account: credentials expired or need re-authentication"; ok=0
      fix+=("Refresh credentials: gcloud auth login")
    else
      add auth pass "$account"
    fi
  fi

  if [[ $ok -eq 1 && -z "$PROJECT" ]]; then
    PROJECT="$(gcloud config get-value project 2>/dev/null)"
  fi
  if [[ $ok -eq 1 && $QUICK -eq 1 ]]; then
    add project "$([[ -n "$PROJECT" ]] && echo pass || echo warn)" "${PROJECT:-no default project}"
  elif [[ $ok -eq 1 ]]; then
    if [[ -z "$PROJECT" ]]; then
      add project warn "no default project"
      fix+=("Set a default project (optional): gcloud config set project PROJECT_ID — or name the project in your request")
      # Still verify the API is reachable by listing projects.
      if err="$(bq --quiet --headless ls -p --max_results=1 2>&1)"; then add bigquery pass "API reachable"
      else add bigquery fail "$(tr '\n' ' ' <<<"$err" | cut -c1-200)"; ok=0; fi
    elif err="$(bq --quiet --headless --project_id="$PROJECT" ls --max_results=1 2>&1)"; then
      add project pass "$PROJECT"; add bigquery pass "can list datasets in $PROJECT"
    else
      add project pass "$PROJECT"
      msg="$(tr '\n' ' ' <<<"$err" | cut -c1-200)"
      add bigquery fail "$msg"; ok=0
      case "$(tr 'A-Z' 'a-z' <<<"$msg")" in
        *"has not been used"*|*"is disabled"*|*service_disabled*)
          fix+=("Enable the BigQuery API: gcloud services enable bigquery.googleapis.com --project=$PROJECT") ;;
        *"access denied"*|*"does not have"*|*permission_denied*|*"403"*)
          fix+=("Ask a project admin to grant $account at least roles/bigquery.jobUser and roles/bigquery.dataViewer (or roles/bigquery.metadataViewer) on $PROJECT") ;;
        *"not found"*|*"404"*)
          fix+=("Check the project ID: gcloud projects list") ;;
        *) fix+=("Run: bq --project_id=$PROJECT ls   and fix the error it prints") ;;
      esac
    fi
  fi

  OUT="$(python3 - "$ok" "$account" "$PROJECT" "${checks[@]+"${checks[@]}"}" -- "${fix[@]+"${fix[@]}"}" <<'PY'
import json, sys
a = sys.argv[1:]
ok, account, project = a[0] == "1", a[1], a[2]
rest = a[3:]
sep = rest.index("--") if "--" in rest else len(rest)
checks = [dict(zip(("name", "status", "detail"), c.split("|", 2))) for c in rest[:sep]]
fix = rest[sep + 1:]
print(json.dumps({"ok": ok, "account": account, "project": project, "checks": checks, "fix": fix}))
PY
)"
  # Cache successes only, so a fixed setup is picked up immediately.
  if [[ $QUICK -eq 1 ]]; then :
  elif [[ $ok -eq 1 ]]; then mkdir -p "$CACHE_DIR" && printf '%s' "$OUT" > "$CACHE_FILE"; else rm -f "$CACHE_FILE"; fi
fi

if [[ $JSON -eq 1 ]]; then
  printf '%s\n' "$OUT"
else
  python3 - "$OUT" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
mark = {"pass": "✓", "fail": "✗", "warn": "!"}
for c in d["checks"]:
    print(f"  {mark.get(c['status'], '?')} {c['name']:<9} {c['detail']}")
if d["fix"]:
    print("\nTo fix:")
    for i, f in enumerate(d["fix"], 1):
        print(f"  {i}. {f}")
print("\nBigQuery: READY" if d["ok"] else "\nBigQuery: NOT READY")
PY
fi
python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.argv[1])["ok"] else 1)' "$OUT"
