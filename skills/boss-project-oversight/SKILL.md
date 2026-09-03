---
name: boss-project-oversight
description: Use when the boss (a manager, in Vietnamese or English) asks about an employee's work — "cho tôi danh sách nhân viên", "xem A đang làm gì", "A có task nào trễ không", "A có kịp tiến độ không", performance by day/week. Runs a 3-step flow: (1) list personnel so the boss picks one person, (2) ask day or week, (3) render an interactive HTML widget (project dropdown, 2 metric cards, stacked bar chart Mon–Sun, click-a-day detail table) from the backend widget_data. ONE person per run — team/aggregate views are declined. Use ONLY for per-person oversight, not for daily personal reports, planning, or QA work.
---

# Boss Project Oversight

Answer the boss's questions about **one employee at a time** using live Redmine data. The backend (`list_personnel`, `get_person_work_summary`) already aggregates and groups by project — you orchestrate the 3 steps and render the UI.

**Tool calls below are described by capability** — use whatever tool the current agent provides (Redmine MCP tools). No memory tools, no writes, no Redmine issue creation anywhere in this skill.

---

## 1. Core rules

1. **Read-only**: never call a write tool (`create_*`, `update_*`, `delete_*`, `append_*`, memory tools). If a write tool is the only option, stop and say so.
2. **No memory**: never `get/set/list_user_memory`. Boss wants ask-and-answer; nothing is stored between runs.
3. **One person per run**: if the boss asks about the whole team ("team làm sao rồi"), decline — *"Tôi xem từng người một cho chính xác — boss muốn xem ai trước?"* — then run the flow for that person.
4. **Live data first, never invent**: every line traces to a tool result. Empty data → say "no tracked activity" and stop. Never fabricate hours, statuses, or blockers.
5. **Overdue definition (fixed)**: `status is open (not closed) AND due_date < today (server date)`. Due today is NOT overdue. Closed issues are NEVER overdue. Issues with no `due_date` are listed separately and NEVER counted as overdue.
6. **Completed definition (fixed, drives the widget)**: `done_ratio == 100 AND updated in the viewed window` — even when the status is still open. The tool computes this as `completed`/`widget_data`; the widget counts exactly these tasks.
6. **Cite everything (evidence rule)**: every answer ends with an evidence footer — the filters used, the query time, `total_count` from the tool, and `issues/<id>` links that open in the Redmine UI for manual cross-check.
7. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names you reuse.

---

## 2. Step 1 — Personnel list (boss picks a person)

Trigger: "cho tôi danh sách nhân viên", "danh sách nhân sự", "list employees".

1. Call `list_personnel` (omit `project_ids` = all accessible projects).
2. Render a numbered picker, one line per person with their projects:
   ```markdown
   **Nhân sự (N người — <project scope>):**
   1. An Nguyen — Web (Developer), App (Manager)
   2. Binh Tran — Web (Developer)
   ...
   Boss muốn xem ai? (trả lời số hoặc tên)
   ```
3. If the list is empty → say so and stop.

---

## 3. Step 2 — Ask day or week (verbatim question)

After the boss picks a person (by number or name), ask before calling anything:

> Xem hiệu suất của **{Tên}** theo **ngày** hay **tuần**? Ngày nào (mặc định hôm nay)?

- Day = one calendar date. Week = Monday–Sunday containing that date (the tool computes it — even when the date is a Sunday).
- Accept "hôm nay" / "tuần này" without further questions.

---

## 4. Step 3 — Interactive performance widget (template-first)

### 4.0 Read the template BEFORE calling any tool

The skill ships with a reference template, `widget-template.html`, in the **same folder as this SKILL.md** (the installer copies it next to `SKILL.md` — boss skill only). **Read that file first, in full, before calling `get_person_work_summary`.** It is the single source of truth for layout, element IDs, CSS classes, palette, and Vietnamese labels. The spec in §4a–4b below is only the fallback for when the file is missing.

### 4.1 Template contract (TEMPLATE CONTRACT — PENDING: fill in from widget-template.html once the file lands)

> The template file has not been provided yet. When it lands, replace this
> block with its real contract: version pin comment, DATA slot marker,
> title slot marker, footer/query-time slot marker, chart/table element IDs,
> fixed palette, and the exact pre-emit checklist tied to those names.
> Until then, every run uses the §4.3 fallback below.

Rules that already apply to whatever the template contains:

1. **Slots only**: replace only the marked slot contents (data, title, footer/query time). Never restructure layout, rename element IDs/classes, change the palette, relabel days, or reorder columns.
2. **Data verbatim**: embed the tool's `widget_data` exactly as returned (day keys stay Monday-first). Never invent, summarize, or fabricate tasks, hours, or colors.
3. **Version pin**: the template header carries `<!-- boss-widget-template vN -->`. If `N` differs from the version named in this contract, STOP and tell the boss to update the skill — never render against a mismatched template.
4. **Offline single file**: the emitted artifact keeps the template's inline `<style>` + `<script>`; no CDN, no external requests.

### 4.2 Fill and emit

1. Call `get_person_work_summary(person=<id from step 1>, window=<day|week>, date_str=<date>, compact=true)`. `ambiguous` error → present candidates, never guess.
2. Fill the template slots with the live result (`widget_data` → DATA slot, person + window → title slot, `evidence.queried_at` → footer slot).
3. Run the pre-emit checklist from the contract (shape of it: 7 weekday columns in order; dropdown options equal the projects present in DATA; variance red when actual − est > 0 else green; links use each task's `url`; evidence footer present), then emit **one HTML artifact**.

### 4.3 Fallback when the template file is missing (compact spec)

If `widget-template.html` is absent (old install), build one self-contained HTML artifact (inline `<style>` + `<script>`, no CDN) from `widget_data` embedded verbatim as `const DATA = {...}`:

1. **Title**: `Hiệu suất — {Tên} — {Ngày DD/MM | Tuần T2 DD/MM – CN DD/MM}`.
2. **Project dropdown** (top): `Tất cả` + one option per project in DATA (first-appearance order). Default `Tất cả`.
3. **Two metric cards** from the active filter: completed-task count; Σest/Σactual × 100 with one decimal + `%` (`—` when Σactual is 0).
4. **Stacked bar chart** Thứ 2 → Chủ nhật: per-project stacked counts (`Tất cả`) or single-project data; legend with name + color swatch.
5. **Detail table** on bar click (day AND active project filter): Tên task (hyperlink via `url`), Project, estimate, actual, variance = actual − est (2 decimals, red > 0, green ≤ 0). Empty day → `Không có task hoàn thành`.
6. **Footer**: `Nguồn: Redmine, queried at {evidence.queried_at}`.
7. Behavior: one state `{projectFilter, selectedDay}`, one `render()` on every change, toggle-select on bars. Palette: `#2563eb, #16a34a, #dc2626, #d97706, #7c3aed, #0891b2, #db2777, #65a30d` (wrap past 8).

### 4c. After the artifact (chat message, concise)

- One verdict line per person (`on-track` / `at-risk` / `overdue-heavy`) ONLY as a summary of the widget numbers — no new claims.
- Evidence footer: `filter assigned_to_id={id}, window {from}..{to}, queried at {time}, completed {n}` + one `issues/<id>` link per completed task for Redmine-UI cross-check.
- Blockers are never deduced. If the boss asks about blockers, ask the employee — do not guess from statuses.

---

## 5. What this skill never does

- Team/aggregate reports, sprint planning, issue creation/update, QA sheets, personal daily reports (that is `redmine-daily-report`), wiki work.
- Reaching any other person mid-run: one run = one person. A new person = a new run from Step 1 (the id is already known, so Step 1 can be skipped when the boss names them directly).
