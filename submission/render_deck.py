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
        ("Kairos AI", "Agentic reliability for manufacturing: catch the critical moment before downtime", [
            "Theme: Manufacturing | Intelligent Operations & Industrial Efficiency.",
            "For plant reliability teams: onboard any device, learn from its documents and data, and turn telemetry into cited, actionable diagnoses.",
            "Built during the AI Builder Cup on Google Cloud: Gemini on Vertex AI, Vertex embeddings, Firestore, Cloud Storage, BigQuery, Secret Manager and Cloud Run.",
        ]),
        ("The problem", "Diagnosis is the bottleneck, not detection", [
            "Alarms tell an engineer what changed, not what to review next; the knowledge is scattered across manuals, registers and event logs.",
            "One upstream fault becomes many tickets, and triage stays slow and tribal.",
            "Hypothesis: grounded evidence, an agentic engine and a cited engineer handoff cut triage effort - to be proven in an approved pilot, not assumed.",
        ]),
        ("What it does", "Onboard -> Learn -> Analyze -> Act, live or historic", [
            "Devices: register any asset and upload datasheets and registers; retrieval runs over Vertex embeddings with a per-device Firestore corpus (RAG).",
            "Agentic chat with Ask / Plan / Agent modes: it clarifies, plans, then generates datasets, test cases, code and live-monitoring plans.",
            "Five-agent engine (Monitor -> Diagnose -> Decide -> Act -> Verify) scores uploaded datasets and live REST streams through one code path.",
            "Live monitoring: the agent reads the datasheet to pick parameters and thresholds, decodes event logs, and streams readings into the same engine.",
        ]),
        ("Google Cloud architecture", "Real services, service-account identity, no embedded keys", [
            "Cloud Run: deployed app, scale-to-zero, runs as a dedicated service account via ADC.",
            "Gemini on Vertex AI: grounded reasoning, generation and structured output.",
            "Vertex embeddings + Firestore: per-device knowledge corpus and durable platform state (users, devices, sources, chunks).",
            "Cloud Storage + BigQuery: telemetry and datasets, plus a partitioned audit table with 30-day retention.",
        ]),
        ("Innovation and honesty", "Beyond a chatbot on a dashboard", [
            "Datasheet-driven monitoring: the agent derives parameter IDs, thresholds and event-log decoding from the device's own documents.",
            "One engine, two modes: identical diagnosis for historic datasets and for a live warm-up then stream.",
            "Physically-consistent synthetic data with ground-truth scenarios scores diagnosis accuracy, downtime and cost avoided.",
            "Honest by design: offline fallbacks are labeled and never shown as Gemini; data is synthetic; humans approve actions.",
        ]),
        ("Impact, feasibility and next step", "Start with one approved workflow at one plant", [
            "Impact: faster triage, consolidated tickets, and device knowledge made accessible to every engineer; scales device-by-device and site-by-site.",
            verified or "Validation: 121 automated tests cover auth, RAG, generation, the engine and the live bridge. Live-cloud checks are recorded, not claimed as production accuracy.",
            "Pilot measures manual-vs-assisted triage time, engineer acceptance and appropriate escalation; no invented savings or market statistics.",
            "Submission: deployed link + public repository + this deck + a video strictly under three minutes.",
        ]),
    ]


def main():
    output = HERE / "Kairos-AI-Proposal.pdf"
    pdf = canvas.Canvas(str(output), pagesize=(WIDTH, HEIGHT))
    pdf.setTitle("Kairos AI | Manufacturing AI Builder Cup")
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
        pdf.drawString(40, 24, "Kairos AI | Manufacturing | Synthetic demonstration")
        pdf.drawRightString(WIDTH - 40, 24, f"{index} / 6")
        pdf.showPage()
    pdf.save()
    print(f"Generated {output}")


if __name__ == "__main__":
    main()
