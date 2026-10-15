"""Explicit BigQuery audit persistence and bounded operational history."""
from __future__ import annotations

import datetime
import os
import re


def is_enabled() -> bool:
    return bool(os.getenv("BQ_DATASET"))


def client():
    from google.cloud import bigquery
    credentials = None
    if os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN"):
        from google.oauth2.credentials import Credentials
        credentials = Credentials(os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"])
    return bigquery.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), credentials=credentials)


def table_id() -> str:
    dataset = os.environ["BQ_DATASET"]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,100}", dataset):
        raise ValueError("Invalid BigQuery dataset identifier.")
    return f"{os.environ['GOOGLE_CLOUD_PROJECT']}.{dataset}.cases"


def schema():
    from google.cloud import bigquery
    fields = {
        "ts": "TIMESTAMP", "case_id": "STRING", "revision": "INTEGER",
        "asset_id": "STRING", "root_cause": "STRING", "cited_sop_ids": "STRING",
        "decision": "STRING", "verification": "STRING", "confidence": "FLOAT",
        "source": "STRING", "mode": "STRING", "elapsed_seconds": "FLOAT",
        "approved": "BOOLEAN", "reviewer": "STRING", "potential_usd": "INTEGER",
        "errors": "STRING",
    }
    return [bigquery.SchemaField(name, kind) for name, kind in fields.items()]


def log_cases(cases: list[dict]) -> int:
    if not is_enabled():
        raise RuntimeError("BigQuery is not configured.")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows = [
        {
            "ts": now, "case_id": c["case_id"],
            "revision": 1 if c["approval"]["approved"] else 0,
            "asset_id": c["evidence"]["asset_id"],
            "root_cause": c["diagnosis"]["root_cause"],
            "cited_sop_ids": ",".join(c["diagnosis"]["cited_sop_ids"]),
            "decision": c["decision"]["action"],
            "verification": c["verification"]["status"],
            "confidence": c["diagnosis"]["confidence"],
            "source": c["diagnosis"]["_source"], "mode": c["mode"],
            "elapsed_seconds": c["elapsed_seconds"],
            "approved": c["approval"]["approved"], "reviewer": c["approval"]["reviewer"],
            "potential_usd": c["value"]["potential_usd"], "errors": "; ".join(c["errors"]),
        }
        for c in cases
    ]
    errors = client().insert_rows_json(
        table_id(), rows, row_ids=[f"{row['case_id']}:{row['revision']}" for row in rows],
    )
    if errors:
        raise RuntimeError(f"BigQuery rejected audit rows: {errors}")
    return len(rows)


def recent_history() -> list[dict]:
    from google.cloud import bigquery
    query = f"""
        SELECT ts, asset_id, root_cause, decision, verification, source, approved
        FROM `{table_id()}`
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        QUALIFY ROW_NUMBER() OVER (PARTITION BY case_id ORDER BY revision DESC, ts DESC) = 1
        ORDER BY ts DESC LIMIT 30
    """
    config = bigquery.QueryJobConfig(maximum_bytes_billed=10 * 1024 * 1024)
    return [dict(row) for row in client().query(query, job_config=config).result(timeout=20)]
