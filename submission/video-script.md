# Kairos AI — Demo Video Script (story-first, ~3:45)

Target ~3:45 (rules allow 3-4 min). Pace ~160 words/min. Speak with conviction - this is a story, not a feature list.
Part 1 = YOU speaking the problem + solution + features (on camera, or voiceover over the matching screens).
Part 2 = LIVE demo + Google Cloud stack + results. End on a high note.

## Pre-recording checklist
- [ ] Deployed app open, logged in as `admin@kairos.ai`.
- [ ] Demo device **"Demo - Power Distribution Panel"** ready (3 assets).
- [ ] GitHub repo + Confluence page ingested (Integrations -> Saved knowledge links).
- [ ] Ask the device: a dataset already generated.
- [ ] Live Monitoring: **Use built-in simulated feed** ON + **Deep analysis** ticked (ready to Start).
- [ ] 1080p, readable zoom, sidebar expanded. Record in segments; stitch.

---

## (OPTIONAL) Intro — 0:00-0:08
| SHOW | SAY |
|---|---|
| You on camera / cover | "Hi, I'm Puneet Pahuja, team lead of Kairos AI, with Khushboo Verma and Anurag Verma. Let me tell you why we built this." |
*(If you use this, everything below shifts ~8 seconds; total stays within 4:00.)*

---

## PART 1 — THE STORY (you speaking) ~0:00-2:00

| Time | SHOW ON SCREEN | SAY (word-for-word) |
|---|---|---|
| 0:00-0:28 | You on camera / power-outage & hospital imagery / cover | "Think about the last time your power went out - that sudden silence, that small moment of helplessness. Now imagine it isn't your home. It's a hospital mid-surgery. A water plant for an entire city. A factory line that just stopped cold. Behind each one is a power device that failed - and an engineer who has to drop everything, drive to the site, and find out what went wrong. Every minute on the road, the cost climbs and the risk grows." |
| 0:28-0:45 | Problem visual / stay on camera | "Here's the hard truth: today, finding the fault still needs a human physically there. The device only raises an alarm - it can't tell you why it failed, or how to recover. Expert engineers are rare, and they can't be everywhere at once. So the world waits - in the dark." |
| 0:45-1:02 | Kairos AI Home / logo | "So we asked one simple question: what if every device could explain itself - and heal itself? That's Kairos AI. We put an expert reliability engineer inside every power device. It learns each device from its own manuals, watches it around the clock, and diagnoses and resolves faults in seconds - remotely." |
| 1:02-1:15 | Device Manager + Data Sources | "Getting started is simple. You onboard any device - a panelboard, a meter, a UPS - and feed it knowledge: upload datasheets, or pull straight from GitHub and Confluence. Kairos AI reads and remembers every page." |
| 1:15-1:40 | Ask the device (show 3 modes + a generated artifact) | "The heart of Kairos AI is 'Ask the device.' Think of it as a personal assistant that knows everything about your device. Ask it anything - what went wrong, how to recover, what a reading means. Or ask it to generate a historic dataset, test cases, a summary, even a complete live-monitoring plan. Three modes - Ask, Plan, and Agent - so it can answer you, plan with you, or go and do the work itself." |
| 1:40-2:00 | Live Monitoring screen | "Next - live monitoring. Imagine watching your device's voltage or current live, from your home, as if you were standing right in front of it. Kairos AI polls every parameter in real time. For this demo I stream a simulated feed into the same engine; in production, the device connects securely through an on-prem connector or a VPN." |

---

## PART 2 — THE AGENTS, THE STACK, THE PROOF ~2:00-3:44

| Time | SHOW ON SCREEN | SAY (word-for-word) |
|---|---|---|
| 2:00-2:30 | Agents diagram (5 agents) | "And the core of it all - Analysis, powered by five AI agents working as a team. Feed it data, and they go to work. Monitor flags anything abnormal. Diagnose explains the root cause, cited from the device's own manuals. Decide weighs the risk. Act auto-resolves what it can safely fix - and when it can't, it escalates: imagine an instant alert to the on-call engineer - 'voltage is dropping on the main incomer, repair needed now.' Then Verify confirms the fix actually worked. That one loop saves hours of downtime, cuts the effort, and saves real money." |
| 2:30-2:47 | Live app montage: login -> device -> Ask -> Live Start -> Analysis Run | "Now let me show you - live, and deployed on Google Cloud. We sign in with role-based access, onboard a device, ask it questions, start live monitoring, and run an analysis on our demo panel." |
| 2:47-3:05 | Google Cloud stack slide / sidebar backends | "Everything runs on Google Cloud. Gemini 2.5 Flash on Vertex AI is the brain - the reasoning and the diagnosis. Vertex AI embeddings ground every answer in the device's own documents. Firestore stores the platform, Cloud Storage the data, BigQuery the audit trail, and Secret Manager the keys - all deployed on Cloud Run." |
| 3:05-3:28 | Analysis results; point to accuracy, downtime, cost | "And here's the analysis, complete. Across three assets, Kairos AI caught every fault - a voltage sag, an overload, and harmonic distortion - and explained each one: what went wrong, and why. It auto-resolved the reversible faults and escalated the rest. The result: two hundred twenty-three minutes of downtime avoided, and over a hundred and fifty thousand dollars saved. These numbers are illustrative - but the leverage is real: faults caught in seconds, with no one on site." |
| 3:28-3:44 | Closing slide | "Power is the one thing our modern world simply can't live without. Kairos AI makes sure that when something goes wrong, the help is already inside the device - so hospitals stay open, water keeps flowing, and no one is left waiting in the dark. That's Kairos AI. Thank you." |

---

## Why this version is impactful
- **Opens on a feeling everyone knows** (power going out) then raises the stakes to hospitals, water, factories - relatable + emotional.
- **Names the villain** (you only get an alarm; experts can't be everywhere) before the hero.
- **"Personal assistant that knows everything about the device"** frames Ask the device simply and memorably.
- **Shows the agents as a team** with a concrete escalation ("voltage dropping, repair now").
- **Closes on the human stakes**, not the tech - that wins Most Impactful and Social Choice.

## Delivery tips
- Slow down on the hook (0:00-0:28) and the close - let them breathe. Speed up slightly through features.
- Mouse = pointer; move to exactly what you name.
- Show, THEN say the big numbers (100% diagnosis, 223 min, ~$150k).
- Say "illustrative" once (it's in the line) - honesty scores with judges.
- Keep total under 4:00; this lands ~3:44 at a natural pace.
