#!/usr/bin/env bash
# SessionStart hook: tell Claude this user works with BigQuery, so questions
# about tables/SQL that don't say "BigQuery" still reach the plugin's skills.
# Local checks only (no network) to keep startup fast.
set -uo pipefail
[[ "${BQ_SKILLS_SESSION_HINT:-on}" == off || "${EVAL_BQ_SESSION_HINT:-on}" == off ]] && exit 0
# Read gcloud's config files directly; invoking gcloud costs ~1-2 s per call.
python3 - "$(command -v gcloud || true)" "$(command -v bq || true)" <<'PY'
import configparser, json, os, sys
gcloud, bq = sys.argv[1], sys.argv[2]
cfg_dir = os.environ.get("CLOUDSDK_CONFIG") or os.path.expanduser("~/.config/gcloud")
account = project = ""
try:
    name = open(os.path.join(cfg_dir, "active_config")).read().strip() or "default"
    cp = configparser.ConfigParser()
    cp.read(os.path.join(cfg_dir, "configurations", f"config_{name}"))
    account = cp.get("core", "account", fallback="")
    project = cp.get("core", "project", fallback="")
except OSError:
    pass
if not account and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    account = "service account key"
checks = []
if not gcloud: checks.append({"name": "gcloud", "status": "fail", "detail": "not installed"})
if gcloud and not bq: checks.append({"name": "bq", "status": "fail", "detail": "not installed"})
if gcloud and not account: checks.append({"name": "auth", "status": "fail", "detail": "no active account"})
d = {"ok": not checks, "account": account, "project": project, "checks": checks}
route = ("The bigquery-skills plugin is installed: when the user asks about tables, datasets, SQL, "
         "partitioning, query cost or failing jobs without naming a database, treat it as Google BigQuery "
         "unless the repository or conversation clearly shows another engine, and use the matching "
         "bigquery-skills skill.")
if os.environ.get("BQ_SKILLS_SESSION_HINT") == "route-only" or os.environ.get("EVAL_BQ_SESSION_HINT") == "route-only":
    d["account"] = d["project"] = ""
if d.get("ok") and d.get("account"):
    ctx = (f"{route} gcloud account: {d.get('account')}; default project: {d.get('project') or 'not set'} "
           "(the user's tables may be in another project: ask when unsure).")
elif d.get("ok"):
    ctx = route
else:
    problems = "; ".join(f"{c['name']}: {c['detail']}" for c in d.get("checks", []) if c.get("status") == "fail")
    ctx = f"{route} BigQuery is not set up on this machine yet ({problems}); the skills will ask the user to set it up."
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
PY
exit 0
