# Kairos AI — Demo Video Script (story-first, ~3:55)

Rules allow 3-4 min. Pace ~160 words/min. Speak with conviction - this is a story, not a feature list.
Part 1 = YOU speaking the problem + solution + features. Part 2 = the agents (with a worked example) + stack + results.

## Pre-recording checklist
- [ ] Deployed app open, logged in as `admin@kairos.ai`.
- [ ] Demo device **"Demo - Power Distribution Panel"** ready (3 assets; after a fresh deploy, open it once so it finishes seeding).
- [ ] GitHub repo + Confluence page ingested (Integrations -> Saved knowledge links).
- [ ] Ask the device: a dataset already generated.
- [ ] Live Monitoring: **Use built-in simulated feed** ON + **Deep analysis** ticked (ready to Start).
- [ ] 1080p, readable zoom, sidebar expanded. Record in segments; stitch.

---

## (OPTIONAL) Intro — 0:00-0:08
| SHOW | SAY |
|---|---|
| You on camera / cover | "Hi, I'm Puneet Pahuja, team lead of Kairos AI, with Khushboo Verma and Anurag Verma. Let me show you what we built - and why." |

---

## PART 1 — THE STORY + THE FEATURES (~0:00-2:05)

| Time | SHOW ON SCREEN | SAY (word-for-word) |
|---|---|---|
| 0:00-0:26 | Power-outage / hospital imagery / cover | "Think about the last time your power went out - that sudden silence, that small moment of helplessness. Now imagine it isn't your home. It's a hospital mid-surgery. A water plant for a whole city. A factory line that just stopped cold. Behind each one is a power device that failed - and an engineer who has to drop everything and drive to the site to find out why." |
| 0:26-0:42 | Problem visual / on camera | "Here's the hard truth: finding the fault still needs a human physically there. The device only raises an alarm - it can't tell you why it failed or how to recover. Expert engineers are rare, and they can't be everywhere. So the world waits - in the dark." |
| 0:42-0:58 | Kairos AI Home / logo | "So we asked a simple question: what if every device could explain itself - and heal itself? That's Kairos AI. We put an expert reliability engineer inside every power device - it learns each device from its own manuals, watches it around the clock, and diagnoses and fixes faults in seconds, remotely." |
| 0:58-1:10 | Device Manager + Data Sources | "Getting started is simple. You onboard any device - a panelboard, a meter, a UPS - and feed it knowledge: upload datasheets, or pull straight from GitHub and Confluence. Kairos AI reads and remembers every page." |
| 1:10-1:32 | Ask the device (show Ask / Plan / Agent + a generated artifact) | "The heart of the product is 'Ask the device' - think of it as a personal assistant that knows everything about your device. Ask it what went wrong, how to recover, what a reading means. Or ask it to generate a historic dataset, test cases, a summary, even a full monitoring plan. Three modes - Ask, Plan, and Agent - so it can answer you, plan with you, or go do the work itself." |
| 1:32-2:05 | **Live Monitoring** (show params streaming) | "And this is the feature we're most excited about - live monitoring. From anywhere - your home, your phone - you can watch a device's voltage, current, every parameter, in real time, as if you were standing right in front of the panel. The agent polls the device on a schedule and streams the readings straight into our analysis engine, flagging any problem the moment it appears. Now, for this demo, we generated realistic test data so we can safely showcase it - but in production, the device connects securely through an on-prem connector or a VPN, and the exact same engine runs on that live stream." |

---

## PART 2 — THE 5 AGENTS (with a worked example), STACK & PROOF (~2:05-3:55)

| Time | SHOW ON SCREEN | SAY (word-for-word) |
|---|---|---|
| 2:05-2:18 | Agents diagram (5 agents) | "Behind all of this is the engine - five AI agents that work as a team on every reading, live or historical. Let me walk you through them with one real fault from our demo: a voltage sag on the main incomer." |
| 2:18-2:32 | Highlight Monitor -> the sag on the chart | "First, **Monitor**. It constantly re-scores every asset against its own healthy baseline. It catches Phase-A voltage on the incomer dropping from two-thirty down to two-oh-one volts - statistically abnormal - and raises a flag." |
| 2:32-2:48 | Highlight Diagnose -> case + citation | "Second, **Diagnose**. It asks *why*. Using Gemini, it reads the event codes and the device's own manual, and correlates across the power chain to rule out downstream symptoms. Its verdict: a genuine voltage sag at the incomer - with ninety-eight percent confidence, and the manual page it used, cited." |
| 2:48-3:02 | Highlight Decide | "Third, **Decide** - the safety brain. Is it safe to fix automatically? A voltage sag is reversible and confidence is high, so it approves autonomous action. But for something irreversible - say a failing battery - it deliberately stops and routes it to a human." |
| 3:02-3:16 | Highlight Act -> the escalation example | "Fourth, **Act**. For the sag, it executes the fix - stabilize voltage and shift load to the healthy feed. And when it *can't* safely fix something - like the sustained overload on motor seven - it raises a work order and alerts the on-call engineer: 'motor seven is overloaded, a technician is needed now.'" |
| 3:16-3:30 | Highlight Verify -> case closes; metrics tick up | "Fifth, **Verify** - the closed loop. It never just assumes success. On the next reading it re-checks the asset, sees the voltage back to normal, and closes the case as self-healed - booking the downtime and cost avoided. If it hadn't recovered, it escalates immediately." |
| 3:30-3:42 | Analysis metrics + Google Cloud sidebar (Store firestore, Model Vertex AI) | "Across three assets it caught every fault, diagnosed each with a hundred percent accuracy, auto-resolved two and escalated one - saving sixty minutes of downtime and over forty thousand dollars. Illustrative numbers - but the leverage is real. And it all runs on Google Cloud: Gemini on Vertex AI, Vertex embeddings, Firestore, Cloud Storage, BigQuery and Secret Manager, deployed on Cloud Run." |
| 3:42-3:55 | Closing slide | "Power is the one thing our world can't live without. Kairos AI makes sure that when something goes wrong, the help is already inside the device - so hospitals stay open, water keeps flowing, and no one is left waiting in the dark. That's Kairos AI. Thank you." |

---

## The 5 agents in one line each (memorize)
- **Monitor** - spots the abnormal reading (voltage 230 -> 201).
- **Diagnose** - explains *why*, cited from the manual (voltage sag, 98% confidence).
- **Decide** - is it safe to auto-fix? (reversible + confident = yes; irreversible = human).
- **Act** - executes the fix, or raises a work order and alerts the engineer.
- **Verify** - re-checks the next reading; closes if healed, escalates if not.

## Why this version is impactful
- Opens on a feeling everyone knows, then raises the stakes (hospitals, water, factories).
- **Live monitoring is headlined** as the signature feature, with an honest "demo uses generated data" caveat.
- The 5 agents are explained through **one concrete fault**, so anyone understands them.
- Closes on the human stakes - that wins Most Impactful and Social Choice.

## Delivery tips
- Slow down on the hook and the close; keep the agent walkthrough crisp and visual - point at each agent as you name it.
- Numbers match the live demo screen (100% accuracy, 2 auto-resolved / 1 escalated, 60 min, ~$40k). Say "illustrative" once.
- Keep total under 4:00; this lands ~3:55 at a natural pace. If tight, trim the onboarding line (1:10-1:32 intro) slightly.
