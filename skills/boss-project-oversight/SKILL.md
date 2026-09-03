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

## 4. Step 3 — Interactive performance widget (single HTML artifact)

Call `get_person_work_summary(person=<id from step 1>, window=<day|week>, date_str=<date>, compact=true)`. If the tool returns an `ambiguous` error, present the candidates and let the boss pick — never guess.

Then build **one self-contained interactive HTML artifact** (inline `<style>` + `<script>`, **no CDN, no external requests** — it must work offline) from the tool's `widget_data`, embedded verbatim as `const DATA = {...}`:

```json
{
  "Thứ 2": [{"id": 1, "name": "Task A", "project": "Web",
              "est": 3, "actual": 2.5, "url": "https://.../issues/1"}],
  "Thứ 3": [], "Thứ 4": [], "Thứ 5": [],
  "Thứ 6": [], "Thứ 7": [], "Chủ nhật": []
}
```

Never invent, reorder, or summarize this data — embed it exactly as returned (day keys stay Monday-first). `est` = estimate hours (0 when Redmine has none), `actual` = hours logged on that task inside the window (0 when none logged).

### 4a. Layout (top to bottom)

1. **Title**: `Hiệu suất — {Tên} — {Ngày DD/MM | Tuần T2 DD/MM – CN DD/MM}`.
2. **Project dropdown** (top): `Tất cả` + one option per project found in DATA (order of first appearance). Default: `Tất cả`.
3. **Two metric cards** (recomputed from the active filter):
   - Tổng task hoàn thành = number of tasks matching the filter.
   - Tỷ lệ hiệu suất = Σest / Σactual × 100, one decimal + `%`; when Σactual is 0 show `—`.
4. **Stacked bar chart** (Thứ 2 → Chủ nhật, fixed order): each column stacks completed-task counts per project; `Tất cả` shows all projects stacked, one project shows only its segment. Column height scales to the tallest column. Below/above: a **legend** of project name + color swatch.
5. **Detail table** (hidden until a column is clicked): rows = tasks of the clicked day AND the active project filter. Columns: Tên task (hyperlink via `url`), Project, Giờ estimate, Giờ thực tế, Chênh lệch = actual − est with 2 decimals — **red when > 0 (over estimate), green when ≤ 0**. Empty day → one row: `Không có task hoàn thành`.
6. **Footer inside the widget**: `Nguồn: Redmine, queried at {evidence.queried_at}`.

### 4b. Behavior (all client-side, no re-fetch)

- One state `{projectFilter: 'all' | name, selectedDay: string | null}` and one `render()` that recomputes cards, chart, and table on every change (dropdown change, bar click).
- Clicking a bar selects that day (visual highlight) and renders its table; clicking the selected bar again deselects it.
- Fixed palette by project index (same project = same color everywhere): `#2563eb, #16a34a, #dc2626, #d97706, #7c3aed, #0891b2, #db2777, #65a30d` (wrap around if more than 8 projects).
- Numbers: hours with up to 2 decimals, counts as integers, Vietnamese day labels verbatim.

### 4c. After the artifact (chat message, concise)

- One verdict line per person (`on-track` / `at-risk` / `overdue-heavy`) ONLY as a summary of the widget numbers — no new claims.
- Evidence footer: `filter assigned_to_id={id}, window {from}..{to}, queried at {time}, completed {n}` + one `issues/<id>` link per completed task for Redmine-UI cross-check.
- Blockers are never deduced. If the boss asks about blockers, ask the employee — do not guess from statuses.

---

## 5. What this skill never does

- Team/aggregate reports, sprint planning, issue creation/update, QA sheets, personal daily reports (that is `redmine-daily-report`), wiki work.
- Reaching any other person mid-run: one run = one person. A new person = a new run from Step 1 (the id is already known, so Step 1 can be skipped when the boss names them directly).
