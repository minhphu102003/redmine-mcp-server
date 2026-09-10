---
name: boss-project-oversight
description: Use when the boss (a manager, in Vietnamese or English) asks about an employee's work — "cho tôi danh sách nhân viên", "xem A đang làm gì", "A có kịp tiến độ không", weekly performance, OR any generic skill invocation like "thực hiện skill này giúp tôi đi" / "chạy skill boss-project-oversight" / "dùng skill này". Runs a 3-step flow: (1) call list_personnel and render the interactive personnel picker (search + paginated, from picker-template.html) so the boss picks one person — NEVER ask "xem ai?" without rendering the list, (2) render a calendar week-picker (from week-picker-template.html) so the boss picks one Mon–Sun week — week-only, no day granularity, (3) render an interactive HTML widget (project dropdown, 3 metric cards, stacked bar chart Mon–Sun, click-a-day detail table) from the backend widget_data. ONE person and ONE week per run — team/aggregate views are declined. Use ONLY for per-person oversight, not for daily personal reports, planning, or QA work.
---

# Boss Project Oversight

Answer the boss's questions about **one employee at a time** using live Redmine data. The backend (`list_personnel`, `get_person_work_summary`) already aggregates and groups by project — you orchestrate the 3 steps and render the UI.

**Tool calls below are described by capability** — use whatever tool the current agent provides (Redmine MCP tools). No memory tools, no writes, no Redmine issue creation anywhere in this skill.

---

## 1. Core rules

1. **Read-only**: never call a write tool (`create_*`, `update_*`, `delete_*`, `append_*`, memory tools). If a write tool is the only option, stop and say so.
2. **No memory**: never `get/set/list_user_memory`. Boss wants ask-and-answer; nothing is stored between runs.
3. **One person + one week per run**: if the boss asks about the whole team ("team làm sao rồi"), decline — *"Tôi xem từng người một cho chính xác."* — then immediately continue into Step 1 below (call `list_personnel`, render the picker) so the boss can pick someone right away instead of answering another question.
4. **Live data first, never invent**: every line traces to a tool result. Empty data → say "no tracked activity" and stop. Never fabricate hours, statuses, or blockers.
5. **Overdue definition (fixed)**: `status is genuinely open (not closed AND not completed) AND due_date < today (server date)`. Completed = `done_ratio == 100 AND status is Done`, or any closed status. Due today is NOT overdue. Completed/closed issues are NEVER overdue. Issues with no `due_date` are listed separately and NEVER counted as overdue.
6. **Completed definition (fixed, drives the widget)**: `done_ratio == 100 AND status is Done` (or any closed status) `AND updated in the viewed window`. A 100% ratio with a non-Done open status does NOT count — flag it via `data_quality_flags` instead. The completion day is the `updated_on` day: the tool emits `completed=true` on exactly that day. The widget counts exactly these entries. `completed_total` is the all-time count (count only, no list).
6b. **Hours scope (fixed interpretation)**: `hours`, `actual_hours` and `totals.hours` count ONLY time logged by this exact user INSIDE the viewed window (see `evidence.hours_scope`). `hours == 0` → always say **"tuần {from}–{to} chưa log giờ"**, NEVER "chưa từng log / chưa làm gì". Quote `evidence.hours_scope.note` as the basis when asked.
7. **Cite everything (evidence rule)**: every answer ends with an evidence footer — the filters used, the query time, `total_count` from the tool, and `issues/<id>` links that open in the Redmine UI for manual cross-check.
8. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names you reuse.
9. **Inline widget, never a file**: Step 1/2/3 output always renders inline in the chat as an interactive widget — never a downloadable file, never via file-creation/present-file tools. Use the host's inline-visualization/widget mechanism (some hosts call that mechanism "artifact" too — fine, as long as it renders inline in the chat, not as a file).

---

## 2. Step 1 — Personnel picker (boss picks a person)

Trigger: "cho tôi danh sách nhân viên", "danh sách nhân sự", "list employees" — AND any generic invocation with no person named: "thực hiện skill này giúp tôi đi", "chạy skill boss-project-oversight", "dùng skill này", a bare `/boss-project-oversight`, or any oversight question that names nobody. Generic invocations jump straight here — never ask the boss to rephrase or to say "danh sách nhân viên" first.

**NEVER ask "xem ai?" / "muốn xem hiệu suất của ai?" without rendering the picker.** The failure mode to avoid: the agent already has (or can fetch) the personnel data and still asks a bare question with no names. If you can call the tool, call it and show the list.

### 2.0 Read the template BEFORE calling any tool

The skill ships with a personnel picker template, `picker-template.html`, in the **same folder as this SKILL.md**. **Read that file first, in full, before calling `list_personnel`.** It is the single source of truth for the picker layout, element IDs, CSS classes, and Vietnamese labels.

### 2.1 Template contract (v1 — `picker-template.html` in this folder)

Version pin: `<!-- boss-picker-template v1 -->` at the top of the file.
If the pin differs, STOP and tell the boss to update the skill — never render
against a mismatched template.

The template is fixed-layout with host-theme fallback (`#rpt-root` maps
`--surface-1/2`, `--border`, `--text-primary/secondary/muted/accent` to
`--rpt-*` with light fallbacks). **Only ONE slot may change per run:**

1. **PEOPLE** — `const PEOPLE = [...]` filled verbatim from the tool's
   `personnel` array. One entry = `{ "id": number, "name": string,
   "projects": [{ "id": number, "name": string, "roles": [string] }] }`.

Fixed behaviors (never change): search box filters by name (case-insensitive);
pagination is exactly 8 people per page with numbering = POSITION IN THE FULL
UNFILTERED LIST (page 2 starts at 9 when unfiltered; filtered items keep their
original numbers) so a chat reply with a number always matches; clicking a
name calls `sendPrompt('Xem báo cáo hiệu suất của {tên}')` which jumps straight
to Step 2 with no further "ai?" question; hosts without `sendPrompt` show a
copy-into-chat fallback box instead. Offline single file: keep inline
`<style>` + `<script>`, no CDN, no external requests.

### 2.2 Fill and render

1. Call `list_personnel` (omit `project_ids` = all accessible projects).
   Tool returns `{"error": ...}` → show the error to the boss and stop (never render an empty picker).
2. Fill the PEOPLE slot verbatim, then render the filled template inline in the chat (rule 9 — widget, not a file).
3. Add ONE chat line under the widget: *"Bấm vào tên để xem ngay — hoặc trả lời số thứ tự / tên trong chat."* Nothing else — no bare "xem ai?" question.
4. If the list is empty → say so and stop.
5. Chat fallback: if the boss replies with a number or a name instead of clicking, resolve it against the rendered list (number = position in the full unfiltered list — numbering survives search filters). A name matching multiple people → list those candidates with their numbers and let the boss pick a number, never guess.

---

## 3. Step 2 — Pick a week via calendar (week-only, no day granularity)

After the boss picks a person (picker click → `sendPrompt('Xem báo cáo hiệu suất của {tên}')` — or a number/name reply in chat), do NOT ask "ngày hay tuần" and do NOT ask for a date in text. Render a calendar and let the boss pick the week visually.

### 3.0 Read the template BEFORE rendering

The skill ships with a week picker template, `week-picker-template.html`, in the **same folder as this SKILL.md**. **Read that file first, in full, before rendering the calendar.**

### 3.1 Template contract (v1 — `week-picker-template.html` in this folder)

Version pin: `<!-- boss-week-picker-template v1 -->` at the top of the file.
If the pin differs, STOP and tell the boss to update the skill — never render
against a mismatched template.

Fixed-layout with the same `#rpt-root` host-theme fallback as the other templates. **Only 2 slots may change per run:**

1. **PERSON_NAME** — `const PERSON_NAME = "..."` = the Step-1 person name.
2. **TODAY** — `const TODAY = "YYYY-MM-DD"` = server date (locks future weeks deterministically; `""` falls back to the viewer clock).

Fixed behaviors (never change): Mon-first grid (Thứ 2 → Chủ nhật headers),
month prev/next navigation with "next" locked at the current month; clicking
ANY day selects the whole Mon–Sun week containing it and highlights the full
row (the tool computes the week from any date, even a Sunday); future weeks
are locked (dimmed + unclickable); a confirm button
`Xem tuần DD/MM – DD/MM` appears after selection and calls
`sendPrompt('Xem hiệu suất của {tên} tuần {YYYY-MM-DD}')` with the Monday of
the picked week; hosts without `sendPrompt` show a copy-into-chat fallback
box instead. Offline single file: keep inline `<style>` + `<script>`, no CDN.

### 3.2 Fill and render

1. Fill PERSON_NAME + TODAY, then render the filled template inline in the chat (rule 9 — widget, not a file).
2. Add ONE chat line: *"Bấm vào một ngày trong tuần boss muốn xem, rồi bấm nút Xem tuần để xác nhận (tuần tương lai đã bị khóa)."*
3. Chat fallback: "tuần này" = current Mon–Sun week; a typed date (DD/MM/YYYY) = the week containing it. Either way, continue to Step 3 with `window=week` and `date_str` = the Monday of that week (YYYY-MM-DD).
4. Shortcut: if the boss already named a person AND a week ("xem An tuần này", "xem An tuần chứa 20/09") in one message, skip both pickers and go straight to Step 3.

---

## 4. Step 3 — Interactive performance widget (template-first)

### 4.0 Read the template BEFORE calling any tool

The skill ships with three templates in the **same folder as this SKILL.md** (the installer copies all `*.html` next to `SKILL.md` — boss skill only): `picker-template.html` (Step 1), `week-picker-template.html` (Step 2), and the reference widget template below (Step 3). **Read `widget-template.html` first, in full, before calling `get_person_work_summary`.** It is the single source of truth for layout, element IDs, CSS classes, palette, and Vietnamese labels. The spec in §4.1–4.3 below mirrors that file and is only the fallback for when the file is missing.

### 4.1 Template contract (v4 — `widget-template.html` in this folder)

Version pin: `<!-- boss-widget-template v4 -->` at the top of the file.
If the pin differs, STOP and tell the boss to update the skill — never render
against a mismatched template.

The template is fixed-layout with host-theme fallback (`#rpt-root` maps
`--surface-1/2`, `--border`, `--text-primary/secondary/muted/accent/danger/success`
to `--rpt-*` with light fallbacks, so it renders standalone and inside the
Visualizer). **Only these 4 slots may change per run:**

1. **Title** — `#widget-title`: `Hiệu suất — {Tên} — Tuần T2 DD/MM – CN DD/MM` (week-only since Step 2; no day titles).
2. **RAMP** — `const RAMP = ["#85B7EB", "#378ADD", "#185FA5", "#042C53", "#B5D4F4"]`
   (single blue tone, stops spaced apart — never switch color families).
   `projectColors` assigns in first-appearance order, wraps with `% RAMP.length`.
3. **DATA** — `const DATA = {...}` embedded verbatim from the tool's
   `widget_data`. One row = one time log on one day for one task; the same
   task id repeats across days, `completed=true` on exactly one day.
   Schema per entry:
    `{ "id": number, "name": string, "project": string, "est": number, "hours": number, "total": number, "url": string, "completed": boolean, "role": "owner" | "supporting" | "supported" }`
    where `est` = estimate of the WHOLE task (same value on every row with
    that id), `hours` = hours logged on THAT day only (not the task total),
    and `total` = hours logged on that task in ALL weeks by this user
    (lifetime, for the overrun column — NOT the week sum).
    `role` = `owner` (assigned to this person) or a contributor role:
    `supporting` (someone else's open task this person logged hours on)
    or `supported` (someone else's closed task they contributed to).
    Contributor rows always carry `completed=false`, so chart columns and
    the 3 cards (which count only `completed=true`) exclude them.
   7 day keys in fixed order, always covering the Mon–Sun week being viewed:
   `"Thứ 2","Thứ 3","Thứ 4","Thứ 5","Thứ 6","Thứ 7","Chủ nhật"`.
4. **Footer** — `Nguồn: Redmine, queried at {evidence.queried_at}`.

Fixed element IDs (never rename): `rpt-root`, `widget-title`,
`project-filter`, `total-tasks`, `eff-ratio`, `week-diff`, `bar-chart`,
`tooltip`, `day-labels`, `legend`, `detail-panel`, `detail-day`, `detail-table`.
Fixed behaviors: dropdown `Tất cả` + one option per project (first-appearance
order); 3 metric cards (`total-tasks` = completed-task count deduped by id,
`eff-ratio` = Σest/Σactual×100 with 1 decimal + `%` or `—` when Σactual is 0,
`week-diff` = Σactual−Σest with 2 decimals and `+` prefix when > 0,
red when > 0 / green when < 0); stacked count bars Thứ 2 → Chủ nhật counting
ONLY `completed=true` entries (never double-count multi-day tasks), with
per-segment hover tooltip and empty-day `2px` tick; click-a-column
`showDetail(day, projectFilter)` showing in-progress rows too (badge
`Đang làm` vs `Hoàn thành` vs `Hỗ trợ` (role=supporting) vs `Đã hỗ trợ`
(role=supported), hyperlink via `url`, `hours` = that day's log,
`Tổng đã log` = lifetime `total`, Estimate/Chênh lệch = `—` for
in-progress rows, Chênh lệch for completed rows = `total` − est,
2 decimals, red > 0 else green) plus a `Tổng ngày` row (variance counts
only tasks completed that day); `Không có task nào` when a day is empty.
Offline single file: keep inline `<style>` + `<script>`, no CDN, no
external requests. Cards (`total-tasks` / `eff-ratio` / `week-diff`) stay
week-scoped from `hours` only — never from `total`.

### 4.2 Fill and render

0. Resolve the person to a numeric id FIRST, silently: call `list_personnel` (omit `project_ids`) and match the Step-1/Step-2 person name against the returned `personnel` array (same matching as §2.2 step 5 — number = position in the full unfiltered list; multiple matches → present candidates, never guess). Pass ONLY the numeric id as `person=` in step 1 below. NEVER pass a raw name string to `get_person_work_summary` on the first call of a run — a name goes through the admin Users API, and a non-admin key returns a confusing "Access denied" instead of a clean result or an "ambiguous" message. This step runs silently (no picker render) when the boss already named the person directly (§3.2 shortcut) — it still runs.
1. Call `get_person_work_summary(person=<numeric id from step 0>, window=week, date_str=<Monday YYYY-MM-DD from the Step-2 confirm message, passed verbatim>, compact=true)`. That `tuần YYYY-MM-DD` string IS the Monday — never re-parse or shift it. `ambiguous` error → present candidates, never guess.
2. Fill the 4 template slots with the live result (`widget_data` → DATA slot verbatim, person + window → title slot, `evidence.queried_at` → footer slot, RAMP stays as pinned).
3. Run the pre-render checklist, then render one inline HTML widget in the chat (rule 9 — widget, not a file):
   - [ ] 7 weekday columns in order Thứ 2 → Chủ nhật, DATA keys match exactly.
   - [ ] `completed=true` on exactly one day per task id; every other logged day of that id is `completed=false`.
   - [ ] `est` identical on all rows sharing an id; `hours` = that day's log only; `total` = lifetime hours (≥ week sum).
    - [ ] In-progress rows present exactly on days with logged hours (badge `Đang làm`, Estimate/Chênh lệch `—`); no unlogged open task appears.
    - [ ] Contributor rows (`supporting`/`supported`) present exactly on days with logged hours on unassigned tasks, badge Hỗ trợ/Đã hỗ trợ, `completed=false`.
    - [ ] Completion counts (`total-tasks` card, chart columns) exclude contributor rows.
   - [ ] `#project-filter` options = `Tất cả` + projects present in DATA (first-appearance order).
   - [ ] `total-tasks` / `eff-ratio` / `week-diff` computed from the active filter only, tasks deduped by id.
   - [ ] Chênh lệch (detail rows + `Tổng ngày`) red when `total` − est > 0, green when < 0; `total-tasks` / `eff-ratio` / `week-diff` stay week-scoped from `hours`.
   - [ ] Task names link via each task's `url`; evidence footer present with `queried_at`.
   - [ ] Known gap (say it if asked): project-level logs with no issue, or issues the tool could not resolve, stay in `totals.hours` but have no DATA row — cross-check via `totals.time_entries`.

### 4.3 Fallback when the template file is missing (mirrors v4)

If `widget-template.html` is absent (old install), build one self-contained inline HTML widget (inline `<style>` + `<script>`, no CDN, rule 9 — widget, not a file) from `widget_data` embedded verbatim as `const DATA = {...}`:

1. **Title** (`#widget-title`): `Hiệu suất — {Tên} — Tuần T2 DD/MM – CN DD/MM`.
2. **Project dropdown** (`#project-filter`, top): `Tất cả` + one option per project in DATA (first-appearance order). Default `Tất cả`.
3. **Three metric cards** from the active filter, tasks deduped by id: completed-task count (`#total-tasks`); Σest/Σactual × 100 with one decimal + `%` (`—` when Σactual is 0) (`#eff-ratio`), where Σactual per task = total `hours` of all rows with that id; week diff Σactual−Σest with 2 decimals, `+` prefix when > 0, red > 0 / green < 0 (`#week-diff`).
4. **Stacked bar chart** (`#bar-chart` + `#day-labels` + `#tooltip` + `#legend`) Thứ 2 → Chủ nhật: per-project stacked counts of `completed=true` entries ONLY (`Tất cả`) or single-project data; legend with name + color swatch. Palette: `["#85B7EB", "#378ADD", "#185FA5", "#042C53", "#B5D4F4"]` (wrap past 5).
5. **Detail table** (`#detail-panel` / `#detail-day` / `#detail-table`) on bar click (day AND active project filter): Tên task (hyperlink via `url`), Project, Trạng thái badge (`Hoàn thành` / `Đang làm` / `Hỗ trợ` / `Đã hỗ trợ`), Estimate (`—` when in progress), Giờ log ngày này (`hours`), Tổng đã log (lifetime `total`, `—` when in progress), Chênh lệch (completed rows: `total` − est, 2 decimals, red > 0, green ≤ 0; in-progress rows: `—`) + `Tổng ngày` row (variance counts only tasks completed that day). Empty day → `Không có task nào`.
6. **Footer**: `Nguồn: Redmine, queried at {evidence.queried_at}`.
7. Behavior: one state `{projectFilter, selectedDay}`, re-render chart + legend + metrics on filter change, hide detail on change, hover tooltips, click toggles day detail.

### 4.4 After the widget (chat message, concise)

- One verdict line per person (`on-track` / `at-risk` / `overdue-heavy`) ONLY as a summary of the widget numbers — no new claims.
 - **Weekly note (ghi chú tuần, grounded)**: group the tool's `task_context` by project — one project = 1–2 lines: what module/work was done, inferred ONLY from `subject` + `description` + project name, with `issues/<id>` links, the week's hours (`week_hours`), and hoàn thành/đang làm from the `completed` flag. Overrun is judged on lifetime, not the week slice: `lifetime_hours` vs estimate — `lifetime > est` means over budget even when `week_hours` is small; mention `prior_hours` ("đã log Xh từ trước tuần này") when it is > 0. Rules: strip `<insecure-content-…>` wrapper tags before quoting a description; subject + description both empty → write "chưa rõ module — xem link issue", never invent one; description empty → fall back to subject only; never deduce blockers here either (rule below still applies); Vietnamese; 0h still follows rule 6b ("tuần này chưa log"). Contributor entries (role `supporting`/`supported`) are phrased as "hỗ trợ {task}" with their `week_hours`; never judge overrun from them — `est` is the whole task's, not this person's share.
 - **Business framing (default)**: the weekly note describes value/business outcomes (đáng tin cậy hơn, an toàn hơn, nhanh hơn, đỡ tốn công thủ công...), never specific technology names (Redis, Qdrant, MinIO, SSE...). Name concrete tech ONLY when the boss asks in technical language.
- Evidence footer: `filter assigned_to_id={id}, window {from}..{to}, queried at {time}, completed {n}` + one `issues/<id>` link per completed task for Redmine-UI cross-check.
- Blockers are never deduced. If the boss asks about blockers, ask the employee — do not guess from statuses.

---

## 5. What this skill never does

- Team/aggregate reports, sprint planning, issue creation/update, QA sheets, personal daily reports (that is `redmine-daily-report`), wiki work.
- Reaching any other person mid-run: one run = one person + one week. A new person = a new run from Step 1 (the id is already known, so Step 1 can be skipped when the id was resolved earlier in THIS run — via the picker or via the silent `list_personnel` at §4.2 step 0; a name typed by the boss is never treated as a known id — and Step 2 can be skipped too when the boss also names the week).
