#!/usr/bin/env bash
# PreToolUse(Skill) hook: before any skill from this plugin loads, make sure
# BigQuery is reachable. Not ready → deny the skill and hand Claude the setup
# steps to give the user. Ready → allow and tell Claude the account/project.
# BQ_SKILLS_PREFLIGHT / EVAL_BQ_PREFLIGHT: off = skip, simulate-fail = act as if not set up (tests).
set -uo pipefail
input="$(cat)"
skill="$(python3 -c 'import json,sys; print((json.loads(sys.argv[1]).get("tool_input") or {}).get("skill",""))' "$input" 2>/dev/null)"

# Only this plugin's skills.
[[ "$skill" =~ ^(bigquery-skills:)?(bq-audit|bigquery(-[a-z-]+)?)$ ]] || exit 0
[[ "${BQ_SKILLS_PREFLIGHT:-on}" == off || "${EVAL_BQ_PREFLIGHT:-on}" == off ]] && exit 0

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${BQ_SKILLS_PREFLIGHT:-}" == simulate-fail || "${EVAL_BQ_PREFLIGHT:-}" == simulate-fail ]]; then
  result='{"ok":false,"account":"","project":"","checks":[{"name":"gcloud","status":"fail","detail":"not installed"}],"fix":["Install the Google Cloud CLI (includes gcloud and bq): https://cloud.google.com/sdk/docs/install","Log in: gcloud auth login"]}'
else
  result="$(bash "$here/../scripts/bq-preflight.sh" --json 2>/dev/null)"
fi

python3 - "$result" "$skill" <<'PY'
import json, sys
raw, skill = sys.argv[1], sys.argv[2]
try:
    d = json.loads(raw)
except Exception:
    d = {"ok": False, "checks": [], "fix": ["Run scripts/bq-preflight.sh from the bigquery-skills plugin to see what is missing"]}
if d.get("ok"):
    proj = d.get("project") or "none set — ask the user which project"
    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "additionalContext": (f"BigQuery preflight OK — account: {d.get('account')}, gcloud default project: {proj}. "
                              "The user's tables may live in another project: if the request doesn't name one, "
                              "ask before assuming the default.")}}
else:
    failed = "; ".join(f"{c['name']}: {c['detail']}" for c in d.get("checks", []) if c.get("status") == "fail")
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(d.get("fix", []), 1))
    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"BigQuery is not set up on this machine, so {skill} was not loaded.\n"
            f"Problem: {failed or 'unknown'}\n"
            f"Setup steps for the user:\n{steps}\n"
            "Tell the user these steps in their language and ask them to run them "
            "(interactive logins can be run with `! gcloud auth login`). Then retry the skill. "
            "Do not run BigQuery commands until setup passes.")}}
print(json.dumps(out))
PY
exit 0
