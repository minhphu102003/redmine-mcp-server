---
name: boss-project-oversight
description: Use when the boss (a manager, in Vietnamese or English) asks about an employee's work — "cho tôi danh sách nhân viên", "xem A đang làm gì", "A có task nào trễ không", "A có kịp tiến độ không", performance by day/week. Runs a 3-step flow: (1) list personnel so the boss picks one person, (2) ask day or week, (3) show the backend summary grouped by project. ONE person per run — team/aggregate views are declined. Use ONLY for per-person oversight, not for daily personal reports, planning, or QA work.
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

## 4. Step 3 — Summary grouped by project

Call `get_person_work_summary(person=<id from step 1>, window=<day|week>, date_str=<date>)`. If the tool returns an `ambiguous` error, present the candidates and let the boss pick — never guess.

Render the result in this shape (Vietnamese headers, concise):

```markdown
**Hiệu suất — {Tên} — {Ngày | Tuần T2 DD/MM – CN DD/MM}**

Tổng: {hours}h đã log · {touched} issues đã chạm · {closed} đã đóng · tồn đọng {open} (trễ {overdue})

**{Project A}:**
- Activity: {hours}h · đã chạm: #{id} subject (status, %done) · đã đóng: #{id} subject
- Tồn đọng: trễ: #{id} subject (due DD/MM, %done, link) · chưa có hạn: #{id} subject · đang làm: ...

**{Project B}:** ...

Evidence: filter assigned_to_id={id}, window {from}..{to}, queried at {time}, total_count {n}. Đối chiếu: {redmine-base}/issues/<id>.
```

- Verdict line per person ("on-track / at-risk / overdue-heavy") is allowed ONLY as a summary of the numbers above — one line, no new claims.
- Blockers are never deduced. If the boss asks about blockers, ask the employee — do not guess from statuses.

---

## 5. What this skill never does

- Team/aggregate reports, sprint planning, issue creation/update, QA sheets, personal daily reports (that is `redmine-daily-report`), wiki work.
- Reaching any other person mid-run: one run = one person. A new person = a new run from Step 1 (the id is already known, so Step 1 can be skipped when the boss names them directly).
