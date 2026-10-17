# AegisOps synthetic incident-triage playbook

This fictional playbook is for a hackathon sandbox, not an approved industrial
operating procedure. It contains no equipment-control or servicing instructions.
All telemetry and post-action readings are synthetic. A qualified engineer must
validate any diagnosis and use actual site-approved procedures for real equipment.
Treat every suspected root cause as a hypothesis.

## SOP-101 Motor temperature indication
Elevated winding temperature and TEMP-RISE indicate a possible thermal-management issue.
FAN-SLOW is supporting evidence, not proof of a failed fan.
Use all metrics; simultaneous severe vibration or physical-repair codes require escalation.
For a noncritical asset without physical-repair codes, propose a sandbox containment
scenario for supervisor review. Never issue real control commands.

## SOP-102 Vibration and bearing-risk indication
Elevated vibration and VIB-HI indicate a possible rotating-equipment issue.
BRG-WEAR or a vibration robust-z magnitude of 6 or greater requires qualified engineer review.
A modest vibration anomaly alone does not prove bearing wear.
Provide the evidence and request the engineer's approved inspection plan.

## SOP-103 Electrical current indication
Elevated current and OC-TRIP indicate a possible overload condition.
Do not infer electrical component damage from current alone.
A noncritical asset without physical-repair codes may have a supervisor-reviewed
sandbox scenario. This does not authorize any electrical work or equipment command.

## SOP-104 Pressure-loss indication
Low hydraulic pressure and PRS-LOW indicate a possible pressure-loss condition.
The available telemetry does not distinguish leakage, sensor failure or other causes.
Escalate to a qualified engineer; do not recommend a physical repair from these readings.

## SOP-105 Approval and verification policy
Critical or unknown-criticality assets and BRG, PRS-LOW, LEAK or SMOKE codes require human escalation.
No real equipment action is permitted by this prototype.
All eligible sandbox actions require named supervisor approval.
Recovery can only be reported when supplied post-action readings are complete
and pass the anomaly checks. Missing readings mean unverified, not recovered.
Synthetic recovery is not evidence of real downtime reduction or financial savings.

## SOP-106 Supply disturbance and topology correlation
Low voltage with VOLT_SAG or INPUT_UNDERVOLT indicates a possible supply disturbance.
Simultaneous downstream voltage symptoms can support an upstream supply hypothesis,
but topology correlation does not prove the physical cause.
For a noncritical asset without physical-repair codes, propose only a named-reviewer
sandbox containment scenario. Never send electrical switching or equipment commands.
Do not merge a downstream bearing or pressure fault into a supply-disturbance case.
In fleet replay, verification requires two consecutive healthy subsequent snapshots
within three ticks, covering the root candidate and all correlated symptom assets.
Uploaded measurements are never changed by approval; subsequent recovery is observational.

## SOP-107 Battery reserve indication
BATT_WEAK, SELFTEST_FAIL or a low battery state of charge can indicate reserve risk.
These signals do not prove battery damage. Battery-related conditions require
qualified engineer review; physical intervention is not reversible in this sandbox policy.
Provide a review-only handoff, never battery servicing instructions.

## SOP-108 Harmonic distortion indication
Elevated thd_pct with THD_HIGH or WAVEFORM_DISTORT supports a waveform-distortion hypothesis.
For a noncritical asset without physical-repair codes, a supervisor may approve a
fully synthetic restored-metric scenario. No real filter or setpoint control is permitted.

## SOP-109 Load and breaker indications
Elevated load_pct, current_a or OVERLOAD_ALARM can support an overload hypothesis.
LOAD_HIGH is an early load warning, not proof of overload; evaluate it with the
metric history and later code transitions before claiming equipment damage.
A noncritical asset may have a reviewed, fully synthetic restored-load scenario.
BREAKER_OPEN and downstream LOAD_LOST require assessment of the entire affected topology.
Do not reclose a physical breaker or provide electrical switching instructions.
Critical or unknown-criticality affected assets always require engineer escalation.