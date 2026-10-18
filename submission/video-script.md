# Kairos AI — 3-Minute Demo Video Script

Target pace: ~155 words/min. Speak clearly and with energy. Pause ~0.5s between sentences.

## Pre-recording checklist (stage these BEFORE you record)
- [ ] Logged in to the deployed app as `admin@kairos.ai` on the public URL.
- [ ] Demo device **"Demo - Power Distribution Panel"** present (3 assets, dataset mode).
- [ ] One GitHub repo **already ingested** so **Integrations -> Saved knowledge links** shows it.
- [ ] One Confluence page already ingested (shows in Saved knowledge links).
- [ ] In **Ask the device**: a dataset already generated (so you can show the result instantly).
- [ ] In **Live Monitoring**: a monitoring plan already built; ready to click **Start**.
- [ ] Browser zoomed so text is readable; sidebar expanded; 1080p screen recording.
- [ ] Record in 3 one-minute segments; stitch together. Keep each click smooth.

---

## MINUTE 1 (0:00-1:00) - Problem - Social impact - Solution - Agents - Start analysis

| Time | SHOW ON SCREEN | SAY (word-for-word) |
|---|---|---|
| 0:00-0:12 | Cover slide (or app Home) | "Power devices run our hospitals, water plants, factories and telecom. But when one fails, finding the fault still needs an engineer physically on site - and by the time they arrive, the downtime has already cost thousands." |
| 0:12-0:22 | Cover / problem visual | "Expert reliability engineers are scarce, and they can't be everywhere at once. That delay is the real problem - and it hits the communities that depend on reliable power the hardest." |
| 0:22-0:35 | App Home - "Kairos AI" header | "Meet Kairos AI - an expert reliability engineer inside every device. It learns each device from its own documents, watches it remotely around the clock, and diagnoses and resolves faults in seconds - not site visits." |
| 0:35-0:52 | Agents diagram (deck slide 3) | "Under the hood, five agents work as a closed loop. Monitor detects anomalies. Diagnose finds the root cause with cited evidence from the device's manuals. Decide weighs confidence and risk. Act self-heals reversible faults or escalates to a human. And Verify confirms the fix and scores the downtime and cost avoided." |
| 0:52-1:00 | Analysis page -> select **Demo - Power Distribution Panel** -> click Run (it starts stepping) | "It all runs on Google Cloud with Gemini on Vertex AI. Let me start an analysis on our demo panel now - it'll run while I show you the platform." |

---

## MINUTE 2 (1:00-2:00) - Login - Users & roles - Device - Integrations - Ask - Live

| Time | SHOW ON SCREEN | SAY (word-for-word) |
|---|---|---|
| 1:00-1:10 | Sidebar showing "Store: firestore - Model: Vertex AI" and role | "Kairos AI is multi-tenant and secure. We sign in with role-based access - admin, engineer and viewer - so configuration, operations and read-only views are cleanly separated." |
| 1:10-1:22 | **User Admin** page - add a user, pick a role | "From User Admin, an admin creates users and assigns roles. Engineers run analysis and approve actions; viewers only see results. For critical infrastructure, that separation of duties matters." |
| 1:22-1:32 | **Device Manager** - show registered devices / Add a device | "In Device Manager we onboard any device - panelboards, meters, UPS, breakers - and each one gets its own private knowledge base." |
| 1:32-1:44 | **Integrations** - point to GitHub repo, Confluence page, Saved knowledge links | "We feed it knowledge in Data Sources and Integrations - upload datasheets, or pull directly from GitHub and Confluence. Everything is embedded with Vertex AI into a per-device knowledge base the agents can cite." |
| 1:44-1:54 | **Ask the device** - show Ask/Plan/Agent toggle; show the already-generated dataset | "Ask the device is our agentic assistant, with Ask, Plan and Agent modes. It clarifies before acting, then generates datasets, test cases, even code - all grounded in that device's documents." |
| 1:54-2:00 | **Live Monitoring** - show the plan, click Start (readings stream) | "And Live Monitoring is self-configuring - the agent reads the datasheet to pick parameters and thresholds, decodes event logs, and streams live data into the very same engine." |

---

## MINUTE 3 (2:00-3:00) - Analysis results - Future - Close

| Time | SHOW ON SCREEN | SAY (word-for-word) |
|---|---|---|
| 2:00-2:14 | **Analysis** page - results now ready; scroll the dashboard | "Now back to our analysis - it's finished. Kairos AI processed the telemetry across three assets and caught every injected fault: a voltage sag, an overload, and rising harmonic distortion." |
| 2:14-2:30 | Point to metrics: Diagnosis accuracy, Downtime avoided, Cost avoided | "It diagnosed each root cause with a hundred percent accuracy against ground truth, auto-resolved the reversible faults, escalated the rest, and quantified the impact - minutes of downtime and thousands of dollars avoided, every incident scored against a no-platform baseline." |
| 2:30-2:44 | Open a case - show Monitor->Diagnose->Decide->Act->Verify trail + citation | "Every decision is fully traceable - the evidence, the cited manual passage, the human approval, and the verification - so engineers can trust it. And the same engine runs on both historical data and live streams." |
| 2:44-3:00 | Closing slide (vision) | "This is just the beginning. Next: real sensor integration at the edge, full fleet modeling, predictive maintenance, and support for any industrial protocol. Kairos AI turns every device into its own reliability engineer - so the communities that depend on reliable power are never left in the dark. Thank you." |

---

## Delivery tips
- **Energy and clarity beat speed.** If you run long, cut the least-important clause, not whole sections.
- **Mouse = pointer.** Move deliberately to exactly what you mention; don't wander.
- **Show, then speak** for the money moments (accuracy %, cost avoided) - let the number land.
- End on the social-impact line; it's what wins "Most Impactful" and "Social Choice".
- Keep total **under 3:00** (hard rule). Aim for ~2:50 to be safe.
