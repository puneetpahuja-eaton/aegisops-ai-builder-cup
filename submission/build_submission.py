"""Fill the official AI Builder Cup submission template with Kairos AI content.

Keeps the template's exact slides, layout and branding; only fills the content
area of each prompt slide. Diagrams reuse the pitch-deck visuals; prototype
snapshots are live screenshots of the deployed app. Outputs
`Kairos-AI-Submission.pptx` (converted to PDF by a companion step).
"""
from __future__ import annotations

import copy
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
TEMPLATE = HERE / "Submission Template _ AI Builder Cup.pptx"
OUT = HERE / "Kairos-AI-Submission.pptx"

DARK = RGBColor(0x20, 0x23, 0x28)
BLUE = RGBColor(0x17, 0x4E, 0xA6)
GREEN = RGBColor(0x18, 0x7A, 0x4B)
MUTE = RGBColor(0x5F, 0x6B, 0x7A)
FONT = "Calibri"

prs = Presentation(str(TEMPLATE))
slides = list(prs.slides)


def heading_shape(slide):
    cand = [sh for sh in slide.shapes
            if sh.has_text_frame and any(p.text.strip() for p in sh.text_frame.paragraphs)]
    return cand[0] if cand else None


def keep_first_paragraph(shape):
    """Remove all but the first paragraph (drops the template's prompt bullets)."""
    tf = shape.text_frame
    ps = tf._txBody.findall(qn("a:p"))
    for p in ps[1:]:
        tf._txBody.remove(p)


def add_body(slide, lines, top=1.5, left=0.45, width=9.1, height=3.75, gap=6):
    """lines: list of dicts {t, bold?, bullet?, size?, color?, indent?, space?}."""
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(ln.get("space", gap))
        bullet = ln.get("bullet", False)
        prefix = "•  " if bullet else ""
        run = p.add_run()
        run.text = prefix + ln["t"]
        f = run.font
        f.size = Pt(ln.get("size", 13))
        f.bold = ln.get("bold", False)
        f.name = FONT
        f.color.rgb = ln.get("color", DARK)
    return tb


def _fit(iw, ih, mw, mh):
    r = min(mw / iw, mh / ih)
    return iw * r, ih * r


def add_image(slide, path, top=1.55, max_w=9.0, max_h=3.6, center_x=5.0):
    iw, ih = Image.open(path).size
    w, h = _fit(iw, ih, max_w, max_h)
    slide.shapes.add_picture(str(path), Inches(center_x - w / 2), Inches(top),
                             Inches(w), Inches(h))


def add_two_images(slide, p1, p2, top=1.6, max_h=3.5, gap=0.4):
    half = (9.2 - gap) / 2
    for path, cx in ((p1, 2.5 + 0.25), (p2, 7.5 - 0.25)):
        iw, ih = Image.open(path).size
        w, h = _fit(iw, ih, half, max_h)
        slide.shapes.add_picture(str(path), Inches(cx - w / 2), Inches(top),
                                 Inches(w), Inches(h))


# ---------------------------------------------------------------- Slide 1 --- #
s1 = slides[0]
hs = heading_shape(s1)
tf = hs.text_frame
fills = {"Team name": "Kairos AI",
         "Team leader name": "Puneet Pahuja",
         "Problem Statement": "Manufacturing - Intelligent Operations & Industrial Efficiency: "
                              "autonomous remote fault diagnosis & self-healing for power devices to cut downtime"}
ps = tf._txBody.findall(qn("a:p"))
for p in tf.paragraphs:
    for key, val in fills.items():
        if p.text.strip().startswith(key):
            run = p.add_run()
            run.text = "  " + val
            run.font.name = FONT
            run.font.bold = False
# add a 4th list item for team members by cloning the last item paragraph
ps = tf._txBody.findall(qn("a:p"))
clone = copy.deepcopy(ps[-1])
for r in clone.findall(qn("a:r")):
    clone.remove(r)
tf._txBody.append(clone)
new_p = tf.paragraphs[-1]
run = new_p.add_run()
run.text = "Team members:  Khushboo Verma, Anurag Verma"
run.font.name = FONT

# ---------------------------------------------------------------- Slide 3 --- #
s = slides[2]
add_body(s, [
    {"t": "Kairos AI puts an expert reliability engineer inside every power device.", "bold": True, "size": 15, "color": BLUE},
    {"t": "It learns each device from its own documentation - datasheets, register maps and event-log "
          "structure - using retrieval-augmented generation on Vertex AI, then continuously monitors live "
          "telemetry and event logs remotely.", "size": 13, "space": 8},
    {"t": "A five-agent engine detects anomalies, diagnoses the root cause with cited evidence, decides with "
          "confidence-gated autonomy, acts to self-heal or escalate (human-in-the-loop), and verifies the fix "
          "- quantifying the downtime and cost avoided. The same engine serves both historical and live analysis.", "size": 13, "space": 8},
    {"t": "Built end-to-end on Google Cloud: Gemini 2.5 Flash on Vertex AI, Vertex embeddings, Firestore, "
          "Cloud Storage, BigQuery and Secret Manager - deployed on Cloud Run.", "size": 13, "color": GREEN, "bold": True},
])

# ---------------------------------------------------------------- Slide 4 --- #
s = slides[3]
keep_first_paragraph(heading_shape(s))
add_body(s, [
    {"t": "How different is it from existing ideas?", "bold": True, "size": 13.5, "color": BLUE},
    {"t": "Existing tools only alert. Kairos AI explains the root cause, correlates cascading alarms across the "
          "dependency chain, and closes the loop - decide, act, verify - with human approval, not just detection.", "size": 12.5, "space": 10},
    {"t": "How will it solve the problem?", "bold": True, "size": 13.5, "color": BLUE},
    {"t": "Remote, autonomous diagnosis in seconds removes the wait for an on-site engineer, cutting downtime. "
          "Every answer is grounded in the device's own manuals, so a junior technician gets senior-grade insight.", "size": 12.5, "space": 10},
    {"t": "USP of the proposed solution", "bold": True, "size": 13.5, "color": BLUE},
    {"t": "Self-configuring monitoring - the agent reads the datasheet to pick parameters, thresholds and decode "
          "event logs - plus one engine for live and historic data, and honest, cited, human-in-the-loop AI on a "
          "deep Google Cloud stack.", "size": 12.5},
])

# ---------------------------------------------------------------- Slide 5 --- #
s = slides[4]
add_body(s, [
    {"t": "Role-based multi-device platform (admin / engineer / viewer) with hashed authentication.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Per-device knowledge base via RAG using Vertex AI embeddings (text-embedding-004).", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Knowledge ingestion: upload PDF / Word / Excel, or pull from GitHub and Confluence.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Ask the device - agentic assistant with Ask / Plan / Agent modes; generates datasets, test cases and code.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Five-agent analysis engine: Monitor -> Diagnose -> Decide -> Act -> Verify.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Datasheet-driven live monitoring over REST, with automatic event-log decoding.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Quantifies diagnosis accuracy, downtime avoided and cost avoided against a baseline.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "One engine for both historical datasets and live streams; secure secrets via Secret Manager.", "bullet": True, "size": 12.5, "space": 7},
])

# ---------------------------------------------------------------- Slide 6 --- #
s = slides[5]
add_image(s, ASSETS / "agents.png", top=1.55, max_w=9.3, max_h=3.6)

# ---------------------------------------------------------------- Slide 7 --- #
s = slides[6]
add_two_images(s, ASSETS / "shot_home.png", ASSETS / "shot_chat.png", top=1.6, max_h=3.5)

# ---------------------------------------------------------------- Slide 8 --- #
s = slides[7]
add_image(s, ASSETS / "architecture.png", top=1.55, max_w=9.3, max_h=3.6)

# ---------------------------------------------------------------- Slide 9 --- #
s = slides[8]
add_body(s, [
    {"t": "Gemini 2.5 Flash on Vertex AI - grounded reasoning, root-cause analysis and generation.", "bullet": True, "size": 12.5, "space": 6},
    {"t": "Vertex AI Embeddings (text-embedding-004) - RAG retrieval over device documents.", "bullet": True, "size": 12.5, "space": 6},
    {"t": "Firestore - platform state: users, devices, sources, chunks and knowledge links.", "bullet": True, "size": 12.5, "space": 6},
    {"t": "Cloud Storage - telemetry and generated/uploaded datasets.", "bullet": True, "size": 12.5, "space": 6},
    {"t": "BigQuery - partitioned audit trail with 30-day retention.", "bullet": True, "size": 12.5, "space": 6},
    {"t": "Secret Manager - integration keys, never stored in device records.", "bullet": True, "size": 12.5, "space": 6},
    {"t": "Cloud Run - serverless deployment; dedicated service account via ADC; scales to zero.", "bullet": True, "size": 12.5, "space": 6},
    {"t": "Python, Streamlit, scikit-learn (robust-Z + Isolation Forest) for the engine and UI.", "bullet": True, "size": 12.5, "space": 6},
    {"t": "Rules check: uses a Google AI model (Gemini) and is deployed on Google Cloud via Cloud Run.", "bold": True, "size": 12.5, "color": GREEN, "space": 6},
])

# ---------------------------------------------------------------- Slide 10 -- #
s = slides[9]
add_body(s, [
    {"t": "Cloud Run - scale-to-zero; ~$0 when idle, pay only per request.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Vertex AI (Gemini + embeddings) - per-token pricing; low for a demo workload.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Firestore / Cloud Storage / BigQuery - minimal at demo scale (free-tier friendly).", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Estimated demo running cost: under $50 / month.", "bold": True, "size": 13, "color": BLUE, "space": 7},
    {"t": "Production cost scales roughly linearly per device and per analysis, with no fixed server cost.", "size": 12.5, "space": 7},
    {"t": "(Illustrative estimate - actual cost depends on usage, region and data volume.)", "size": 11, "color": MUTE},
])

# ---------------------------------------------------------------- Slide 11 -- #
s = slides[10]
add_two_images(s, ASSETS / "shot_analysis.png", ASSETS / "shot_live.png", top=1.6, max_h=3.5)

# ---------------------------------------------------------------- Slide 12 -- #
s = slides[11]
add_body(s, [
    {"t": "121 automated tests passing (auth, RAG, generation, engine, live bridge, PRISM parity).", "bullet": True, "size": 12.5, "space": 8},
    {"t": "Demo analysis: 3 assets with 3 injected faults -> 100% diagnosis accuracy vs ground truth.", "bullet": True, "size": 12.5, "space": 8},
    {"t": "Illustrative impact: 223 minutes of downtime avoided and $153,550 cost avoided across 6 incidents, "
          "each scored against a no-platform baseline (synthetic scenarios, not realized savings).", "bullet": True, "size": 12.5, "space": 8},
    {"t": "MTTR drops from tens of hours to 1-2 analysis cycles.", "bullet": True, "size": 12.5, "space": 8},
    {"t": "Deployed and verified live on Cloud Run - Firestore-backed, Gemini on Vertex AI, zero runtime errors.", "bullet": True, "size": 12.5, "space": 8},
])

# ---------------------------------------------------------------- Slide 13 -- #
s = slides[12]
add_body(s, [
    {"t": "Real edge-sensor and IoT integration via Pub/Sub and Dataflow for always-on ingestion.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Multi-device fleet modeling with topology correlation across an entire site.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Predictive maintenance - forecasting failures before they occur.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Support for additional industrial protocols (Modbus, DLMS and others).", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Mobile alerts and automated work-order dispatch; multi-tenant SaaS for operators.", "bullet": True, "size": 12.5, "space": 7},
    {"t": "Domain-tuned models and on-device inference for low-connectivity sites.", "bullet": True, "size": 12.5, "space": 7},
])

# ---------------------------------------------------------------- Slide 14 -- #
s = slides[13]
keep_first_paragraph(heading_shape(s))
add_body(s, [
    {"t": "GitHub Public Repository:", "bold": True, "size": 13, "color": BLUE, "space": 4},
    {"t": "https://github.com/puneetpahuja-eaton/kairos-ai", "size": 13, "space": 12},
    {"t": "Demo Video (3 minutes):", "bold": True, "size": 13, "color": BLUE, "space": 4},
    {"t": "[Add your public YouTube / Vimeo / Drive link here after recording]", "size": 13, "color": MUTE, "space": 12},
    {"t": "Final Product (deployed on Cloud Run):", "bold": True, "size": 13, "color": BLUE, "space": 4},
    {"t": "https://kairos-ai-498775210896.asia-south1.run.app", "size": 13},
])

prs.save(str(OUT))
print(f"Saved {OUT}  ({len(prs.slides._sldIdLst)} slides)")
