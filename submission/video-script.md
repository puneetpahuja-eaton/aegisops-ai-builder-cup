# AegisOps demo script | Target 2 minutes 45 seconds

Use the actual deployed application in live Vertex AI mode. Do not label offline
results as Gemini. Pre-run or pause the fleet before recording to avoid spending the
three-minute limit watching API latency; label any cuts transparently.
Do not edit footage to imply actions happened that did not happen.

## 0:00-0:20 | Problem

"A plant alarm tells you what changed, not what to review next. AegisOps turns
operational telemetry into a cited incident hypothesis and engineer handoff.
This demonstration uses synthetic data and never controls real equipment."

Show the title and the Cloud Run address.

## 0:20-0:40 | Cloud implementation

"The application runs on Cloud Run. Gemini on Vertex AI reasons over evidence
and SOPs from private Cloud Storage. BigQuery retains the audit trail."

Show the reasoning backend, document source and history configuration.

## 0:40-1:20 | Fleet evidence, topology and replacement

"The numerical evidence is deterministic. Gemini provides the hypothesis and
these source citations; the application validates each quote. Confidence here
is the model's own report, not a proven failure probability."

Load the small synthetic fleet and process two timestamps. Show FEEDER-01 as
an upstream candidate with MTR-07/PMP-03 correlated symptoms, plus the actual
accepted Gemini source. Show timestamped tool events and the topology tab.
Briefly open the CSV/JSON replacement templates and explain that a validated
upload replaces the entire sample fleet, history and trained models.
If Gemini escalates conservatively, show that honestly rather than invent approval.

## 1:20-1:45 | Human approval and verification

"Eligible sandbox scenarios still require named human approval. After approval,
the verifier evaluates later snapshots. It needs two healthy ticks within three.
Synthetic recovery is not a real repair; approval never changes uploaded measurements."

Enter a demo reviewer alias, approve an eligible fleet case, then step two later
timestamps and show verification.
If no live case is eligible, demonstrate escalation instead and explain the
approval mechanism separately without pretending it occurred.

## 1:45-2:15 | Engineer escalation

"The pump has a bearing-risk code, so the independent gate requires engineer
review. Gemini drafts a structured, review-only work order grounded in the SOP.
Nothing is dispatched or repaired automatically."

Continue to timestamp five for the independent PMP-03 bearing indication.
Show why it stays separate from the supply event, its escalation and work-order draft.

## 2:15-2:35 | Audit and failure behavior

"The audit preserves the model source, decision, approval and verification.
API failures are explicit; the app never substitutes offline rules as Gemini."

Save the case summaries to BigQuery and download the full fleet audit JSON.
Show the power-demo option: 22 assets, three healthy training days and six
fault scenarios, with no claim of production accuracy.

## 2:35-2:45 | Closing

"Our next step is an engineer-validated pilot measuring triage time and handoff
quality. AegisOps gives manufacturing teams evidence to action, with humans in control."

## Recording checklist

- Use no personal information, secrets, account tokens or employer data on screen.
- Ensure the final duration is strictly under 3:00; aim for 2:45-2:55.
- Verify video access in an incognito window after upload.
- Any editing should be transparent, with no fabricated outcomes or metrics.
