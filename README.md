# Kairos AI — Multi-Device AI Reliability Platform (Google Cloud edition)

A role-based platform that onboards industrial devices, **learns from their
documents and data (RAG)**, analyzes both fed and **live** telemetry with an
agentic engine, and answers questions in a grounded Gemini chat. Built on Google
Cloud: Gemini on Vertex AI, Vertex AI embeddings, Firestore, Cloud Storage,
BigQuery, Secret Manager and Cloud Run.

- Live application: https://kairos-ai-498775210896.asia-south1.run.app
- Source: https://github.com/puneetpahuja-eaton/aegisops-ai-builder-cup

## Scope and provenance

Built for the **Manufacturing** theme of the Google Cloud AI Builder Cup. The
Kairos AI platform in this repository — authentication and roles, per-device
retrieval (RAG) over Vertex AI embeddings and Firestore, the agentic
Ask / Plan / Agent assistant, the generative dataset and live-monitoring
builders, the unified live-and-historic diagnostic engine, and the full Google
Cloud deployment (Cloud Run, Gemini on Vertex AI, Cloud Storage, BigQuery,
Secret Manager) — was developed during the hackathon window. It builds on a
team-authored power-reliability diagnostic method, disclosed transparently
rather than presented as new. All telemetry, datasheets and procedures used in
the demo are synthetic; the system never controls real equipment.

## What it does

1. **Role-based login** (admin / engineer / viewer) — Firestore-backed, hashed
   passwords. Admin configures; engineer runs analysis and live monitoring and
   approves; viewer sees analysis and chat only.
2. **Multi-device onboarding** — admins register any number of devices.
3. **Feed data** — upload PDF / Word / Excel / CSV / text, paste notes, or pull
   from **GitHub** and **Confluence**. Everything is extracted, chunked, embedded
   (Vertex AI `text-embedding-004`) and stored as per-device knowledge.
4. **Analysis** — the proven PRISM power-reliability engine runs per device on
   synthetic or uploaded telemetry, with all six original tabs.
5. **Live monitoring** — the agent reads the device's datasheet to decide which
   REST fields to poll, then streams and analyzes telemetry in real time,
   auto-resolving or escalating issues with estimated downtime/cost avoided.
   **REST is enabled; Modbus and DLMS are intentionally disabled** in this edition.
6. **Grounded chat** — a Gemini-style assistant answers only from the selected
   device's ingested data and the current analysis, with citations.

### Pages by role

| Page | admin | engineer | viewer |
|---|---|---|---|
| Device Manager, Data Sources, Integrations, Simulate/Upload, User Admin | ✅ | — | — |
| Analysis | ✅ | ✅ | ✅ |
| Live Monitoring | ✅ | ✅ | — |
| Ask the device (chat) | ✅ | ✅ | ✅ |

## Architecture

- **Streamlit multi-page** (`app.py` → `st.navigation`, role-gated).
- **Datastore** (`datastore.py`): Firestore when configured, else a local JSON
  store so the platform runs and is testable with **no cloud credentials**.
  Vector similarity is computed in-process over each device's bounded corpus.
- **Auth** (`auth.py`): PBKDF2-hashed passwords, roles, seeded admin.
- **Ingestion** (`ingest.py`): extract → chunk → embed → store.
- **Embeddings** (`embeddings.py`): Vertex AI, with a deterministic offline fallback.
- **RAG** (`rag.py`): retrieve top-k chunks → grounded Gemini answer with citations.
- **Integrations** (`integrations/`): GitHub + Confluence.
- **Live** (`live/`): REST adapter, agent field-mapping, rolling anomaly monitor,
  built-in simulated feed for credential-free demos.
- **Analysis engine**: the unchanged PRISM package (`prism_reference/prism`,
  byte-identical to `prism_reference/manifest.json`) plus cloud adapters
  (`prism_cloud.py`, `prism_extensions.py`), embedded as the Analysis page.
- **Secrets** (`secretmgr.py`): Secret Manager, else a local gitignored store.

## The embedded PRISM analysis

The default application preserves the original six tabs and their fields:

1. **Live Operations**: Play/Pause/Reset/Step once, original replay-speed options,
   Cases, Auto-resolved, Escalated, Diagnosis acc., Downtime avoided, Cost avoided;
   asset/metric selectors, telemetry and anomaly charts, fleet status,
   agent reasoning trace, named tool calls and event-code stream.
2. **Cases**: original case ID, fault type, asset/name, lifecycle badge, confidence,
   decision, downtime/cost estimates, metric/code evidence, ground-truth comparison,
   downstream symptoms, planned action, reversibility and decision rationale.
3. **Counterfactual (value)**: the original asset/metric selectors and
   `PRISM (live)` versus `No PRISM (baseline)` curves.
4. **Power Topology**: original power chain and root/anomaly/healthy colors.
5. **Models & Data**: original model/training fields and explanations.
6. **How it works**: original five-agent process and tool descriptions.

Original asset fields are retained: `asset_id`, `name`, `type`, `parent_id`,
`site`, `rated_kw`, `criticality`. Original scenario fields are retained:
`scenario_id`, `asset_id`, `fault_type`, `start_sample`, `description`,
`ground_truth_root_cause`.

The 22-asset, 480 V / 60 Hz original simulator trains on three synthetic days
(864 samples per asset), then runs 96 five-minute snapshots. Its six scenarios
are voltage sag, overload, battery degradation, thermal runaway, harmonic
distortion and breaker trip. Original thresholds, confidence calculation,
reversibility playbook, automatic synthetic actions, verification grace period,
case deduplication and value assumptions are unchanged.

The canonical `prism_reference/prism` package is byte-identical to the imported
reference; `prism_reference/manifest.json` records SHA-256 hashes. A bounded
one-time migration tool, `tools/import_prism.py`, excludes reports, documents,
credentials and caches. The original PRISM working folder is not modified.

## Google Cloud integrations

- **Cloud Run** hosts the Streamlit application with a dedicated service identity.
- **Gemini on Vertex AI** adds schema-validated, SOP-cited hypotheses and
  review-only work-order drafts. Its accepted source is displayed in each case.
- **Cloud Storage** supplies the original topology and scenario configuration
  (`prism/assets.csv`, `prism/live_scenarios.json`) and the fictional SOP.
- **BigQuery** stores versioned case summaries in a partitioned audit table and
  provides a bounded seven-day history query.

Cloud features are additive: expand **Google Cloud & data source** in the sidebar
or **Cloud audit & full agent trace** in Cases. Existing fields are not renamed.
Numerical PRISM confidence remains heuristic; Gemini's self-reported confidence
is shown separately. Gemini does not replace deterministic scoring, topology,
classification or the simulator's reversibility policy.

No model output is silently substituted with offline rules. A failed request or
insufficient grounding escalates instead of reporting a Gemini success. Therefore
cloud availability or a conservative Gemini assessment can deliberately change
a case to escalation; exact numerical/lifecycle parity is tested in explicit
offline mode with supported SOP evidence.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit 1.65+ is required (role-gated `st.navigation`, keyed tabs/expanders and
`st.fragment` live polling). With **no credentials** the platform runs fully on
the local store and offline reasoning — ideal for development and the test suite.
Offline results are explicitly labeled, never presented as Google AI.

**First run** seeds a demo admin (override with `KAIROS_ADMIN_EMAIL` /
`KAIROS_ADMIN_PASSWORD`): `admin@kairos.ai` / `admin12345`. Create engineer and
viewer accounts from **User Admin**.

To enable Google Cloud, set in `.env`:

```text
USE_VERTEX=1
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-2.5-flash
EMBED_MODEL=text-embedding-004
USE_FIRESTORE=1
FIRESTORE_PROJECT=your-project
USE_SECRET_MANAGER=1
GCS_BUCKET=your-bucket
BQ_DATASET=your_dataset
```

Use `gcloud auth application-default login` locally. Cloud Run uses its attached
service identity. AI Studio remains available with `USE_VERTEX=0` and a local
`GEMINI_API_KEY`. Never commit credentials or disable TLS verification.

## Feed data and integrations

- **Data Sources** (admin): upload PDF/Word/Excel/CSV/text or paste notes. Each
  source is extracted, chunked and embedded into the selected device's corpus.
- **Integrations** (admin): save a GitHub token and/or Confluence credentials
  (stored in Secret Manager), then ingest a repository (`owner/repo`) or a
  Confluence page (ID or URL) into the device's corpus.
- **Simulate / Upload** (admin): attach the built-in synthetic PRISM simulator,
  generate a dataset snapshot, or upload your own CSV/JSON telemetry.

## Live monitoring (REST)

In **Live Monitoring** (engineer/admin): keep the built-in simulated feed for a
credential-free demo, or point it at a real REST endpoint. Paste a sample
response and click **Ask agent to map fields** — the agent reads the device's
datasheet (RAG) and the sample to propose which JSON fields map to telemetry
metrics. **Start** streams readings at the configured interval; anomalies are
detected with a rolling robust-z baseline and either auto-resolved on recovery or
escalated, accumulating **estimated** downtime/cost avoided. Credentials are kept
in Secret Manager, never in device records. Modbus and DLMS are disabled.

## Persistence (across logins, logouts and deployments)

Everything an admin configures is stored in the datastore/secret store, **not** in
the login session, so it survives logout and re-login and **accumulates** over time:

- **API keys / tokens** → secret store.
- **Devices, uploaded knowledge (chunks + embeddings), and saved GitHub/Confluence
  links** → datastore. Each new source *adds* to the device corpus; the agent gets
  better as you feed more. Re-ingesting a saved link **refreshes** it (replaces its
  chunks) instead of duplicating.
- **Saved links** appear under **Integrations → Saved knowledge links** with
  **Refresh** / **Remove**, plus **Re-ingest all** to retrain on the latest content.

Backends:
- **Local mode** (no cloud): persisted to a `.localstore/` JSON file on the host.
  This survives restarts **on the same machine/path** but is not shared and is
  **ephemeral on Cloud Run**.
- **Cloud mode** (recommended for deployment): set `USE_FIRESTORE=1`,
  `USE_SECRET_MANAGER=1` and `GCS_BUCKET` so devices/knowledge, secrets and large
  files persist durably and across instances.

If you switch the embedding backend (offline ↔ Vertex AI), vector dimensions
change; stale-dimension chunks are ignored for retrieval. Use **Re-ingest all** to
re-embed saved links with the new model.

## Replace telemetry in the Analysis engine

In **Simulate / Upload**, or in **Analysis → Models & Data**, use the telemetry
template:

1. Prepare the PRISM telemetry template.
2. Download the CSV or JSON containing the original asset metadata and measurements.
3. Replace the data with authorized, non-confidential measurements.
4. Upload it and replace the fleet.

A successful replacement resets the topology, history-trained models, cases,
timeline and trace. Invalid input leaves the existing replay unchanged.
**Restore original PRISM simulator** brings back the original 22 assets/scenarios.

CSV metadata columns:

```text
timestamp,asset_id,phase,asset_type,criticality,parent_id,name,site,rated_kw,event_codes,<numeric metrics...>
```

- `timestamp`: timezone-qualified ISO 8601.
- `phase`: `history` or `replay`; all known-healthy training data must precede replay.
- At least 20 healthy history readings per asset; history codes must be `OK`,
  `SELFTEST_PASS`, `FAN_OK` or `LOAD_HIGH`.
- `criticality`: `low`, `medium`, `high`, `critical` or `unknown`.
- `parent_id`: blank or an existing ID. Cycles are rejected.
- `name`, `site`, `rated_kw` retain original asset metadata; these three columns
  are optional for older templates.
- `event_codes`: pipe-separated codes. PRISM's original code vocabulary is used.
- Numeric feature columns must be finite and consistent per asset across history
  and replay; blanks only for features not used by that asset throughout.
- Every replay timestamp must contain one row per asset.
- Maximum 2 MB per file, 50 assets, 20,000 total history rows, 10,000 replay rows
  and 30 metrics per reading.

JSON uses `assets`, `history`, `telemetry` arrays, with each reading containing
`timestamp`, `asset_id`, `metrics` and `event_codes`. Template `assets.id` maps to
the original displayed `asset_id`. User-supplied `source: synthetic` cannot
enable simulator mutation.

Uploaded measurements are **observation-only**: all cases route to engineer review,
no synthetic remediation is applied, no invented counterfactual savings are shown,
and diagnosis accuracy is `n/a` without ground truth. Custom metrics are displayed,
but the original classifier recognizes only its original power-fault signatures;
an arbitrary new metric is not a validated new diagnosis capability.

Uploading is not a PLC/SCADA/MQTT connection. "Live" means observable processing
of chronological replay. Uploaded data stays in session memory unless the user
authorizes Vertex AI processing or explicitly saves case summaries to BigQuery.
Do not upload confidential, personal or employer data. The SOP stays fictional.

## Safety and truthful interpretation

- Every automatic action in the Analysis engine changes **synthetic simulator
  state only**. No equipment command or external work-order dispatch exists.
- Live monitoring **reads** telemetry over REST; it never writes to or controls a
  device. Its downtime/cost-avoided figures are **estimates**, not measured savings.
- RAG answers are grounded only in ingested sources and cite them; ingested
  documents are treated as untrusted data and never followed as instructions.
- Recovery is verified against later snapshots, not proof of a production repair.
- Downtime/cost fields reproduce an **assumption-based counterfactual**.
  Realized production savings are $0 measured.
- Ground-truth accuracy compares against built-in scenario labels, not validated
  accuracy on factory data. Before diagnosed cases exist, it shows `n/a`.
- This is a reliability/triage prototype, not validated predictive maintenance.
  Do not upload confidential, personal or employer data. SOPs are fictional.

## Verification

```powershell
python -m unittest discover -s tests -v
Set-Location submission
node .\verify-prism.mjs
node .\verify-prism.mjs --live
```

The local browser check expects the new app on port 8505; set `KAIROS_URL` to
override. It exercises all original tabs, automatic synthetic remediation,
case/audit downloads, full-field telemetry replacement, observation-only handling
and invalid-upload preservation. The live check additionally uses actual Vertex AI,
Cloud Storage and BigQuery with synthetic template data only.

Parity tests compare all 96 original fleet snapshots, event sequences, score
histories, fitted model state, every case field/lifecycle, topology, baseline
curves, value and all original named tools. Cloud tools are additive.

The earlier Kairos AI interface remains in `legacy_app.py` for regression/comparison,
but is not the default dashboard. Its tests are retained.

## Deployment and costs

```powershell
python -m cloud.provision
.\cloud\deploy.ps1
```

Provisioning seeds private GCS sources, configures dedicated build/runtime
identities and a partitioned BigQuery table with 30-day retention.
Runtime permissions: Vertex AI User, BigQuery Job User, Firestore (Datastore)
User and Secret Manager Accessor on the project, Object Admin on the demo bucket,
Writer on the audit dataset.

On first visit the deployed app seeds a labeled demo device (`SEED_DEMO=1`) so
Analysis is populated immediately — three synthetic assets with three disclosed
ground-truth faults, scoring diagnosis accuracy, downtime avoided and cost
avoided. The seed is race-safe (fixed id) and idempotent.

Scale: Cloud Run is stateless (state lives in Firestore/GCS/BigQuery), so it
scales horizontally; the service is configured to scale to zero up to four
instances at concurrency eight, and history queries are bounded to 10 MiB. This
is not a spending cap; Vertex AI, builds, storage and hosting may incur charges,
and the billing-account owner still needs to configure budget alerts. This
public hackathon demo is not a production multi-tenant system.

## Submission

See `submission/verification.md` for evidence and limitations. Review the proposal,
eligibility/IP/development dates and all organizer requirements before submitting.
The old 165-second video draft predates this exact-PRISM interface and must be
re-recorded. Do not claim production repairs, measured savings or guaranteed wins.
