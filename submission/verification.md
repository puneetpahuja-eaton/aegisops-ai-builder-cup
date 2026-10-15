# Verification record | October 15, 2026

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
