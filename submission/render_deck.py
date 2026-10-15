"""Render a six-slide landscape PDF from the reviewed submission content."""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

HERE = Path(__file__).parent
WIDTH, HEIGHT = 960, 540
NAVY, TEAL, WHITE = HexColor("#102338"), HexColor("#42dcc4"), HexColor("#f3f6fa")


def slides():
    results_path = HERE / "live_results.json"
    verified = ""
    if results_path.exists():
        cases = json.loads(results_path.read_text(encoding="utf-8"))
        accepted = sum(case["diagnosis"]["_source"].startswith("gemini:") for case in cases)
        verified = f"Recorded live smoke test: {accepted}/{len(cases)} accepted Gemini diagnoses. This is not accuracy on a labeled production dataset."
    return [
        ("AegisOps", "Evidence to action, with humans in control", [
            "Manufacturing | Intelligent Operations & Industrial Efficiency",
            "For plant supervisors and reliability engineers: turn fragmented alarms and sensor readings into a traceable incident brief.",
            "Synthetic hackathon sandbox. No real equipment control or production savings claims.",
        ]),
        ("The problem and the narrow wedge", "A number is not an engineer-ready decision", [
            "Target task: incident triage for motors, pumps and pressure systems.",
            "Today: interpret deviations, find relevant procedures and assemble the engineer handoff.",
            "Product hypothesis: cited context and a complete review-only work order reduce gathering effort and improve handoff quality.",
            "Validate this hypothesis with an approved pilot; no invented customer or market statistics.",
        ]),
        ("A complete, reviewable workflow", "Monitor -> Diagnose -> Decide -> Act -> Verify", [
            "Monitor: robust-z evidence, with disclosed baseline assumptions.",
            "Diagnose: Gemini hypotheses with schema validation and source-checked SOP quotes.",
            "Decide: independent gates for criticality, physical-repair codes, severe vibration and insufficient evidence.",
            "Act: named approval for sandbox scenarios, or review-only engineer work order.",
            "Verify: explicit post-action readings; missing data stays unverified and continued anomalies reopen.",
        ]),
        ("Google Cloud architecture", "Real services, not decorative integrations", [
            "Cloud Run: deployed application, scale-to-zero, one-instance demo limit.",
            "Gemini on Vertex AI: structured incident reasoning and work-order drafting.",
            "Cloud Storage: private SOP and synthetic scenario documents.",
            "BigQuery: partitioned audit table, 30-day retention, bounded history query.",
            "Dedicated runtime service account; no API key embedded in the cloud service.",
        ]),
        ("Validation and honest limitations", "Make failures visible; do not manufacture success", [
            "Regression tests exercise approval, invalid output, bad citations, missing evidence, reopened cases, storage failure and rejected audit rows.",
            verified or "Live-cloud verification is required before submission; do not claim it until recorded.",
            "Quote checks establish textual provenance, not proof of every causal claim. Model confidence is self-reported.",
            "Assets, SOPs and post-action readings are synthetic. No production deployment or financial savings measured.",
        ]),
        ("Impact, feasibility and the next step", "Start with one approved workflow at one plant", [
            "Pilot measures: manual-vs-assisted triage time, engineer acceptance, unsupported claims and appropriate escalation.",
            "Use approved site procedures, qualified industrial review, tenant isolation and authenticated access before any production pilot.",
            "Scale documents and audit across sites; add real monitoring ingestion only after validation.",
            "Future roadmap only: Pub/Sub, Dataflow and hosted predictive workloads.",
            "Submission: deployed demo + public source + this PDF + video strictly under three minutes.",
        ]),
    ]


def main():
    output = HERE / "AegisOps-Proposal.pdf"
    pdf = canvas.Canvas(str(output), pagesize=(WIDTH, HEIGHT))
    pdf.setTitle("AegisOps | Manufacturing AI Builder Cup")
    style = ParagraphStyle("body", fontName="Helvetica", fontSize=17, leading=24, textColor=WHITE, alignment=TA_LEFT)
    for index, (title, subtitle, bullets) in enumerate(slides(), 1):
        pdf.setFillColor(NAVY)
        pdf.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        pdf.setFillColor(TEAL)
        pdf.rect(40, HEIGHT - 48, 80, 5, fill=1, stroke=0)
        pdf.setFillColor(WHITE)
        pdf.setFont("Helvetica-Bold", 30)
        pdf.drawString(40, HEIGHT - 100, title)
        pdf.setFillColor(TEAL)
        pdf.setFont("Helvetica", 18)
        pdf.drawString(40, HEIGHT - 136, subtitle)
        y = HEIGHT - 178
        for text in bullets:
            paragraph = Paragraph("- " + text, style)
            _, height = paragraph.wrap(WIDTH - 100, HEIGHT)
            if y - height < 54:
                raise ValueError(f"Slide {index} overflow; shorten the content.")
            paragraph.drawOn(pdf, 40, y - height)
            y -= height + 14
        pdf.setFillColor(TEAL)
        pdf.setFont("Helvetica", 11)
        pdf.drawString(40, 24, "AegisOps | Manufacturing | Synthetic demonstration")
        pdf.drawRightString(WIDTH - 40, 24, f"{index} / 6")
        pdf.showPage()
    pdf.save()
    print(f"Generated {output}")


if __name__ == "__main__":
    main()
