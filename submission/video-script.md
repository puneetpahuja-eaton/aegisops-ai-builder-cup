# AegisOps demo script | Target 2 minutes 45 seconds

Use the actual deployed application in live Vertex AI mode. Do not label offline
results as Gemini. Pre-run the fleet before recording to avoid spending the
three-minute limit watching API latency; say that the analysis has completed.
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

## 0:40-1:20 | Motor case: evidence and reasoning

"The numerical evidence is deterministic. Gemini provides the hypothesis and
these source citations; the application validates each quote. Confidence here
is the model's own report, not a proven failure probability."

Open MTR-07 evidence and diagnosis. Show the actual accepted Gemini source label.
If the model conservatively escalates the motor, explain that honestly; do not
claim it approved containment. Use SWG-02 for an eligible approval if available.

## 1:20-1:45 | Human approval and verification

"Eligible sandbox scenarios still require named human approval. After approval,
the verifier evaluates supplied post-action readings. Recovery is synthetic;
missing readings would remain unverified."

Enter a demo reviewer alias, approve an eligible case, and show verification.
If no live case is eligible, demonstrate escalation instead and explain the
approval mechanism separately without pretending it occurred.

## 1:45-2:15 | Engineer escalation

"The pump has a bearing-risk code, so the independent gate requires engineer
review. Gemini drafts a structured, review-only work order grounded in the SOP.
Nothing is dispatched or repaired automatically."

Show PMP-03, escalation reasons and the work order.

## 2:15-2:35 | Audit and failure behavior

"The audit preserves the model source, decision, approval and verification.
API failures are explicit; the app never substitutes offline rules as Gemini."

Refresh BigQuery history and download the audit JSON.

## 2:35-2:45 | Closing

"Our next step is an engineer-validated pilot measuring triage time and handoff
quality. AegisOps gives manufacturing teams evidence to action, with humans in control."

## Recording checklist

- Use no personal information, secrets, account tokens or employer data on screen.
- Ensure the final duration is strictly under 3:00; aim for 2:45-2:55.
- Verify video access in an incognito window after upload.
- Any editing should be transparent, with no fabricated outcomes or metrics.
