#!/usr/bin/env python3
"""Turn raw collector output into metrics and candidate findings.

    analyze.py AUDIT_DIR [--pricing PATH]

Reads AUDIT_DIR/raw/*.json (written by collect.sh) and writes:
    AUDIT_DIR/analysis/<area>.json   metrics + candidate findings per area
    AUDIT_DIR/analysis/summary.json  headline numbers and scores

All arithmetic lives here so the numbers in the report are reproducible.
Candidates are deliberately conservative; the analyst agents confirm,
enrich or drop them. Standard library only.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

GIB = 1024 ** 3
TIB = 1024 ** 4
HERE = Path(__file__).resolve().parent

SEVERITY_WEIGHT = {"critical": 25, "high": 12, "medium": 5, "low": 2, "info": 0}
AREAS = ["cost", "performance", "schema", "security", "reliability"]


# ---------- helpers ----------

def load(raw, name, default=None):
    p = raw / f"{name}.json"
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8") or "null")
    except json.JSONDecodeError:
        return default


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def ts(v):
    """bq prints timestamps as epoch seconds or 'YYYY-MM-DD HH:MM:SS[.ffffff]' strings."""
    if v in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(v), tz=timezone.utc)
    except (TypeError, ValueError):
        pass
    s = str(v).replace(" UTC", "").replace("T", " ").split("+")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def gib(b):
    return round(num(b) / GIB, 2)


def fqn(*parts):
    return ".".join(p for p in parts if p)


class Findings:
    def __init__(self, area):
        self.area = area
        self.items = []

    def add(self, check, severity, title, evidence, objects=None, savings=None,
            hint="", confidence="high"):
        self.items.append({
            "id": f"{self.area[:3].upper()}-{check}-{len(self.items) + 1:02d}",
            "area": self.area,
            "check": check,
            "severity": severity,
            "title": title,
            "evidence": evidence,
            "objects": objects or [],
            "est_monthly_savings_usd": round(savings, 2) if savings else None,
            "recommendation_hint": hint,
            "confidence": confidence,
        })


def score(items):
    penalty = sum(SEVERITY_WEIGHT[i["severity"]] for i in items)
    return max(0, 100 - penalty)


# ---------- areas ----------

def analyze_cost(d, price, ctx):
    f = Findings("cost")
    ov = ctx["overview"]
    rate = price["on_demand_per_tib"]
    per_month = ctx["per_month"]

    ov_cost = ov["bytes_billed"] / TIB * rate * per_month
    metrics = {
        "on_demand_query_cost_month_usd": round(ov_cost, 2),
        "slot_hours_month": round(ov["slot_ms"] / 3.6e6 * per_month, 1),
        "on_demand_job_share": round(ov["on_demand_jobs"] / ov["jobs"], 3) if ov["jobs"] else None,
        "cache_hit_rate": round(ov["cache_hits"] / ov["jobs"], 3) if ov["jobs"] else None,
    }

    # Query spend concentration by pattern.
    patterns = d.get("top_query_patterns") or []
    total_billed = ov["bytes_billed"] or 1
    for p in patterns[:20]:
        share = num(p.get("bytes_billed")) / total_billed
        runs = int(num(p.get("runs")))
        cost = num(p.get("bytes_billed")) / TIB * rate * per_month
        if share >= 0.20 and cost >= 50:
            f.add("C2", "high" if cost >= 500 else "medium",
                  f"One query pattern drives {share:.0%} of query spend (~${cost:,.0f}/month)",
                  {"query_hash": p.get("query_hash"), "runs": runs, "share": round(share, 3),
                   "gib_billed": gib(p.get("bytes_billed")), "cache_hits": int(num(p.get("cache_hits"))),
                   "sample_job_id": p.get("sample_job_id"), "referenced_tables": p.get("referenced_tables")},
                  objects=[p.get("sample_job_id")], savings=cost * 0.5,
                  hint="Tune this query first (see performance findings for the same hash); "
                       "consider a summary table or materialized view if it runs on a schedule.",
                  confidence="medium")

    # Single very large jobs → missing guardrails.
    big = [p for p in patterns if num(p.get("max_bytes_billed")) >= TIB]
    if big:
        f.add("C4", "high", f"{len(big)} query pattern(s) billed over 1 TiB in a single run",
              {"patterns": [{"query_hash": p.get("query_hash"), "max_tib": round(num(p.get("max_bytes_billed")) / TIB, 2),
                             "sample_user": p.get("sample_user")} for p in big[:10]]},
              hint="Set maximum_bytes_billed on scheduled/app queries and custom quotas "
                   "(QueryUsagePerDay, QueryUsagePerUserPerDay) so one mistake can't burn the budget.")

    # Spend concentration by principal.
    users = d.get("cost_by_user") or []
    for u in users[:5]:
        share = num(u.get("bytes_billed")) / total_billed
        if share >= 0.40 and ov_cost >= 50:
            f.add("C3", "medium", f"{u.get('user_email')} accounts for {share:.0%} of query spend",
                  {"user": u.get("user_email"), "jobs": int(num(u.get("jobs"))), "share": round(share, 3),
                   "gib_billed": gib(u.get("bytes_billed"))},
                  objects=[u.get("user_email")],
                  hint="Confirm this principal's workload is expected; give it a per-user custom quota "
                       "and label its jobs for attribution.",
                  confidence="medium")

    # Storage billing model per dataset.
    storage = d.get("table_storage") or []
    datasets = {r.get("dataset"): r for r in (d.get("datasets") or [])}
    by_ds = {}
    for t in storage:
        ds = t.get("table_schema")
        a = by_ds.setdefault(ds, {k: 0.0 for k in (
            "active_logical", "long_logical", "active_physical", "long_physical", "time_travel", "fail_safe")})
        a["active_logical"] += num(t.get("active_logical_bytes"))
        a["long_logical"] += num(t.get("long_term_logical_bytes"))
        a["active_physical"] += num(t.get("active_physical_bytes"))
        a["long_physical"] += num(t.get("long_term_physical_bytes"))
        a["time_travel"] += num(t.get("time_travel_physical_bytes"))
        a["fail_safe"] += num(t.get("fail_safe_physical_bytes"))
    storage_month = 0.0
    switch_candidates = []
    for ds, a in by_ds.items():
        logical = (a["active_logical"] * price["logical_active_per_gib"] + a["long_logical"] * price["logical_longterm_per_gib"]) / GIB
        # Physical model bills time travel and fail-safe on top; active_physical already includes time travel.
        physical = ((a["active_physical"] + a["fail_safe"]) * price["physical_active_per_gib"]
                    + a["long_physical"] * price["physical_longterm_per_gib"]) / GIB
        model = (datasets.get(ds, {}).get("storage_billing_model") or "LOGICAL").strip('"').upper()
        current = physical if model == "PHYSICAL" else logical
        storage_month += current
        other = logical if model == "PHYSICAL" else physical
        if current - other >= 20 and other < current * 0.8:
            switch_candidates.append({"dataset": ds, "current_model": model, "current_usd_month": round(current, 2),
                                      "alternative_usd_month": round(other, 2),
                                      "time_travel_gib": gib(a["time_travel"])})
    metrics["storage_cost_month_usd"] = round(storage_month, 2)
    if switch_candidates:
        saving = sum(c["current_usd_month"] - c["alternative_usd_month"] for c in switch_candidates)
        f.add("C5", "medium" if saving < 500 else "high",
              f"Switching storage billing model on {len(switch_candidates)} dataset(s) saves ~${saving:,.0f}/month",
              {"datasets": sorted(switch_candidates, key=lambda c: c["alternative_usd_month"] - c["current_usd_month"])[:20]},
              objects=[c["dataset"] for c in switch_candidates], savings=saving,
              hint="ALTER SCHEMA ... SET OPTIONS(storage_billing_model='PHYSICAL'|'LOGICAL'). "
                   "Takes effect in ~24h and cannot be changed again for 14 days. Under PHYSICAL, also "
                   "consider lowering max_time_travel_hours (min 48).")

    # Unreferenced large tables (review, never delete automatically).
    usage = {fqn(u.get("dataset_id"), u.get("table_id")) for u in (d.get("table_usage") or [])}
    now = ctx["now"]
    stale = []
    for t in storage:
        size = num(t.get("total_logical_bytes"))
        key = fqn(t.get("table_schema"), t.get("table_name"))
        last_mod = ts(t.get("storage_last_modified_time"))
        if size >= GIB and key not in usage and last_mod and (now - last_mod).days >= ctx["days"]:
            stale.append({"table": key, "gib": gib(size), "last_modified": last_mod.date().isoformat()})
    if stale:
        stale.sort(key=lambda s: -s["gib"])
        gib_total = sum(s["gib"] for s in stale)
        saving = gib_total * price["logical_longterm_per_gib"]
        f.add("C6", "low" if gib_total < 1024 else "medium",
              f"{len(stale)} tables ({gib_total:,.0f} GiB) were neither queried in this project nor modified in {ctx['days']} days",
              {"tables": stale[:30]}, objects=[s["table"] for s in stale[:30]], savings=saving,
              hint="REVIEW ONLY. JOBS_BY_PROJECT does not see reads from other projects, BI tools using "
                   "other projects, or exports. Confirm with owners; prefer setting an expiration or "
                   "archiving to GCS over deleting.",
              confidence="low")

    # Many tiny queries: each referenced table is billed at least 10 MiB.
    if ov["jobs"] >= 1000 and ov["bytes_processed"] > 0:
        ratio = ov["bytes_billed"] / ov["bytes_processed"]
        overhead = (ov["bytes_billed"] - ov["bytes_processed"]) / TIB * rate * per_month
        if ratio >= 3 and overhead >= 10:
            f.add("C9", "medium" if overhead >= 100 else "low",
                  f"Billed bytes are {ratio:.0f}× processed bytes: ~${overhead:,.0f}/month is the 10 MiB per-table minimum",
                  {"jobs": int(ov["jobs"]), "gib_billed": gib(ov["bytes_billed"]),
                   "gib_processed": gib(ov["bytes_processed"]), "ratio": round(ratio, 1),
                   "avg_mib_processed_per_job": round(ov["bytes_processed"] / ov["jobs"] / 1024 ** 2, 2)},
                  savings=overhead * 0.7,
                  hint="Workload is many small queries (lookups, per-event checks, polling). Batch them into "
                       "fewer queries, cache results in the app, move point lookups to a serving store, "
                       "or put this workload on a small reservation where the minimum does not apply. "
                       "Find the callers in cost_by_user and top_query_patterns.",
                  confidence="medium")

    # On-demand vs editions (rough).
    if ov["jobs"] and metrics["on_demand_job_share"] and metrics["on_demand_job_share"] > 0.9 and ov_cost >= 200:
        editions = metrics["slot_hours_month"] * price["editions_standard_per_slot_hour"]
        if editions < ov_cost * 0.6:
            f.add("C8", "medium", f"Editions could be cheaper than on-demand (~${editions:,.0f} vs ${ov_cost:,.0f}/month)",
                  {"slot_hours_month": metrics["slot_hours_month"], "on_demand_usd": round(ov_cost, 2),
                   "standard_edition_usd_estimate": round(editions, 2)},
                  savings=ov_cost - editions,
                  hint="Rough estimate from consumed slot-hours; autoscaling bills in 1-minute/50-slot "
                       "increments and needs a max-slots cap. Pilot a reservation on one workload first.",
                  confidence="low")

    return metrics, f.items


def analyze_performance(d, price, ctx):
    f = Findings("performance")
    storage = {fqn(t.get("table_schema"), t.get("table_name")): t for t in (d.get("table_storage") or [])}
    layout = {fqn(t.get("table_schema"), t.get("table_name")): t for t in (d.get("table_layout") or [])}
    rate = price["on_demand_per_tib"]

    # Full scans of large tables by single-table queries.
    full = []
    for u in d.get("table_usage") or []:
        key = fqn(u.get("dataset_id"), u.get("table_id"))
        t = storage.get(key)
        if not t or int(num(u.get("single_table_jobs"))) < 5:
            continue
        size = num(t.get("total_logical_bytes"))
        avg = num(u.get("avg_single_table_bytes_processed"))
        if size >= 10 * GIB and avg / size >= 0.8:
            lay = layout.get(key, {})
            full.append({"table": key, "table_gib": gib(size), "avg_scan_ratio": round(avg / size, 2),
                         "single_table_jobs": int(num(u.get("single_table_jobs"))),
                         "partition_by": lay.get("partition_by"), "cluster_by": lay.get("cluster_by"),
                         "usd_month": round(num(u.get("single_table_bytes_billed")) / TIB * rate * ctx["per_month"], 2)})
    for x in sorted(full, key=lambda x: -x["usd_month"])[:15]:
        partitioned = bool(x["partition_by"])
        f.add("P1", "high" if x["usd_month"] >= 100 else "medium",
              f"Queries on {x['table']} scan {x['avg_scan_ratio']:.0%} of it on average"
              + (" despite partitioning" if partitioned else " (table is not partitioned)"),
              x, objects=[x["table"]], savings=x["usd_month"] * 0.6,
              hint=("Partition pruning is not happening: look for filters that wrap the partition column "
                    "in a function, compare it to a subquery, or are missing." if partitioned else
                    "See schema findings: partition (and cluster) this table on the column queries filter by."),
              confidence="medium")

    patterns = d.get("top_query_patterns") or []
    repeated = []
    anti = [
        ("select_star", r"select\s+\*(?!\s*except)", "SELECT * on the largest tables reads every column"),
        ("order_no_limit", r"order\s+by(?![\s\S]*\blimit\b)", "ORDER BY without LIMIT forces a single-worker sort"),
        ("count_distinct", r"count\s*\(\s*distinct", "Exact COUNT(DISTINCT) where APPROX_COUNT_DISTINCT may do"),
        ("cross_join", r"cross\s+join", "CROSS JOIN"),
        ("regexp", r"regexp_(contains|extract|replace)", "Regex over large columns"),
        ("window_no_partition", r"over\s*\(\s*(order\s+by|\))", "Window function without PARTITION BY"),
        ("wildcard_table", r"\*`", "Wildcard table; check _TABLE_SUFFIX filters"),
    ]
    for p in patterns[:25]:
        q = (p.get("sample_query") or "").lower()
        hits = [label for key, rx, label in anti if re.search(rx, q)]
        gib_billed = gib(p.get("bytes_billed"))
        slow = num(p.get("avg_duration_ms")) >= 5 * 60 * 1000
        if (hits and gib_billed >= 100) or slow:
            f.add("P6", "medium" if gib_billed >= 1024 or slow else "low",
                  ("Slow" if slow else "Costly") + f" query pattern ({int(num(p.get('runs')))} runs, {gib_billed:,.0f} GiB)"
                  + (": " + "; ".join(hits) if hits else ""),
                  {"query_hash": p.get("query_hash"), "sample_job_id": p.get("sample_job_id"),
                   "runs": int(num(p.get("runs"))), "gib_billed": gib_billed,
                   "avg_duration_s": round(num(p.get("avg_duration_ms")) / 1000, 1),
                   "slot_hours": round(num(p.get("slot_ms")) / 3.6e6, 1),
                   "patterns_detected": hits, "referenced_tables": p.get("referenced_tables"),
                   "sample_query": p.get("sample_query")},
                  objects=[p.get("sample_job_id")],
                  hint="Read sample_query and propose a concrete rewrite. Patterns are regex hints, "
                       "not proof; drop any that the SQL does not actually show.",
                  confidence="medium")
        runs = int(num(p.get("runs")))
        per_run_gib = gib_billed / max(runs, 1)
        if runs >= ctx["days"] and per_run_gib >= 1 and num(p.get("cache_hits")) / max(runs, 1) < 0.2 \
                and (p.get("statement_type") or "") == "SELECT":
            repeated.append({"query_hash": p.get("query_hash"), "sample_job_id": p.get("sample_job_id"),
                             "runs": runs, "gib_billed": gib_billed, "gib_per_run": round(per_run_gib, 2),
                             "referenced_tables": p.get("referenced_tables"), "sample_query": p.get("sample_query")})
    if repeated:
        f.add("P7", "medium" if sum(r["gib_billed"] for r in repeated) >= 10240 else "low",
              f"{len(repeated)} heavy SELECT patterns re-run ≥{ctx['days']}× with little caching",
              {"patterns": repeated[:10]}, objects=[r["sample_job_id"] for r in repeated[:10]],
              hint="Candidates for a materialized view, a scheduled summary table, or BI Engine. "
                   "Non-deterministic functions (CURRENT_TIMESTAMP) disable the cache.",
              confidence="medium")

    # Load profile.
    hours = [num(h.get("avg_slots")) for h in (d.get("hourly_load") or [])]
    metrics = {}
    if hours:
        s = sorted(hours)
        median = s[len(s) // 2]
        p95 = s[int(len(s) * 0.95) - 1] if len(s) > 1 else s[0]
        metrics = {"hours": len(hours), "median_avg_slots": round(median, 1), "p95_avg_slots": round(p95, 1),
                   "max_avg_slots": round(s[-1], 1)}
        if median > 0 and p95 / median >= 5 and p95 >= 100:
            f.add("P5", "low", f"Bursty load: p95 hour uses {p95 / median:.0f}× the median slots",
                  metrics, hint="If on reservations, check queueing in those hours and stagger scheduled jobs.",
                  confidence="medium")
    return metrics, f.items


SHARD_RX = re.compile(r"^(.*?)(_)?(\d{8})$")
TEMP_RX = re.compile(r"(^|_)(tmp|temp|staging|stg|scratch|backup|bak|copy|old|test)(_|$|\d)", re.I)


def analyze_schema(d, price, ctx):
    f = Findings("schema")
    storage = {fqn(t.get("table_schema"), t.get("table_name")): t for t in (d.get("table_storage") or [])}
    usage = {fqn(u.get("dataset_id"), u.get("table_id")): u for u in (d.get("table_usage") or [])}
    layout = d.get("table_layout") or []

    unpart, no_rpf, no_cluster, over_part, temp = [], [], [], [], []
    for t in layout:
        key = fqn(t.get("table_schema"), t.get("table_name"))
        st = storage.get(key, {})
        size = num(st.get("total_logical_bytes"))
        jobs = int(num(usage.get(key, {}).get("jobs")))
        parts = int(num(st.get("total_partitions")))
        partitioned = bool(t.get("partition_by"))
        rpf = str(t.get("require_partition_filter") or "").lower() == "true"
        row = {"table": key, "gib": gib(size), "jobs": jobs, "partitions": parts,
               "partition_by": t.get("partition_by"), "cluster_by": t.get("cluster_by")}
        if not partitioned and size >= 10 * GIB and jobs >= 5:
            unpart.append(row)
        if partitioned and not rpf and size >= 100 * GIB and jobs >= 5:
            no_rpf.append(row)
        if not t.get("cluster_by") and size >= 10 * GIB and jobs >= 20:
            no_cluster.append(row)
        if parts >= 2000 and size / max(parts, 1) < 100 * 1024 ** 2:
            over_part.append({**row, "avg_partition_mib": round(size / max(parts, 1) / 1024 ** 2, 1)})
        if TEMP_RX.search(t.get("table_name") or "") and size >= GIB and not t.get("expiration_timestamp"):
            temp.append(row)

    if unpart:
        f.add("S1", "high", f"{len(unpart)} large, frequently queried tables are not partitioned",
              {"tables": sorted(unpart, key=lambda r: -r["gib"])[:20]}, objects=[r["table"] for r in unpart[:20]],
              hint="Recreate as a partitioned (and clustered) table on the column queries filter by. "
                   "This is a full rewrite: estimate with dry run, build alongside, swap names in a "
                   "maintenance window. Never CREATE OR REPLACE the live table.")
    if no_rpf:
        f.add("S3", "medium", f"{len(no_rpf)} partitioned tables ≥100 GiB allow unfiltered full scans",
              {"tables": sorted(no_rpf, key=lambda r: -r["gib"])[:20]}, objects=[r["table"] for r in no_rpf[:20]],
              hint="ALTER TABLE ... SET OPTIONS(require_partition_filter=TRUE). Existing queries without a "
                   "partition filter will start failing: find them in JOBS first.")
    if no_cluster:
        f.add("S4", "low", f"{len(no_cluster)} heavily queried tables have no clustering",
              {"tables": sorted(no_cluster, key=lambda r: -r["jobs"])[:20]}, objects=[r["table"] for r in no_cluster[:20]],
              hint="Pick up to 4 columns used in filters/joins, most selective first. bq update "
                   "--clustering_fields only affects newly written data unless the table is rewritten.",
              confidence="medium")
    if over_part:
        f.add("S2", "high" if any(r["partitions"] >= 8000 for r in over_part) else "medium",
              f"{len(over_part)} tables have many tiny partitions",
              {"tables": over_part[:20]}, objects=[r["table"] for r in over_part[:20]],
              hint="Limit is 10,000 partitions per table. Use coarser granularity (MONTH/YEAR) plus clustering.")
    if temp:
        f.add("S5", "low", f"{len(temp)} temp/staging/backup-looking tables (≥1 GiB) never expire",
              {"tables": sorted(temp, key=lambda r: -r["gib"])[:20]}, objects=[r["table"] for r in temp[:20]],
              hint="Confirm with owners, then set expiration_timestamp or a dataset default expiration "
                   "for scratch datasets.", confidence="medium")

    # Date-sharded tables.
    shards = {}
    for key in storage:
        ds, _, name = key.partition(".")
        m = SHARD_RX.match(name)
        if m:
            shards.setdefault(f"{ds}.{m.group(1)}*", []).append(name)
    sharded = [{"prefix": k, "shards": len(v)} for k, v in shards.items() if len(v) >= 30]
    if sharded:
        f.add("S6", "medium", f"{len(sharded)} date-sharded table families (table_YYYYMMDD)",
              {"families": sorted(sharded, key=lambda s: -s["shards"])[:20]},
              objects=[s["prefix"] for s in sharded[:20]],
              hint="Sharding adds per-table metadata overhead and limits optimization; migrate to one "
                   "date-partitioned table. GA4/Firebase exports are sharded by design: note, don't flag.",
              confidence="medium")

    metrics = {"tables": len(layout),
               "partitioned_share": round(sum(1 for t in layout if t.get("partition_by")) / len(layout), 3) if layout else None,
               "clustered_share": round(sum(1 for t in layout if t.get("cluster_by")) / len(layout), 3) if layout else None}
    return metrics, f.items


BROAD_ROLES = {"roles/owner", "roles/editor", "roles/bigquery.admin"}
# Roles that let a principal grant itself anything or impersonate others: owner in all but name.
ESCALATION_ROLES = {"roles/resourcemanager.projectIamAdmin", "roles/iam.securityAdmin",
                    "roles/iam.serviceAccountAdmin", "roles/iam.serviceAccountTokenCreator",
                    "roles/iam.serviceAccountKeyAdmin", "roles/iam.workloadIdentityPoolAdmin"}


def analyze_security(d, price, ctx):
    f = Findings("security")
    acl = d.get("dataset_acl") or []
    public, personal, broad_ds = [], [], []
    for ds in acl:
        for e in ds.get("access", []):
            who = e.get("specialGroup") or e.get("iamMember") or e.get("userByEmail") or e.get("groupByEmail") or e.get("domain")
            role = e.get("role")
            if e.get("specialGroup") == "allAuthenticatedUsers" or e.get("iamMember") in ("allUsers", "allAuthenticatedUsers"):
                public.append({"dataset": ds["dataset"], "member": who, "role": role})
            elif (e.get("userByEmail") or "").lower().endswith(("@gmail.com", "@googlemail.com")):
                personal.append({"dataset": ds["dataset"], "member": who, "role": role})
            elif e.get("domain") and role in ("OWNER", "WRITER", "roles/bigquery.dataOwner", "roles/bigquery.dataEditor"):
                broad_ds.append({"dataset": ds["dataset"], "member": f"domain:{who}", "role": role})
    if public:
        f.add("SEC1", "critical", f"{len(public)} dataset grant(s) are open to all users / all authenticated Google accounts",
              {"grants": public}, objects=sorted({p["dataset"] for p in public}),
              hint="Remove the grant unless the dataset is intentionally public; for sharing, use "
                   "Analytics Hub or authorized views.")
    if personal:
        f.add("SEC4", "high", f"{len(personal)} dataset grant(s) to personal Gmail accounts",
              {"grants": personal[:30]}, objects=sorted({p["dataset"] for p in personal}),
              hint="Replace with corporate identities or groups.")
    if broad_ds:
        f.add("SEC3", "medium", f"{len(broad_ds)} whole-domain write/owner grants on datasets",
              {"grants": broad_ds[:30]}, objects=sorted({p["dataset"] for p in broad_ds}),
              hint="Grant write access to specific groups; domain-wide should be read at most.")

    iam = d.get("project_iam")
    metrics = {"datasets_checked": len(acl), "project_iam_available": iam is not None}
    if iam:
        broad = []
        for b in iam.get("bindings", []):
            if b.get("role") in BROAD_ROLES:
                for m in b.get("members", []):
                    broad.append({"role": b["role"], "member": m})
        sa_broad = [b for b in broad if b["member"].startswith("serviceAccount:")]
        humans = [b for b in broad if b["member"].startswith(("user:", "group:", "domain:"))]
        metrics.update({"broad_role_members": len(broad), "service_accounts_with_broad_roles": len(sa_broad)})
        if sa_broad:
            f.add("SEC2", "high", f"{len(sa_broad)} service account(s) hold owner/editor/BigQuery admin",
                  {"bindings": sa_broad[:30]}, objects=[b["member"] for b in sa_broad[:30]],
                  hint="Give pipelines roles/bigquery.jobUser on the project plus dataEditor/dataViewer on "
                       "only the datasets they touch. The default compute SA with Editor is a common culprit.")
        escal = {}
        for b in iam.get("bindings", []):
            if b.get("role") in ESCALATION_ROLES:
                for m in b.get("members", []):
                    if m.startswith("serviceAccount:"):
                        escal.setdefault(m, []).append(b["role"])
        if escal:
            f.add("SEC7", "high", f"{len(escal)} service account(s) can escalate to owner via IAM/impersonation roles",
                  {"service_accounts": [{"member": m, "roles": r} for m, r in escal.items()][:20]},
                  objects=list(escal)[:20],
                  hint="Usually a CI/CD deployer. Confirm keyless (Workload Identity Federation) with a "
                       "repo/branch-pinned condition, split infra-apply from app-deploy, and remove "
                       "projectIamAdmin/TokenCreator from anything that only deploys code.")
        if len(humans) > 5:
            f.add("SEC2", "medium", f"{len(humans)} people/groups hold owner/editor/BigQuery admin on the project",
                  {"bindings": humans[:30]}, objects=[b["member"] for b in humans[:30]],
                  hint="Keep admins to a small group; analysts need jobUser + dataViewer.")
    pii = d.get("pii_columns") or []
    if pii:
        tables = sorted({fqn(c.get("table_schema"), c.get("table_name")) for c in pii})
        f.add("SEC6", "info", f"{len(pii)} columns across {len(tables)} tables look like personal data",
              {"columns": pii[:50]}, objects=tables[:50],
              hint="Check who can read these tables; consider policy tags with data masking or authorized "
                   "views. Name matching only — confirm before acting.", confidence="low")
    return metrics, f.items


ERROR_HINTS = {
    "quotaExceeded": "Quota hit (403). Identify which quota from the message; spread load or request an increase.",
    "rateLimitExceeded": "Rate limit (403). Add exponential backoff; batch DML/table updates.",
    "resourcesExceeded": "Query shape too heavy for one worker: ORDER BY without LIMIT, OVER() without PARTITION BY, huge ARRAY_AGG, skewed joins.",
    "accessDenied": "Permissions or credentials changed (rotated key, removed member, Drive scope for Sheets tables).",
    "notFound": "Missing table/dataset or region mismatch (job location ≠ dataset location).",
    "invalidQuery": "Broken SQL, often after a schema change upstream.",
    "billingTierLimitExceeded": "Query exceeded CPU-to-bytes ratio on on-demand billing; simplify or use a reservation.",
    "backendError": "Transient; retry with backoff. Investigate only if persistent.",
    "internalError": "Transient; retry with backoff. Investigate only if persistent.",
}


def analyze_reliability(d, price, ctx):
    f = Findings("reliability")
    ov = ctx["overview"]
    rate = ov["failed_jobs"] / ov["jobs"] if ov["jobs"] else 0
    metrics = {"query_failure_rate": round(rate, 4)}
    if ov["jobs"] >= 100 and rate >= 0.05:
        f.add("R1", "high" if rate >= 0.15 else "medium", f"{rate:.1%} of queries failed in the window",
              {"jobs": ov["jobs"], "failed": ov["failed_jobs"]})

    groups = {}
    for e in d.get("errors") or []:
        msg = re.sub(r"^Query error: ", "", e.get("message_pattern") or "")
        msg = re.sub(r" at \[N:N\]$", "", msg)
        # Collapse per-tenant names (ll_acc_xxx, hashes) so one bug is one signature.
        msg = re.sub(r"\b(?=\w*N)\w*[a-zA-Z]\w*N\w*\b", "<id>", msg)
        key = (e.get("job_type"), e.get("reason"), msg[:200])
        g = groups.setdefault(key, {**e, "message_pattern": msg, "occurrences": 0, "variants": 0})
        g["occurrences"] += int(num(e.get("occurrences")))
        g["variants"] += 1
    for e in sorted(groups.values(), key=lambda g: -g["occurrences"])[:15]:
        occ = int(num(e.get("occurrences")))
        if occ < max(10, ctx["days"]):
            continue
        reason = e.get("reason") or "unknown"
        msg = e.get("message_pattern") or ""
        if "serialize access" in msg.lower():
            hint = "Concurrent DML on the same table; serialize writers or batch them."
        else:
            hint = ERROR_HINTS.get(reason, "Read the message and sample job; map to a root cause.")
        f.add("R2", "medium" if occ >= 100 else "low", f"Recurring {reason} ({occ}×): {msg[:90]}",
              {"job_type": e.get("job_type"), "reason": reason, "message_pattern": msg, "occurrences": occ,
               "users": int(num(e.get("users"))), "sample_user": e.get("sample_user"), "variants": e.get("variants"),
               "sample_job_id": e.get("sample_job_id"), "last_seen": e.get("last_seen")},
              objects=[e.get("sample_job_id")], hint=hint, confidence="medium")

    broken = []
    for s in d.get("scheduled_runs") or []:
        recent = s.get("recent_runs") or []
        if recent and recent[0].get("reason"):
            broken.append({"destination": s.get("destination"), "run_as": s.get("run_as"),
                           "failed_runs": int(num(s.get("failed_runs"))), "runs": int(num(s.get("runs"))),
                           "last_error": recent[0].get("message")})
    if broken:
        f.add("R3", "high", f"{len(broken)} scheduled queries failed on their latest run",
              {"schedules": broken[:20]}, objects=[b["destination"] for b in broken[:20]],
              hint="Fix or pause each; downstream tables are going stale. Check run_as identity first.")

    configs = d.get("transfer_configs") or []
    owned_by_user, disabled = [], []
    for c in configs:
        owner = ((c.get("ownerInfo") or {}).get("email") or "")
        if owner and not owner.endswith("gserviceaccount.com"):
            owned_by_user.append({"name": c.get("displayName"), "owner": owner})
        if c.get("disabled"):
            disabled.append(c.get("displayName"))
    if owned_by_user:
        f.add("R4", "medium", f"{len(owned_by_user)} scheduled queries/transfers run as a person, not a service account",
              {"configs": owned_by_user[:30]},
              hint="They break when that person leaves or loses access. bq update --transfer_config "
                   "--service_account_name=... moves them to a service account.")
    metrics.update({"scheduled_destinations": len(d.get("scheduled_runs") or []),
                    "transfer_configs": len(configs), "disabled_configs": len(disabled)})
    return metrics, f.items


# ---------- main ----------

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    audit = Path(sys.argv[1])
    pricing_path = HERE.parent / "references" / "pricing.json"
    if "--pricing" in sys.argv:
        pricing_path = Path(sys.argv[sys.argv.index("--pricing") + 1])
    price = json.loads(pricing_path.read_text())
    raw = audit / "raw"
    manifest = json.loads((audit / "manifest.json").read_text())
    names = ["jobs_overview", "cost_by_user", "top_query_patterns", "table_usage", "table_storage",
             "table_layout", "datasets", "errors", "scheduled_runs", "hourly_load", "pii_columns",
             "dataset_acl", "project_iam", "transfer_configs"]
    d = {n: load(raw, n) for n in names}

    ov_row = (d["jobs_overview"] or [{}])[0] if d["jobs_overview"] else {}
    overview = {k: num(ov_row.get(k)) for k in ("jobs", "failed_jobs", "cache_hits", "bytes_billed",
                                                  "bytes_processed", "slot_ms", "on_demand_jobs",
                                                  "reservation_jobs", "users")}
    days = int(manifest.get("days", 30))
    ctx = {"overview": overview, "days": days, "per_month": 30 / days, "now": datetime.now(timezone.utc)}

    out = audit / "analysis"
    out.mkdir(exist_ok=True)
    summary = {"project": manifest["project"], "region": manifest["region"], "days": days,
               "collected_at": manifest.get("collected_at"), "pricing": price,
               "collectors": manifest.get("collectors", {}), "areas": {}}
    analyzers = {"cost": analyze_cost, "performance": analyze_performance, "schema": analyze_schema,
                 "security": analyze_security, "reliability": analyze_reliability}
    # An area whose core inputs are missing is "not assessed", not "healthy".
    required = {"cost": ["jobs_overview"], "performance": ["top_query_patterns", "table_storage"],
                "schema": ["table_layout", "table_storage"], "security": ["dataset_acl"],
                "reliability": ["errors"]}
    all_items = []
    for area in AREAS:
        metrics, items = analyzers[area](d, price, ctx)
        (out / f"{area}.json").write_text(json.dumps({"area": area, "metrics": metrics, "candidates": items},
                                                     indent=2, default=str))
        missing = [n for n in required[area] if d.get(n) is None]
        summary["areas"][area] = {"score": None if len(missing) == len(required[area]) else score(items),
                                  "partial": bool(missing), "missing_inputs": missing,
                                  "candidates": len(items),
                                  "by_severity": {s: sum(1 for i in items if i["severity"] == s) for s in SEVERITY_WEIGHT},
                                  "metrics": metrics}
        all_items += items
    assessed = [a["score"] for a in summary["areas"].values() if a["score"] is not None]
    summary["overall_score"] = round(sum(assessed) / len(assessed)) if assessed else None
    summary["est_monthly_savings_usd"] = round(sum(i["est_monthly_savings_usd"] or 0 for i in all_items), 2)
    summary["overview"] = overview
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    print(f"Overall score {summary['overall_score']}/100 (assessed areas only) — {len(all_items)} candidate findings, "
          f"~${summary['est_monthly_savings_usd']:,.0f}/month potential savings (pre-review)")
    for area in AREAS:
        a = summary["areas"][area]
        sev = ", ".join(f"{k}:{v}" for k, v in a["by_severity"].items() if v)
        label = "n/a" if a["score"] is None else f"{a['score']:>3}"
        note = f"  [partial: missing {', '.join(a['missing_inputs'])}]" if a["partial"] else ""
        print(f"  {area:<12} {label}/100  {sev or 'no findings'}{note}")
    print(f"Wrote {out}/")


if __name__ == "__main__":
    main()
