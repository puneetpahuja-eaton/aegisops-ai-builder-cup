"""Build the Kairos AI investor-grade pitch deck (PPTX) for the AI Builder Cup.

Generates `Kairos-AI-Pitch-Deck.pptx`. A companion step converts it to PDF via
PowerPoint. Content is aligned to the *current* implementation: Gemini on Vertex
AI, Vertex embeddings, Firestore, Cloud Storage, BigQuery, Secret Manager,
Cloud Run. All quantified savings are labeled illustrative/synthetic.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = Path(__file__).parent

# ---- palette -------------------------------------------------------------- #
BG = RGBColor(0x0B, 0x1B, 0x2E)        # deep navy
PANEL = RGBColor(0x14, 0x2C, 0x47)     # lighter navy panel
PANEL2 = RGBColor(0x1C, 0x3A, 0x5C)
TEAL = RGBColor(0x2D, 0xD4, 0xBF)
BLUE = RGBColor(0x4C, 0x8D, 0xFF)
AMBER = RGBColor(0xF5, 0xA5, 0x24)
GREEN = RGBColor(0x34, 0xD3, 0x99)
PINK = RGBColor(0xF4, 0x72, 0xB6)
WHITE = RGBColor(0xF4, 0xF7, 0xFB)
MUTE = RGBColor(0x9F, 0xB3, 0xC8)
DARKTEXT = RGBColor(0x0B, 0x1B, 0x2E)
FONT = "Calibri"
FONT_H = "Calibri"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = 13.333, 7.5


def slide():
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    return s


def _no_shadow(shape):
    shape.shadow.inherit = False


def box(s, l, t, w, h, fill=PANEL, line=None, line_w=1.0, radius=0.07, shape_type=MSO_SHAPE.ROUNDED_RECTANGLE):
    sp = s.shapes.add_shape(shape_type, Inches(l), Inches(t), Inches(w), Inches(h))
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(line_w)
    _no_shadow(sp)
    try:
        if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE:
            sp.adjustments[0] = radius
    except Exception:
        pass
    sp.text_frame.word_wrap = True
    return sp


def text(s, l, t, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """runs: list of (text, size, bold, color) or (text, size, bold, color, space_after)."""
    tb = s.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for i, r in enumerate(runs):
        txt, size, bold, color = r[0], r[1], r[2], r[3]
        space_after = r[4] if len(r) > 4 else 4
        space_before = r[5] if len(r) > 5 else 0
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.space_before = Pt(space_before)
        run = p.add_run()
        run.text = txt
        f = run.font
        f.size = Pt(size)
        f.bold = bold
        f.name = FONT
        f.color.rgb = color
    return tb


def fill_text(shape, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Inches(0.12)
    tf.margin_right = Inches(0.12)
    tf.margin_top = Inches(0.06)
    tf.margin_bottom = Inches(0.06)
    for i, r in enumerate(runs):
        txt, size, bold, color = r[0], r[1], r[2], r[3]
        space_after = r[4] if len(r) > 4 else 3
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        run = p.add_run()
        run.text = txt
        f = run.font
        f.size = Pt(size)
        f.bold = bold
        f.name = FONT
        f.color.rgb = color


def header(s, kicker, title, accent=TEAL):
    box(s, 0.6, 0.5, 0.14, 0.62, fill=accent, radius=0.3)
    text(s, 0.85, 0.42, 11.8, 0.4, [(kicker.upper(), 12.5, True, accent)])
    text(s, 0.85, 0.66, 11.8, 0.7, [(title, 29, True, WHITE)])


def footer(s, n):
    text(s, 0.6, 7.03, 8.0, 0.35, [("Kairos AI  ·  Google Cloud AI Builder Cup 2026  ·  Manufacturing", 9.5, False, MUTE)])
    text(s, 11.5, 7.03, 1.25, 0.35, [(f"{n:02d}", 9.5, True, MUTE)], align=PP_ALIGN.RIGHT)


def arrow(s, l, t, w, h, fill=TEAL, shape_type=MSO_SHAPE.RIGHT_ARROW):
    sp = s.shapes.add_shape(shape_type, Inches(l), Inches(t), Inches(w), Inches(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    sp.line.fill.background()
    _no_shadow(sp)
    return sp


def chip(s, l, t, w, h, label, fill=PANEL2, color=WHITE, size=11.5, bold=True, line=None):
    sp = box(s, l, t, w, h, fill=fill, line=line, radius=0.25)
    fill_text(sp, [(label, size, bold, color)], align=PP_ALIGN.CENTER)
    return sp


# =========================================================================== #
# Slide 1 — Cover
# =========================================================================== #
s = slide()
# decorative accent band
band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.28), Inches(SH))
band.fill.solid(); band.fill.fore_color.rgb = TEAL; band.line.fill.background(); _no_shadow(band)
circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9.6), Inches(-2.2), Inches(6.0), Inches(6.0))
circ.fill.solid(); circ.fill.fore_color.rgb = PANEL; circ.line.fill.background(); _no_shadow(circ)
circ2 = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(11.0), Inches(3.4), Inches(4.2), Inches(4.2))
circ2.fill.solid(); circ2.fill.fore_color.rgb = PANEL2; circ2.line.fill.background(); _no_shadow(circ2)
text(s, 0.95, 1.5, 11.5, 0.5, [("GOOGLE CLOUD AI BUILDER CUP 2026  ·  JAPAC", 13, True, TEAL)])
text(s, 0.9, 2.0, 11.6, 1.6, [("Kairos AI", 72, True, WHITE)])
text(s, 0.95, 3.5, 10.8, 0.9,
     [("An expert reliability engineer inside every power device.", 23, True, TEAL)])
text(s, 0.95, 4.35, 10.6, 1.0,
     [("Autonomous, remote fault diagnosis and self-healing for critical power "
       "infrastructure — catching the moment to act, before downtime.", 15, False, MUTE)])
# chips
chip(s, 0.95, 5.5, 3.5, 0.5, "Theme · Manufacturing", fill=PANEL, color=WHITE, size=12)
chip(s, 4.6, 5.5, 3.4, 0.5, "Gemini on Vertex AI", fill=PANEL, color=WHITE, size=12)
chip(s, 8.1, 5.5, 3.2, 0.5, "Deployed on Cloud Run", fill=PANEL, color=WHITE, size=12)
text(s, 0.95, 6.45, 11.5, 0.5,
     [("Live: kairos-ai-498775210896.asia-south1.run.app     ·     github.com/puneetpahuja-eaton/kairos-ai",
       11, False, MUTE)])

# =========================================================================== #
# Slide 2 — Hackathon context
# =========================================================================== #
s = slide()
header(s, "The arena", "Build in JAPAC. Build for the world.")
intro = ("The Google Cloud AI Builder Cup invites JAPAC's 15M+ developers to start with a real problem, "
         "build a working solution on Google Cloud, and prove that something built for a local need can scale globally.")
text(s, 0.85, 1.7, 11.6, 0.9, [(intro, 15, False, MUTE)])
cards = [
    ("Our theme", "Manufacturing — Intelligent Operations & Industrial Efficiency.", TEAL),
    ("The mandate", "Must use Google AI (Gemini / Gemma) and deploy on Cloud Run / GCP / Firebase.", BLUE),
    ("Our answer", "Kairos AI — a working, deployed, agentic reliability platform on Google Cloud.", GREEN),
]
cw = 3.75
for i, (h, b, acc) in enumerate(cards):
    l = 0.85 + i * (cw + 0.3)
    c = box(s, l, 2.8, cw, 2.1, fill=PANEL)
    box(s, l, 2.8, cw, 0.12, fill=acc, radius=0.3)
    text(s, l + 0.25, 3.05, cw - 0.5, 0.5, [(h, 17, True, WHITE)])
    text(s, l + 0.25, 3.6, cw - 0.5, 1.2, [(b, 13.5, False, MUTE)])
stat = box(s, 0.85, 5.3, 11.6, 1.3, fill=PANEL2)
fill_text(stat, [("$30,000 prize pool      ·      In-person Grand Finale in Singapore      ·      "
                  "Judged on Technical Merit & Gen AI (40%), Impact (25%), Innovation (25%), UX (10%)",
                  14, True, WHITE)], align=PP_ALIGN.CENTER)
footer(s, 2)

# =========================================================================== #
# Slide 3 — Problem
# =========================================================================== #
s = slide()
header(s, "The problem", "When power fails, someone has to be there", accent=AMBER)
lead = ("In the field, finding a fault still needs a human physically present. By the time an alarm is noticed, "
        "reported, and an engineer travels to site, the downtime has already compounded — and expert reliability "
        "engineers are scarce and cannot be everywhere at once.")
text(s, 0.85, 1.65, 11.6, 0.95, [(lead, 15, False, WHITE)])
pains = [
    ("No root-cause intelligence", "Tools only alert. They don't explain why sags, faults and alarms happen across panelboards and UPS systems — diagnosis stays manual and slow."),
    ("Manual commissioning & ops", "Configuring devices and troubleshooting still need on-site specialists and hand analysis of telemetry — slowing deployments and raising cost."),
    ("No prediction or correlation", "Monitoring lacks early warning and can't correlate cascading alarms along the chain (utility → transformer → UPS → PDU → load), masking the true cause."),
    ("No closed-loop remediation", "Today's systems automate only ~10% of the incident lifecycle (alerting). The other 90% — decide, act, verify — is manual, with no safe agentic workflow."),
]
cw, ch = 5.75, 1.7
for i, (h, b) in enumerate(pains):
    l = 0.85 + (i % 2) * (cw + 0.25)
    t = 2.75 + (i // 2) * (ch + 0.25)
    box(s, l, t, cw, ch, fill=PANEL)
    box(s, l, t, 0.1, ch, fill=AMBER, radius=0.3)
    text(s, l + 0.3, t + 0.18, cw - 0.55, 0.5, [(f"{i+1}.  {h}", 15.5, True, WHITE)])
    text(s, l + 0.3, t + 0.68, cw - 0.55, 1.0, [(b, 12, False, MUTE)])
footer(s, 3)

# =========================================================================== #
# Slide 4 — Solution
# =========================================================================== #
s = slide()
header(s, "The solution", "Kairos AI — the critical moment to act, before downtime")
big = box(s, 0.85, 1.65, 11.6, 1.2, fill=PANEL2)
fill_text(big, [("Kairos AI puts an expert reliability engineer inside every device — learning it from its own "
                 "documentation, watching it remotely 24/7, and closing the loop from detection to verified fix.",
                 16.5, True, WHITE)], align=PP_ALIGN.CENTER)
pillars = [
    ("Learn", "Ingests each device's datasheets, register maps and event-log structure (RAG on Vertex AI).", TEAL),
    ("Monitor", "Watches live telemetry and event logs remotely, around the clock.", BLUE),
    ("Diagnose", "Explains the root cause in plain English, with cited evidence from the device's own docs.", GREEN),
    ("Act & Verify", "Auto-resolves reversible faults or escalates — human-in-the-loop — then verifies the fix.", AMBER),
]
cw = 2.8
for i, (h, b, acc) in enumerate(pillars):
    l = 0.85 + i * (cw + 0.12)
    box(s, l, 3.2, cw, 2.5, fill=PANEL)
    box(s, l, 3.2, cw, 0.12, fill=acc, radius=0.3)
    text(s, l + 0.22, 3.45, cw - 0.44, 0.5, [(h, 18, True, acc)])
    text(s, l + 0.22, 4.0, cw - 0.44, 1.6, [(b, 13, False, MUTE)])
text(s, 0.85, 6.0, 11.6, 0.6,
     [("Seconds, not site visits — the same five-agent engine runs on both live streams and historical data.",
       14, True, TEAL)], align=PP_ALIGN.CENTER)
footer(s, 4)

# =========================================================================== #
# Slide 5 — Capabilities
# =========================================================================== #
s = slide()
header(s, "What it does", "One platform: onboard → learn → analyze → act")
caps = [
    ("Multi-device onboarding", "Register any number of devices with role-based access (admin / engineer / viewer).", TEAL),
    ("Learn from anything", "Upload PDFs, spreadsheets, notes — or pull from GitHub & Confluence. Embedded with Vertex AI into a per-device knowledge base.", BLUE),
    ("Ask the device", "An agentic assistant with Ask / Plan / Agent modes — clarifies first, then generates datasets, test cases, code and monitoring plans.", GREEN),
    ("Analyze, live or historic", "A five-agent engine scores uploaded datasets and live REST streams through one code path.", AMBER),
    ("Datasheet-driven live monitoring", "The agent reads the datasheet to choose which parameters to poll and decodes event-log codes automatically.", PINK),
    ("Auto-resolve or escalate", "Reversible faults self-heal; the rest escalate to a human — with downtime and cost avoided quantified.", TEAL),
]
cw, ch = 3.75, 1.65
for i, (h, b, acc) in enumerate(caps):
    l = 0.85 + (i % 3) * (cw + 0.3)
    t = 1.9 + (i // 3) * (ch + 0.3)
    box(s, l, t, cw, ch, fill=PANEL)
    box(s, l, t, 0.1, ch, fill=acc, radius=0.3)
    text(s, l + 0.28, t + 0.16, cw - 0.5, 0.6, [(h, 14.5, True, WHITE)])
    text(s, l + 0.28, t + 0.74, cw - 0.5, 0.85, [(b, 11.5, False, MUTE)])
footer(s, 5)

# =========================================================================== #
# Slide 6 — Devices & sectors
# =========================================================================== #
s = slide()
header(s, "Where it applies", "From one panel to an entire fleet")
text(s, 0.85, 1.6, 11.6, 0.6,
     [("Any device that exposes telemetry or logs — Kairos AI learns it from its own documentation.", 15, False, MUTE)])
text(s, 0.85, 2.35, 11.6, 0.4, [("DEVICES", 13, True, TEAL)])
devices = ["Panelboards", "Power & energy meters", "Switchgear", "UPS & batteries",
           "PDUs", "Transformers", "Motors & drives", "Breakers"]
for i, d in enumerate(devices):
    l = 0.85 + (i % 4) * 2.95
    t = 2.75 + (i // 4) * 0.75
    chip(s, l, t, 2.75, 0.6, d, fill=PANEL, color=WHITE, size=12.5)
text(s, 0.85, 4.45, 11.6, 0.4, [("SECTORS WE PROTECT", 13, True, AMBER)])
sectors = [("Hospitals & clinics", GREEN), ("Water & utilities", BLUE), ("Telecom networks", TEAL),
           ("Manufacturing plants", AMBER), ("Data centers", PINK), ("Substations & grid", GREEN)]
for i, (d, acc) in enumerate(sectors):
    l = 0.85 + (i % 3) * 3.95
    t = 4.9 + (i // 3) * 0.95
    sp = box(s, l, t, 3.75, 0.78, fill=PANEL)
    box(s, l, t, 0.1, 0.78, fill=acc, radius=0.3)
    text(s, l + 0.3, t + 0.19, 3.3, 0.5, [(d, 14, True, WHITE)])
footer(s, 6)

# =========================================================================== #
# Slide 7 — Architecture
# =========================================================================== #
s = slide()
header(s, "High-level architecture", "Built end-to-end on Google Cloud")
# Left: devices
lb = box(s, 0.55, 2.55, 2.25, 2.3, fill=PANEL2, line=TEAL, line_w=1.25)
fill_text(lb, [("Field power devices", 14, True, WHITE), ("Panelboard · UPS", 11, False, MUTE),
               ("Meter · PDU · Motor", 11, False, MUTE), ("", 6, False, MUTE),
               ("REST + Event logs", 11.5, True, TEAL)], align=PP_ALIGN.CENTER)
arrow(s, 2.9, 3.55, 0.5, 0.35, fill=TEAL)
# Center: Cloud Run panel
cp = box(s, 3.55, 1.95, 6.35, 4.35, fill=PANEL)
text(s, 3.75, 2.12, 6.0, 0.45, [("Kairos AI  ·  Cloud Run", 16, True, TEAL)])
services = [
    ("Gemini on Vertex AI", "reasoning & generation"),
    ("Vertex Embeddings", "RAG retrieval"),
    ("Firestore", "state & knowledge"),
    ("Cloud Storage", "telemetry & datasets"),
    ("BigQuery", "partitioned audit"),
    ("Secret Manager", "keys, no embedding"),
]
gx = [3.75, 5.82, 7.89]
gy = [2.7, 4.5]
cwi, chi = 1.95, 1.65
for i, (name, sub) in enumerate(services):
    l = gx[i % 3]
    t = gy[i // 3]
    sp = box(s, l, t, cwi, chi, fill=PANEL2, line=BLUE, line_w=1.0)
    fill_text(sp, [(name, 12, True, WHITE), (sub, 10, False, MUTE)], align=PP_ALIGN.CENTER)
arrow(s, 10.0, 3.55, 0.5, 0.35, fill=TEAL)
# Right: engineer
rb = box(s, 10.6, 2.55, 2.15, 2.3, fill=PANEL2, line=GREEN, line_w=1.25)
fill_text(rb, [("Reliability engineer", 13.5, True, WHITE), ("& operator", 13.5, True, WHITE),
               ("", 6, False, MUTE), ("Dashboard · Chat", 11, False, MUTE),
               ("Alerts · Work orders", 11, False, MUTE)], align=PP_ALIGN.CENTER)
text(s, 0.85, 6.55, 11.6, 0.4,
     [("Runs as a dedicated service account via ADC — no API keys embedded in the container. Scales to zero.",
       11.5, False, MUTE)], align=PP_ALIGN.CENTER)
footer(s, 7)

# =========================================================================== #
# Slide 8 — Agents
# =========================================================================== #
s = slide()
header(s, "The agents", "A closed loop of five agents, guided by a Gemini knowledge plane")
# Gemini plane (top)
gp = box(s, 0.85, 1.6, 11.6, 1.0, fill=PANEL2, line=TEAL, line_w=1.25)
fill_text(gp, [("Gemini Knowledge & Agentic Plane", 14.5, True, TEAL),
               ("RAG retrieval over device docs  ·  Ask / Plan / Agent assistant  ·  dataset & live-monitor-plan generators",
                11.5, False, WHITE)], align=PP_ALIGN.CENTER)
# down arrow into Diagnose
arrow(s, 5.72, 2.62, 0.35, 0.45, fill=TEAL, shape_type=MSO_SHAPE.DOWN_ARROW)
# five agents
agents = [
    ("1 · Monitor", "Detects anomalies in live & historic telemetry (robust-Z + Isolation Forest).", TEAL),
    ("2 · Diagnose", "Root cause via topology correlation + Gemini hypotheses with cited evidence.", BLUE),
    ("3 · Decide", "Confidence-gated autonomy — weighs reversibility and asset criticality.", GREEN),
    ("4 · Act", "Self-heals reversible faults or hands off to a human for approval.", AMBER),
    ("5 · Verify", "Confirms the fix worked; scores downtime and cost avoided.", PINK),
]
aw, ah = 2.2, 2.45
xs = [0.7, 3.15, 5.6, 8.05, 10.5]
for i, (h, b, acc) in enumerate(agents):
    l = xs[i]
    box(s, l, 3.25, aw, ah, fill=PANEL, line=acc, line_w=1.25)
    box(s, l, 3.25, aw, 0.12, fill=acc, radius=0.3)
    text(s, l + 0.18, 3.45, aw - 0.36, 0.5, [(h, 13.5, True, acc)])
    text(s, l + 0.18, 3.95, aw - 0.36, 1.6, [(b, 11, False, WHITE)])
    if i < 4:
        arrow(s, l + aw + 0.0, 4.25, 0.26, 0.4, fill=MUTE)
# human-in-the-loop marker under Decide/Act
hil = box(s, 5.6, 5.85, 4.65, 0.55, fill=PANEL2, line=AMBER, line_w=1.0)
fill_text(hil, [("Human-in-the-loop approval gate at Decide → Act", 11.5, True, AMBER)], align=PP_ALIGN.CENTER)
# closed-loop return
loop = box(s, 0.7, 6.55, 11.0, 0.5, fill=None, line=TEAL, line_w=1.25, radius=0.2)
fill_text(loop, [("↺  Continuous closed loop — Verify feeds Monitor, so the engine keeps learning",
                  11.5, True, TEAL)], align=PP_ALIGN.CENTER)
footer(s, 8)

# =========================================================================== #
# Slide 9 — Impact: downtime & cost
# =========================================================================== #
s = slide()
header(s, "Quantified impact", "Hours of downtime → minutes", accent=GREEN)
rows = [
    ("Case", "Fault (asset)", "Path", "Downtime avoided", "$ avoided"),
    ("C001", "Voltage sag (Main Incomer)", "Auto-resolved", "40 min", "$34,000"),
    ("C002", "Overload (Feeder PDU-2)", "Auto-resolved", "25 min", "$11,250"),
    ("C003", "Battery degradation (UPS-3)", "Escalated (early detection)", "48 min", "$40,800"),
    ("C004", "Thermal runaway (UPS-1)", "Auto-resolved", "55 min", "$46,750"),
    ("C005", "Harmonic distortion (PDU-1)", "Auto-resolved", "35 min", "$15,750"),
    ("C006", "Breaker trip (BRK-4)", "Auto-resolved", "20 min", "$5,000"),
    ("Total · 6 incidents", "—", "5 auto / 1 escalated", "223 min", "$153,550"),
]
tbl_w = 8.3
rows_n = len(rows)
gfx = s.shapes.add_table(rows_n, 5, Inches(0.85), Inches(1.75), Inches(tbl_w), Inches(4.2)).table
gfx.columns[0].width = Inches(1.5)
gfx.columns[1].width = Inches(2.7)
gfx.columns[2].width = Inches(1.9)
gfx.columns[3].width = Inches(1.3)
gfx.columns[4].width = Inches(0.9)
for ri, row in enumerate(rows):
    for ci, val in enumerate(row):
        cell = gfx.cell(ri, ci)
        cell.margin_left = Inches(0.08); cell.margin_right = Inches(0.06)
        cell.margin_top = Inches(0.03); cell.margin_bottom = Inches(0.03)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        if ri == 0:
            cell.fill.solid(); cell.fill.fore_color.rgb = TEAL
            col, bold, size = DARKTEXT, True, 11.5
        elif ri == rows_n - 1:
            cell.fill.solid(); cell.fill.fore_color.rgb = PANEL2
            col, bold, size = WHITE, True, 11.5
        else:
            cell.fill.solid(); cell.fill.fore_color.rgb = PANEL if ri % 2 else BG
            col, bold, size = WHITE, False, 11
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run(); run.text = val
        run.font.size = Pt(size); run.font.bold = bold; run.font.color.rgb = col; run.font.name = FONT
# side stats
sx = 9.4
stats = [("MTTR", "tens of hours → 1–2 cycles", TEAL),
         ("Truck-rolls", "fewer repeat visits — right-part-first RCA", BLUE),
         ("Monitoring", "becomes an outcome-based SLA you can price", GREEN)]
for i, (h, b, acc) in enumerate(stats):
    t = 1.75 + i * 1.15
    box(s, sx, t, 3.3, 1.0, fill=PANEL)
    box(s, sx, t, 0.1, 1.0, fill=acc, radius=0.3)
    text(s, sx + 0.28, t + 0.14, 2.9, 0.4, [(h, 14, True, WHITE)])
    text(s, sx + 0.28, t + 0.5, 2.9, 0.5, [(b, 11, False, MUTE)])
text(s, 0.85, 6.1, 11.9, 0.7,
     [("Illustrative synthetic scenarios — not realized production savings. Downtime cost rates: "
       "critical $850/min, high $450/min, medium $250/min. Every incident is scored against a 'no-platform' baseline.",
       10.5, False, MUTE)])
footer(s, 9)

# =========================================================================== #
# Slide 10 — Social impact
# =========================================================================== #
s = slide()
header(s, "Why it matters", "Keeping the lights on for the communities that depend on them", accent=PINK)
lead = ("Hospitals, clean-water pumping, vaccine cold-chains, telecom and schools all run on reliable power. "
        "Cutting fault response from hours to seconds protects the most vulnerable — especially in remote regions "
        "and during climate-stressed grid events.")
text(s, 0.85, 1.65, 11.6, 0.9, [(lead, 15, False, WHITE)])
impacts = [
    ("Essential services uptime", "Less downtime at hospitals, water and telecom keeps life-critical services running.", GREEN),
    ("Expertise for everyone", "A junior technician — or no one on site — gets senior-engineer diagnosis grounded in the device's own manuals.", BLUE),
    ("Safety", "Overload, thermal runaway and harmonic faults are fire and injury hazards; early remote detection prevents accidents.", AMBER),
    ("Sustainability", "Catches wasted energy (power factor, harmonics, imbalance), extends equipment life, and cuts diesel-backup and truck-roll emissions.", TEAL),
    ("Resilience", "Faster autonomous response hardens critical infrastructure against outages as grids come under stress.", PINK),
]
cw, ch = 3.75, 1.7
for i, (h, b, acc) in enumerate(impacts):
    l = 0.85 + (i % 3) * (cw + 0.3)
    t = 2.75 + (i // 3) * (ch + 0.25)
    box(s, l, t, cw, ch, fill=PANEL)
    box(s, l, t, 0.1, ch, fill=acc, radius=0.3)
    text(s, l + 0.28, t + 0.16, cw - 0.5, 0.55, [(h, 15, True, WHITE)])
    text(s, l + 0.28, t + 0.72, cw - 0.5, 0.9, [(b, 11.5, False, MUTE)])
footer(s, 10)

# =========================================================================== #
# Slide 11 — Why we win
# =========================================================================== #
s = slide()
header(s, "Why Kairos AI", "Meaningful Gen AI, honest by design")
wins = [
    ("Deep, real Google Cloud AI", "Gemini on Vertex AI, Vertex embeddings, Firestore, Cloud Storage, BigQuery, Secret Manager, Cloud Run — not a token API call.", TEAL),
    ("One engine, live + historic", "The same five-agent brain diagnoses a replayed dataset and a live warm-up-then-stream — a genuine differentiator.", BLUE),
    ("The agent decides what to watch", "It reads the datasheet to pick parameters and thresholds and decodes event logs — monitoring configures itself.", GREEN),
    ("Honest by design", "Offline fallbacks are labeled and never shown as Google AI; demo data is synthetic and disclosed; humans approve every action.", AMBER),
]
cw, ch = 5.75, 1.85
for i, (h, b, acc) in enumerate(wins):
    l = 0.85 + (i % 2) * (cw + 0.25)
    t = 1.85 + (i // 2) * (ch + 0.25)
    box(s, l, t, cw, ch, fill=PANEL)
    box(s, l, t, 0.1, ch, fill=acc, radius=0.3)
    text(s, l + 0.3, t + 0.2, cw - 0.55, 0.5, [(h, 16.5, True, WHITE)])
    text(s, l + 0.3, t + 0.78, cw - 0.55, 1.0, [(b, 12.5, False, MUTE)])
badge = box(s, 0.85, 5.8, 11.6, 0.8, fill=PANEL2)
fill_text(badge, [("121 automated tests  ·  deployed & verified on Cloud Run  ·  Firestore-backed  ·  Gemini on Vertex AI",
                   13, True, TEAL)], align=PP_ALIGN.CENTER)
footer(s, 11)

# =========================================================================== #
# Slide 12 — Closing
# =========================================================================== #
s = slide()
band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.28), Inches(SH))
band.fill.solid(); band.fill.fore_color.rgb = TEAL; band.line.fill.background(); _no_shadow(band)
circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9.8), Inches(3.0), Inches(5.5), Inches(5.5))
circ.fill.solid(); circ.fill.fore_color.rgb = PANEL; circ.line.fill.background(); _no_shadow(circ)
text(s, 0.95, 2.1, 11.2, 0.5, [("THE VISION", 13, True, TEAL)])
text(s, 0.9, 2.55, 11.4, 1.4, [("Start with one device.", 44, True, WHITE), ("Scale to the world.", 44, True, TEAL)])
text(s, 0.95, 4.6, 10.8, 0.7,
     [("Kairos AI turns every power device into its own reliability engineer — so the communities that depend on "
       "reliable power are never left waiting in the dark.", 15, False, MUTE)])
chip(s, 0.95, 5.7, 5.6, 0.55, "Live  ·  kairos-ai-498775210896.asia-south1.run.app", fill=PANEL2, color=WHITE, size=12)
chip(s, 6.75, 5.7, 4.3, 0.55, "github.com/puneetpahuja-eaton/kairos-ai", fill=PANEL2, color=WHITE, size=12)
text(s, 0.95, 6.5, 11.0, 0.5, [("Kairos AI — the moment to act, every time.", 15, True, TEAL)])

out = HERE / "Kairos-AI-Pitch-Deck.pptx"
prs.save(str(out))
print(f"Saved {out}  ({len(prs.slides._sldIdLst)} slides)")
