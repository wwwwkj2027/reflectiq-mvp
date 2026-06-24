# ReflectIQ MVP

A Python Flask web app that guides students through a Socratic three-step reflection workflow, classifies responses into learning signals, and surfaces anonymous aggregated patterns to faculty.

## Run & Operate

- **ReflectIQ** workflow — runs `cd reflectiq && python3 app.py` on port 8000
- Required secrets: `OPENAI_API_KEY` — for follow-up question generation and signal classification

### How to add or replace the OpenAI API key

1. In Replit, open **Secrets** (the 🔒 lock icon in the left sidebar)
2. Set the secret name to `OPENAI_API_KEY` and paste your key as the value
3. Restart the **ReflectIQ** workflow for the key to take effect
4. Visit `/api/test-openai` to verify the key is working — the result appears in the browser (no key is ever shown)

If the key test fails, the server console will print the real error (e.g., `insufficient_quota`, `invalid_api_key`, `model_not_found`, or a permission error). The key value is never logged or sent to the browser.

## Stack

- Python 3.11 + Flask 3
- OpenAI `gpt-4o-mini` for Socratic follow-ups and learning signal classification
- SQLite for anonymous reflection storage (`reflectiq/data/reflections.db`)
- Jinja2 templates + vanilla CSS/JS (no frontend framework)

## Course

**Emerging Technologies** · MASY1-GC 1800 · Summer 2026 (NYU)
11 weekly topics from Origins of Technology through POC and POV implementation.

## Student vs. Faculty Views

### Student side — `/` or `/reflect` or `/student`

Students pick a topic and complete a 4-step Socratic reflection:

1. **Step 1 — Identity:** Name and student ID (stored separately for completion tracking only)
2. **Step 2 — Q1:** What did you learn from this topic?
3. **Step 3 — Q2:** AI-generated Socratic follow-up question (generated live via OpenAI)
4. **Step 4 — Q3:** Why does this concept matter, and how would you apply it to a real business or technology case?

The student page shows no dashboard analytics, no class patterns, and no other students' data.

### Faculty side — `/dashboard` or `/faculty`

Faculty see aggregated, anonymous class-level learning intelligence:

1. **KPI Summary** — total reflections, topics covered, comprehension rate, action signal count
2. **Top Cluster Cards** — enriched theme + faculty insight + recommended action per signal cluster
3. **Signal Distribution** — bar chart of all 6 learning signal types
4. **Action Signals** — flagged patterns that may warrant instructional response
5. **Topic-Level Pattern View** — dominant signals per topic

Faculty pages show no individual student content, scores, grades, or rankings.

### Completion page — `/completion`

Faculty-only. Shows: `student_name`, `student_id`, `topic`, `timestamp`.
Never shows Q1, Q2, Q3 answers, signal type, or AI classification.

### Governance page — `/governance`

Explains the data separation architecture:
- Completion is identifiable
- Content analysis is anonymized
- Dashboard insight is aggregated

## Dummy Data / Demo Mode

The dashboard includes a **Load Dummy Data** button that pre-populates the system with 19 sample anonymous reflections across 5 topics and 10 sample completion records. This lets you explore the full dashboard without waiting for real student submissions.

**To activate demo mode:**
1. Open the Faculty Dashboard (`/dashboard`)
2. Click **Load Dummy Data**
3. A yellow banner appears: "Demo data shown for MVP testing"

**To remove demo data:**
1. Click **Clear Demo Data** on the dashboard
2. All demo records are removed; real student data is unaffected

Demo data covers these topics:
- Introduction: Origins of Technology & Life Cycle Stages (5 reflections)
- Diffusion of Innovation (4 reflections)
- User-Led Adoption of Emerging Technologies (4 reflections)
- Emerging Technologies Classification and Adoption Strategy (3 reflections)
- Implementing Emerging Technologies — Proof of Value (3 reflections)

## Where things live

- `reflectiq/app.py` — Flask routes, OpenAI calls, DB logic, dummy data
- `reflectiq/data/courses.json` — NYU Emerging Technologies syllabus (11 topics, full metadata)
- `reflectiq/data/reflections.db` — SQLite DB (auto-created on first run)
- `reflectiq/templates/` — Jinja2 HTML templates
- `reflectiq/static/css/style.css` — all styles
- `reflectiq/static/js/reflect.js` — multi-step form logic (4 steps)

## Governance Controls (enforced in code)

| Rule | How it's enforced |
|---|---|
| No grading | Reflection data is never stored with grade fields; dashboard has no grade column |
| No ranking | No ORDER BY student identity; no individual comparison query exists |
| No individual attribution | Dashboard reads only from `anonymous_analysis`; never joins with `completion_log` |
| Completion separate from analysis | Two tables, never joined — `completion_log` (identity) and `anonymous_analysis` (content) |
| Anonymous analysis only | `anonymous_analysis` has no `student_name`, `student_id`, `email`, `NetID` columns |
| Aggregated dashboard only | All dashboard queries use GROUP BY + COUNT; clusters < 3 responses are suppressed |
| Faculty decision remains final | All action signals include "Faculty review required before action" disclaimer |
| AI signals require faculty review | Classification happens server-side; no automated action is triggered by any signal |

**Aggregation threshold = 3:** clusters with fewer than 3 responses are suppressed in the dashboard for privacy.

## Architecture decisions

- **SQLite over Postgres** for MVP: zero-config, single-file, sufficient for classroom scale
- **gpt-4o-mini for both tasks**: fast and cheap; follow-up generation uses temp=0.7 for variety, classification uses temp=0.2 for determinism
- **Two-table separation**: `completion_log` stores name+student_id; `anonymous_analysis` stores reflection content with NO student identifiers — they are never joined
- **Aggregation threshold = 3**: clusters with fewer than 3 responses are suppressed in the dashboard for privacy
- **Classification happens server-side at submit**: not exposed to the client, keeping the signal rubric internal
- **is_demo flag**: demo records are tagged with `is_demo=1` in both tables; clearing demo data removes only those rows without affecting real submissions

## Learning signals

| Signal | Meaning |
|---|---|
| comprehension | Solid, nuanced grasp of the concept |
| surface_understanding | Knows terms but lacks depth |
| definitional_gap | Key vocabulary unclear or confused |
| applied_transfer_difficulty | Struggles to apply to new contexts |
| pacing_concern | Reflection suggests pace issues |
| support_need | Needs additional resources or check-in |

## How to run the demo

1. Start the **ReflectIQ** workflow (if not already running)
2. Set `OPENAI_API_KEY` in Replit Secrets and restart the workflow
3. Open the app in the preview pane — the homepage is the student topic picker
4. Go to `/dashboard` and click **Load Dummy Data** to explore the faculty view with sample data
5. Click any topic card to try the 4-step student reflection flow
6. Visit `/completion` to see the completion tracking view (identifiable but content-free)
7. Visit `/governance` to read the full data architecture explanation
8. Visit `/api/test-openai` to confirm the API key is working

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- The SQLite DB is created at first startup inside `reflectiq/data/` — restart the workflow if the file is missing
- `OPENAI_API_KEY` must be set as a Replit secret before starting the workflow
- Port 8000 is used by Flask; the Replit proxy routes the root `/` path to Flask
- The two DB tables (`completion_log`, `anonymous_analysis`) are never joined by design
- `is_demo=1` rows can be removed without affecting real student data via the Clear Demo Data button
