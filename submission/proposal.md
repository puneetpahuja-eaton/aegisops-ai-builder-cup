# Kairos AI | Evidence to action, with humans in control

## 1. Problem: diagnosis is the bottleneck

Manufacturing teams receive fragmented alarms and telemetry. Operators must
interpret deviations, find the applicable procedure and prepare a useful
engineer handoff. A number alone does not explain what to review next.

Target user: plant supervisors and reliability engineers.
Initial wedge: incident triage for motors, pumps and pressure systems.
Theme: Manufacturing - Intelligent Operations & Industrial Efficiency.

This is a problem hypothesis informed by engineering experience, not a
quantified market study or independently validated customer research.

## 2. Solution: one complete, traceable workflow

Telemetry -> deterministic evidence -> Gemini-grounded hypothesis -> policy gate
-> named human review -> sandbox verification or review-only work order.

Every accepted SOP reference has a supporting quote validated against the source.
Every result shows its origin: Gemini, explicit offline rules, or unavailable.
The operator can export an audit report and review-only work orders.

## 3. Google Cloud architecture

- Cloud Run: deployed Streamlit application, scale-to-zero.
- Gemini on Vertex AI: structured diagnosis and work-order generation.
- Cloud Storage: private synthetic SOP/scenario documents.
- BigQuery: partitioned audit records and bounded recent-history queries.
- Attached service account: no API key in the deployed application.

Local robust-z evidence is not a hosted predictive Vertex model.
Pub/Sub and Dataflow are future ingestion options, not implemented services.

## 4. Technical distinction: useful reasoning, constrained execution

The model reasons over multiple signals and the relevant procedure rather than
just narrating a threshold alert. Structured schemas reject malformed output.
Source quotes are checked; criticality and physical-repair gates are deterministic.
Unsupported or unavailable reasoning goes to a human instead of becoming a fake success.

The five stages are an orchestrated workflow, not five separately trained agents.
The prototype never controls equipment.

## 5. Validation and limitations

Automated regression tests cover safety gates, invalid model output, missing
evidence, continued faults, explicit cloud failures and audit-write rejection.
Live-cloud results are recorded separately after execution.

Four synthetic demonstration incidents exercise both supervisor review and
engineer escalation. Predefined post-action readings demonstrate the verification
mechanism, not the effectiveness of a real repair.

No production downtime savings are claimed. Self-reported model confidence is
not calibrated reliability. Qualified industrial review is required.

## 6. Impact and scaling

Hypothesis: a cited incident brief reduces time spent gathering context and
improves the completeness of engineer handoffs.

Pilot plan: compare manual triage against assisted triage on an approved labeled
incident set; measure completion time, engineer acceptance, unsupported claims,
and appropriate escalation. Establish a manual baseline before claiming improvement.

Start with site-approved SOPs at one plant. Scale documents and audit history
across sites, add tenant isolation and authentication, then integrate ingestion.
Manufacturing expertise remains in the human review loop.
