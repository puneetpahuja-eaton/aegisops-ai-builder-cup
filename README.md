# PRISM | Google Cloud edition

Manufacturing reliability simulation with the participant-owned original PRISM
dashboard and agent engine, extended with Gemini on Vertex AI, private Cloud
Storage inputs, BigQuery audit and Cloud Run hosting.

- Live application: https://aegis-ops-498775210896.asia-south1.run.app
- Source: https://github.com/puneetpahuja-eaton/aegisops-ai-builder-cup

## Original PRISM, not a redesigned dashboard

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

Streamlit 1.65+ is required for persistent tabs/expanders. Select
**Explicit offline simulation** for a credential-free run. Offline results are
explicitly labeled, never presented as Google AI.

For the configured Windows cloud deployment, use `.\run_local.ps1`.
It starts the same interface on port 8502 with a short-lived gcloud token.
Restart the script after token expiration.

For Vertex AI, configure:

```text
USE_VERTEX=1
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-2.5-flash
```

Use `gcloud auth application-default login` locally. Cloud Run uses its attached
service identity. AI Studio remains available with `USE_VERTEX=0` and a local
`GEMINI_API_KEY`. Never commit credentials or disable TLS verification.

## Replace telemetry without losing the original UI

In **Models & Data**, expand **Replace telemetry / download original fleet fields**:

1. Click **Prepare PRISM telemetry templates**.
2. Download the CSV or JSON containing the original asset metadata and measurements.
3. Replace the data with authorized, non-confidential measurements.
4. Upload it and click **Replace entire fleet**.

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

- Every original automatic action changes **synthetic simulator state only**.
  No equipment command or external work-order dispatch exists.
- The original playbook's electrical action labels are simulator descriptions,
  not operating/servicing instructions for real equipment.
- Recovery is verified against later synthetic snapshots using PRISM's original
  verifier and three-sample grace period; it is not proof of a production repair.
- Downtime/cost fields reproduce the original **assumption-based counterfactual**.
  Realized production savings are $0 measured.
- Ground-truth accuracy is a comparison against built-in scenario labels, not
  validated accuracy on factory data. Before diagnosed cases exist, it shows `n/a`.
- Quote checking proves textual provenance, not industrial correctness or full
  entailment of a generated explanation.
- This is a reliability/triage prototype, not validated predictive maintenance.

## Verification

```powershell
python -m unittest discover -s tests -v
Set-Location submission
node .\verify-prism.mjs
node .\verify-prism.mjs --live
```

The local browser check expects the new app on port 8505; set `AEGIS_URL` to
override. It exercises all original tabs, automatic synthetic remediation,
case/audit downloads, full-field telemetry replacement, observation-only handling
and invalid-upload preservation. The live check additionally uses actual Vertex AI,
Cloud Storage and BigQuery with synthetic template data only.

Parity tests compare all 96 original fleet snapshots, event sequences, score
histories, fitted model state, every case field/lifecycle, topology, baseline
curves, value and all original named tools. Cloud tools are additive.

The earlier AegisOps interface remains in `legacy_app.py` for regression/comparison,
but is not the default dashboard. Its tests are retained.

## Deployment and costs

```powershell
python -m cloud.provision
.\cloud\deploy.ps1
```

Provisioning seeds private GCS sources, configures dedicated build/runtime
identities and a partitioned BigQuery table with 30-day retention.
Runtime permissions: Vertex AI User and BigQuery Job User on the project,
Object Viewer on the demo bucket, Writer on the audit dataset.

The demo scales to zero, limits Cloud Run to one instance, and bounds history
queries to 10 MiB. This is not a spending cap; Vertex AI, builds, storage and
hosting may incur charges. The billing-account owner still needs to configure
budget alerts. This public hackathon demo is not a production multi-tenant system.

## Submission

See `submission/verification.md` for evidence and limitations. Review the proposal,
eligibility/IP/development dates and all organizer requirements before submitting.
The old 165-second video draft predates this exact-PRISM interface and must be
re-recorded. Do not claim production repairs, measured savings or guaranteed wins.
