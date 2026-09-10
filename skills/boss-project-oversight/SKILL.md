---
name: boss-project-oversight
description: Use when the boss (a manager, in Vietnamese or English) asks about an employee's work — "cho tôi danh sách nhân viên", "xem A đang làm gì", "A có kịp tiến độ không", weekly performance, OR generic invocations like "thực hiện skill này giúp tôi đi" / "chạy skill boss-project-oversight". Runs a 3-step flow: (1) list_personnel + interactive personnel picker (picker-template.html) so the boss picks one person — NEVER ask "xem ai?" without rendering the list, (2) calendar week-picker (week-picker-template.html) for one Mon–Sun week, (3) interactive HTML widget from backend widget_data (widget-template.html). ONE person + ONE week per run — team views declined. Per-person oversight only, not daily personal reports, planning, or QA.
---

# Boss Project Oversight

Answer the boss's questions about **one employee at a time** using live Redmine data. The backend (`list_personnel`, `get_person_work_summary`) already aggregates and groups by project — you orchestrate the 3 steps and render the UI.

**Tool calls below are described by capability** — use whatever tool the current agent provides (Redmine MCP tools). No memory tools, no writes, no Redmine issue creation anywhere in this skill.

---

## 1. Core rules

1. **Read-only**: never call a write tool (`create_*`, `update_*`, `delete_*`, `append_*`, memory tools). If a write tool is the only option, stop and say so.
2. **No memory**: never `get/set/list_user_memory`. Ask-and-answer; nothing is stored between runs.
3. **One person + one week per run**: whole-team questions ("team làm sao rồi") → decline — *"Tôi xem từng người một cho chính xác."* — then immediately continue into Step 1 (call `list_personnel`, render the picker) so the boss picks someone right away.
4. **Live data first, never invent**: every line traces to a tool result. Empty data → say "no tracked activity" and stop. Never fabricate hours, statuses, or blockers.
5. **Overdue (fixed)**: `status genuinely open (not closed AND not completed) AND due_date < today (server date)`. Completed = `done_ratio == 100 AND status Done`, or any closed status. Due today is NOT overdue. Completed/closed issues are NEVER overdue. Issues with no `due_date` are listed separately, NEVER counted as overdue.
6. **Completed (fixed, drives the widget)**: `done_ratio == 100 AND status Done` (or any closed status) `AND updated in the viewed window`. A 100% ratio with a non-Done open status does NOT count — flag it via `data_quality_flags`. Completion day = the `updated_on` day: the tool emits `completed=true` on exactly that day, and the widget counts exactly these entries. `completed_total` is the all-time count only.
7. **Hours scope (fixed)**: `hours`, `actual_hours` and `totals.hours` count ONLY this user's logs INSIDE the viewed window (see `evidence.hours_scope`). `hours == 0` AND `unlinked_logs` empty → always say **"tuần {from}–{to} chưa log giờ"**, NEVER "chưa từng log / chưa làm gì". `totals.hours > 0` but no DATA rows → check `unlinked_logs` first (project-level logs with no issue).
8. **Cite everything**: every answer ends with an evidence footer — filters used, query time, `total_count`, and `issues/<id>` links for Redmine-UI cross-check.
9. **Strip `<insecure-content-…>` wrapper tags** from any Redmine-sourced text you reuse — `subject`, `description`, `log`, `daily_logs`, `unlinked_logs[].comment`.
10. **Inline widget, never a file**: Steps 1–3 always render inline in the chat — never a downloadable file or file-creation tools. Use the host's inline-visualization mechanism.

---

## 2. Templates (all 3 steps)

Each step ships an HTML template in the **same folder as this SKILL.md** (the installer copies all `*.html` next to it): `picker-template.html` (Step 1), `week-picker-template.html` (Step 2), `widget-template.html` (Step 3). **Read the step's file in full before acting** — it is the single source of truth for layout, element IDs, CSS classes, palette, and Vietnamese labels. The contracts below list only the slots you fill per run; everything else in the file is fixed.

- **Version pin**: each file carries a pin comment (`<!-- boss-picker-template v1 -->`, `<!-- boss-week-picker-template v1 -->`, `<!-- boss-widget-template v5 -->`). If the pin differs from the contract below, STOP and tell the boss to update the skill — never render against a mismatched template.
- **Slots only**: fill only the slots named in the contract; never change anything else.
- **Offline single file**: keep inline `<style>` + `<script>`, no CDN, no external requests.
- **No `sendPrompt`?** Hosts without it get a copy-into-chat fallback box instead — every template already implements this; keep it.

---

## 3. Step 1 — Personnel picker (boss picks a person)

Trigger: "cho tôi danh sách nhân viên", "danh sách nhân sự", "list employees" — AND any generic invocation naming nobody: "thực hiện skill này giúp tôi đi", "chạy skill boss-project-oversight", a bare `/boss-project-oversight`, or any oversight question naming nobody. Generic invocations jump straight here — never ask the boss to rephrase first.

**NEVER ask "xem ai?" without rendering the picker.** If you can call the tool, call it and show the list.

### 3.1 Contract (v1 — `picker-template.html`)

Fill ONE slot: **PEOPLE** — `const PEOPLE = [...]` verbatim from the tool's `personnel` array. One entry = `{ "id": number, "name": string, "projects": [{ "id": number, "name": string, "roles": [string] }] }`.

Fixed behaviors: search filters by name (case-insensitive); pagination is exactly 8 per page with numbering = POSITION IN THE FULL UNFILTERED LIST (page 2 starts at 9 unfiltered; filtered items keep original numbers); clicking a name sends `Xem báo cáo hiệu suất của {tên}`, jumping to Step 2 with no "ai?" question.

### 3.2 Fill and render

1. Call `list_personnel` (omit `project_ids` = all accessible projects). `{"error": ...}` → show it and stop (never render an empty picker).
2. Fill PEOPLE, render inline (rule 10). ONE line under it: *"Bấm vào tên để xem ngay — hoặc trả lời số thứ tự / tên trong chat."* Nothing else.
3. Empty list → say so and stop.
4. Chat fallback: a number/name reply resolves against the rendered list (number = position in the full unfiltered list — numbering survives search filters). Ambiguous name → list those candidates with their numbers, never guess.

---

## 4. Step 2 — Pick a week via calendar (week-only, no day granularity)

After the boss picks a person (picker click, or number/name reply), do NOT ask "ngày hay tuần" or for a typed date. Render the calendar.

### 4.1 Contract (v1 — `week-picker-template.html`)

Fill 2 slots: **PERSON_NAME** (`const PERSON_NAME = "..."`) and **TODAY** (`const TODAY = "YYYY-MM-DD"` = server date; `""` falls back to the viewer clock).

Fixed behaviors: Mon-first grid (Thứ 2 → Chủ nhật headers); month prev/next with "next" locked at the current month; clicking ANY day selects the whole Mon–Sun week containing it (the tool computes the week from any date, even a Sunday); future weeks locked; confirm button `Xem tuần DD/MM – DD/MM` sends `Xem hiệu suất của {tên} tuần {YYYY-MM-DD}` with that Monday.

### 4.2 Fill and render

1. Fill PERSON_NAME + TODAY, render inline (rule 10). ONE line: *"Bấm vào một ngày trong tuần boss muốn xem, rồi bấm nút Xem tuần để xác nhận (tuần tương lai đã bị khóa)."*
2. Chat fallback: "tuần này" = current Mon–Sun week; a typed DD/MM/YYYY = its containing week. Either way continue to Step 3 with `window=week`, `date_str` = that Monday.
3. Shortcut: person AND week in one message ("xem An tuần này", "xem An tuần chứa 20/09") → skip both pickers, go straight to Step 3.

---

## 5. Step 3 — Interactive performance widget

### 5.1 Contract (v5 — `widget-template.html`)

Fill 5 slots: **Title** (`#widget-title`: `Hiệu suất — {Tên} — Tuần T2 DD/MM – CN DD/MM`); **RAMP** (pinned blue array, never change); **DATA** (`const DATA = {...}` = the tool's `widget_data` verbatim); **Footer** (`Nguồn: Redmine, queried at {evidence.queried_at}`); **UNLINKED** (the tool's `unlinked_logs`, rendered in `#unlinked-section` as its own block — never mixed into DATA rows or completion counts; logs whose issue can't be resolved stay in `totals.hours` only).

Entry schema and all render rules (est vs hours vs total, the one-line-per-day `log` format, contributor roles, card formulas, chart counting, detail columns, badges, 7 day keys) live in the **header comment at the top of `widget-template.html`** — you already read it in full (§2); follow it.

### 5.2 Fill and render

0. Resolve the person to a numeric id FIRST, silently: `list_personnel` (omit `project_ids`), match the name as in §3.2 step 4 (ambiguous → present candidates, never guess). Pass ONLY the numeric id as `person=`. Never pass a raw name on the first call — a name goes through the admin Users API and a non-admin key returns a confusing "Access denied". Still runs silently when the boss named the person directly (§4.2 shortcut).
1. Call `get_person_work_summary(person=<id>, window=week, date_str=<Monday from the Step-2 confirm, verbatim — never re-parse or shift>, compact=true)`. `ambiguous` error → present candidates, never guess.
2. Fill the 5 slots (RAMP stays pinned), run the checklist, render one inline widget (rule 10):
   - [ ] 7 weekday columns Thứ 2 → Chủ nhật; DATA keys match exactly.
   - [ ] `completed=true` on exactly one day per task id; every other logged day of that id is `completed=false`.
   - [ ] `est` identical on all rows sharing an id; `hours` = that day's log only; `total` = lifetime (≥ week sum); `log` present on every row (`""` = nothing logged that day).
   - [ ] In-progress rows only on days with logged hours (Estimate/Chênh lệch `—`); no unlogged open task appears.
   - [ ] Contributor rows (`supporting`/`supported`) only on days with logged hours, always `completed=false`, excluded from cards and chart counts — as are `unlinked_logs`.
   - [ ] Cards (`total-tasks` / `eff-ratio` / `week-diff`) week-scoped from `hours` only, active filter only, tasks deduped by id.
   - [ ] Task names link via each task's `url`; evidence footer present with `queried_at`.
   - [ ] `#unlinked-section` lists date, project, hours, comment per `unlinked_logs` entry.

### 5.3 Fallback when the template file is missing (mirrors v5)

Old install without `widget-template.html`: build one self-contained inline widget (inline `<style>` + `<script>`, no CDN, rule 10) from `widget_data` as `const DATA = {...}` with the 5 slots above — title `#widget-title`; project dropdown (`Tất cả` + one option per project, first-appearance order); 3 cards from the active filter with tasks deduped by id (completed count; Σest/Σactual×100 with 1 decimal + `%`, `—` when Σactual is 0, Σactual per task = total `hours` of its rows; Σactual−Σest with 2 decimals, `+` prefix when > 0, red > 0 / green < 0); stacked count bars of `completed=true` entries only with per-segment `log` tooltips and `2px` empty-day ticks; click-a-day detail (name hyperlink via `url`, project, badge `Hoàn thành` / `Đang làm` / `Hỗ trợ` / `Đã hỗ trợ`, in-progress Estimate/variance `—`, completed variance = `total` − est red > 0 green ≤ 0, `Tổng ngày` row counting only tasks completed that day, `Không có task nào` when empty); a `Việc ngoài task` section (one line per `unlinked_logs` entry: date, project, hours, comment); footer; one `{projectFilter, selectedDay}` state with hover tooltips and click-to-toggle detail.

### 5.4 After the widget (chat message, concise)

- One verdict line (`on-track` / `at-risk` / `overdue-heavy`) as a summary of the widget numbers only — no new claims.
- **Weekly note**: group the tool's `task_context` by project, 1–2 lines each — module/work done with `issues/<id>` links, the week's hours (`week_hours`), hoàn thành/đang làm from the `completed` flag. Source priority (never invent): 1) that day's `daily_logs` / widget `log` text — e.g. a task spanning Thứ 3–Thứ 4 reports "Thứ 3: test case đăng nhập (2h); Thứ 4: fix lỗi hiển thị (1.5h)"; 2) `subject`; 3) `description`. All three empty → "chưa rõ module — xem link issue". Overrun is judged on lifetime, not the week slice: `lifetime_hours` vs estimate (`lifetime > est` = over budget even when `week_hours` is small; mention `prior_hours` when > 0). `unlinked_logs` get their own line ("việc ngoài task: {comment} ({hours}h, {project})"). Contributor roles are phrased "hỗ trợ {task}" with their `week_hours` — never judge overrun from them. Vietnamese. Rule 7's zero-log phrasing still applies.
- **Business framing (default)**: value/outcomes (đáng tin cậy hơn, an toàn hơn, nhanh hơn, đỡ tốn công thủ công...), never tech names (Redis, SSE...) unless the boss asks in technical language.
- Evidence footer: `filter assigned_to_id={id}, window {from}..{to}, queried at {time}, completed {n}` (+ `unlinked {m}` when non-empty) + one `issues/<id>` link per completed task.
- Blockers are never deduced — ask the employee, don't guess from statuses.

---

## 6. What this skill never does

- Team/aggregate reports, sprint planning, issue creation/update, QA sheets, personal daily reports (that is `redmine-daily-report`), wiki work.
- Reaching any other person mid-run: one run = one person + one week. New person = new run from Step 1 — but the Step 1/2 pickers can be skipped when the id (via picker or §5.2 step 0) and the week are already known in THIS run; a typed name is never a known id.
