"""Idempotent hackathon infrastructure, invoked as python -m cloud.provision."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from google.api_core.exceptions import NotFound
from google.cloud import bigquery, storage
from google.oauth2.credentials import Credentials

import bq

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "project-fd312a16-8445-4b1f-862")
REGION = "asia-south1"
BUCKET = "aegisops-498775210896-demo"
DATASET = "aegisops_audit"
ACCOUNT = f"aegisops-runtime@{PROJECT}.iam.gserviceaccount.com"
BUILD_ACCOUNT = f"aegisops-builder@{PROJECT}.iam.gserviceaccount.com"
ROOT = Path(__file__).resolve().parents[1]
CLI = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Cloud SDK" / "google-cloud-sdk" / "lib" / "gcloud.py"


def gcloud(*arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, str(CLI), *arguments, "--quiet"],
        check=True, capture_output=True, text=True, timeout=180,
    )
    return result.stdout.strip()


def credentials() -> Credentials:
    return Credentials(gcloud("auth", "print-access-token"))


def main() -> None:
    import truststore
    truststore.inject_into_ssl()
    auth = credentials()
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT
    os.environ["BQ_DATASET"] = DATASET
    os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"] = auth.token
    accounts = json.loads(gcloud("iam", "service-accounts", "list", f"--project={PROJECT}", "--format=json"))
    if not any(account["email"] == ACCOUNT for account in accounts):
        gcloud("iam", "service-accounts", "create", "aegisops-runtime", f"--project={PROJECT}", "--display-name=AegisOps runtime")
    if not any(account["email"] == BUILD_ACCOUNT for account in accounts):
        gcloud("iam", "service-accounts", "create", "aegisops-builder", f"--project={PROJECT}", "--display-name=AegisOps builds")
    gcloud("projects", "add-iam-policy-binding", PROJECT, f"--member=serviceAccount:{BUILD_ACCOUNT}", "--role=roles/run.builder", "--condition=None")
    for role in ("roles/aiplatform.user", "roles/bigquery.jobUser"):
        gcloud("projects", "add-iam-policy-binding", PROJECT, f"--member=serviceAccount:{ACCOUNT}", f"--role={role}", "--condition=None")
    print("Runtime service account and project roles configured.")
    storage_client = storage.Client(project=PROJECT, credentials=auth)
    bucket = storage_client.bucket(BUCKET)
    try:
        bucket.reload()
    except NotFound:
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        bucket.iam_configuration.public_access_prevention = "enforced"
        bucket = storage_client.create_bucket(bucket, location=REGION)
    policy = bucket.get_iam_policy(requested_policy_version=3)
    member = f"serviceAccount:{ACCOUNT}"
    binding = next((item for item in policy.bindings if item["role"] == "roles/storage.objectViewer"), None)
    if binding is None:
        policy.bindings.append({"role": "roles/storage.objectViewer", "members": {member}})
    else:
        binding["members"].add(member)
    bucket.set_iam_policy(policy)
    for name in ("sop.md", "scenarios.json", "sample_incident.json"):
        bucket.blob(name).upload_from_filename(str(ROOT / "data" / name))
    print("Private Cloud Storage bucket seeded.")
    query_client = bigquery.Client(project=PROJECT, credentials=auth)
    dataset = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    dataset.location = REGION
    dataset.default_table_expiration_ms = 30 * 24 * 60 * 60 * 1000
    dataset = query_client.create_dataset(dataset, exists_ok=True)
    entries = list(dataset.access_entries)
    entry = bigquery.AccessEntry("WRITER", "userByEmail", ACCOUNT)
    if entry not in entries:
        entries.append(entry)
        dataset.access_entries = entries
        query_client.update_dataset(dataset, ["access_entries"])
    table = bigquery.Table(f"{PROJECT}.{DATASET}.cases", schema=bq.schema())
    table.time_partitioning = bigquery.TimePartitioning(field="ts")
    query_client.create_table(table, exists_ok=True)
    print("Partitioned BigQuery audit table configured (30-day retention).")
    result = {"project": PROJECT, "region": REGION, "bucket": BUCKET, "dataset": DATASET, "service_account": ACCOUNT, "build_account": BUILD_ACCOUNT}
    (ROOT / "cloud" / "deployment.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
