# Verification record | October 17, 2026

## Original PRISM / Google Cloud edition (current)

- All 54 unittest/Streamlit AppTest regressions passed with Python 3.11.9,
  including the ten exact-PRISM parity/integration tests. The final full run
  completed in 198 seconds while browser checks were also running.
- The default entrypoint now launches the original PRISM dashboard, not the
  earlier redesigned AegisOps interface. All six original tabs, replay controls,
  asset/scenario fields, case details and original five-agent engine are retained.
- The canonical engine and synthetic inputs are byte-identical to the imported
  source manifest. Git attributes preserve the original bytes on Linux checkout.
  The dashboard has documented additive cloud/upload panels and truthful
  simulator caveats; it is not claimed to be an unmodified source file.
- Parity tests compare all 96 original snapshots and event streams, fitted model
  state, score histories, every case field/lifecycle, topology, counterfactual
  curves, value and original named tool calls.
- Actual headless Chrome checks passed locally on port 8505 and on Cloud Run.
  Both verified the six tabs, original controls, 22 original assets and a
  full-field JSON template. The offline first supply case auto-remediated and
  resolved using the original synthetic policy.
- The deployed browser accepted a real `gemini:gemini-2.5-flash` explanation,
  saved PRISM summaries to BigQuery and exercised the audit-history query.
  Original topology/scenario configuration was loaded from private Cloud Storage.
- Each browser replaced every asset ID with a `USER-` ID using an actual file
  upload. The replacement reset the replay, trained replacement models and
  produced cases only for replacement assets. Uploaded cases escalated, claimed
  zero avoided cost and reported no diagnosis accuracy without ground truth.
- Invalid replacement data was rejected visibly without changing the active run.
  Neither synthetic nor uploaded paths sent equipment commands.
- Current deployed application revision: `aegis-ops-00010-kph`.
- Reproduce with `node submission/verify-prism.mjs` locally or add `--live`.
  Only synthetic template data was used for cloud checks. Screenshots and
  machine-readable results are generated under ignored `submission/media/`.
- `npm run capture` in `submission` now records the current PRISM browser
  workflow; it no longer targets the superseded UI. The raw recording is not a
  final narrated or duration-edited submission video.

Intentional differences from the original: additive Google Cloud/upload/audit
panels; diagnosis accuracy is `n/a` until measurable; automatic actions are
limited to synthetic simulator state; uploaded observations cannot be repaired
or credited with savings; cloud failure or insufficient evidence escalates
explicitly rather than pretending to provide a successful Google AI result.
Exact numerical/lifecycle parity is tested in explicit offline mode.

The current proposal PDF and demo script describe this PRISM edition. The old
165-second video draft is obsolete and must be re-recorded before submission.

## Earlier redesigned fleet upgrade (historical)

- 44 unittest/Streamlit AppTest regressions passed with Python 3.11.9.
- The full 22-asset synthetic power replay processed 96 timestamps after
  training on 864 healthy readings per asset. All six scheduled fault root/category
  pairs were detected at their injection tick in this deterministic offline test.
  This is synthetic scenario coverage, not validated diagnostic accuracy.
- Local headless Chrome verified actual file upload, whole-fleet replacement,
  named approval, two-tick synthetic recovery, invalid-upload rejection without
  losing the existing replay, play/pause and automatic pause for approval.
- Real-cloud headless Chrome verified Gemini 2.5 Flash diagnoses, topology symptom
  grouping, named approval and future-tick synthetic verification.
- The browser then uploaded a synthetic template with every asset ID changed.
  All training rows and cases used the replacement fleet, not the sample fleet.
- The uploaded supply case stayed abnormal after approval and failed its
  three-tick verification window. The separate bearing case escalated.
  Both uploaded cases had accepted `gemini:gemini-2.5-flash` sources.
  This expected failure verifies that uploaded telemetry is not rewritten to
  manufacture recovery. The replay recorded 71 observable tool events.
- A real fleet case summary was saved to BigQuery; a separate bounded history
  query confirmed a Gemini-backed FEEDER-01 audit record.
- Final deployed application revision: `aegis-ops-00008-lw8`.
- Browser reproduction: `node submission/verify-fleet.mjs` locally, or add
  `--live` for the public deployment. Uses only synthetic test data.

Validation caught and corrected two integration defects: NumPy boolean values
in model context were converted to native JSON booleans at their producer;
paused replay no longer periodically erases audit-save feedback.
Those behaviors now have regression coverage.

These fleet-interface checks describe the previous UI, which remains available
only as the legacy application for comparison and regression coverage.

## Earlier single-incident checks (October 15)

## Automated regression

22 tests passed with Python 3.11.9, using unittest and Streamlit AppTest.
Coverage includes evidence validation, citations, approval, outage handling,
unverified/reopened states, storage and BigQuery failures, fleet rendering,
session persistence and mode isolation.
Audit-history results persist across reruns and the panel stays open after refresh.

## Real Google Cloud smoke test

Gemini model: gemini-2.5-flash on Vertex AI, global model endpoint.
Application region: asia-south1.
Data: private Cloud Storage bucket, synthetic SOP and incidents.

| Asset | Accepted source | Gate | Measured analysis duration |
|---|---|---|---|
| MTR-07 | Gemini | Propose supervisor-reviewed sandbox | 7.34 s |
| PMP-03 | Gemini | Escalate to engineer | 14.72 s |
| SWG-02 | Gemini | Propose supervisor-reviewed sandbox | 4.47 s |
| PRESS-01 | Gemini | Escalate to engineer | 7.70 s |

Four audit rows were accepted by BigQuery. The bounded history query returned
13 records across the accumulated test runs. These are one-run measurements,
not latency guarantees, production accuracy or measured business savings.

## Deployed browser checks

- Public Cloud Run health endpoint returned HTTP 200 / ok.
- Dashboard loaded with Vertex AI, Cloud Storage and BigQuery configured.
- A real Gemini motor diagnosis was accepted.
- Named supervisor approval changed pending approval to simulated recovery.
- A subsequent fleet browser run accepted three diagnoses; the pump received
  a transient HTTP 504. The failure was explicitly displayed and escalated,
  not silently replaced by offline reasoning.

Google model capacity/timeouts can affect Cloud Run too. Deployment does not
eliminate model availability errors. Retrying a failed incident is supported.

## Publication and remaining ownership tasks

The standalone public GitHub source is:
https://github.com/puneetpahuja-eaton/aegisops-ai-builder-cup

The proposed deck and demo assets require participant review.
The final video must be uploaded to an organizer-accepted host.
Eligibility, fresh-code dates and IP/terms compliance require participant confirmation.

## Billing limitation

An attempt to configure a project-scoped billing budget received HTTP 403 from
the Billing Budgets API. No budget alert was created. The billing-account owner
must create it in the console or grant appropriate budget-management access.
Cloud Run's one-instance limit is not a project spending cap.
