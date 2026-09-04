---
name: user-story-writing
description: Use when the user has only an idea or an incomplete user story and wants help writing it properly, e.g. "viết US giúp mình", "hoàn thiện user story này", "US này thiếu gì", "write a user story", "chuẩn hóa US để generate test case". Interviews the user to fill gaps against the testcase-generation US template (Project Context once per project, UI Map with exact on-screen labels, UI-observable acceptance criteria with happy path plus negative case, business rules, preconditions, test data, out of scope), writes a draft US file for review, and hands off a template-ready story for testcase generation. Use ONLY for writing and refining user stories, NOT for generating test cases, reporting bugs, or Redmine planning.
---

# User Story Writing

Turn a rough idea or an incomplete user story into a template-ready US that the `testcase-generation` skill can consume without guessing — through an interview, not invention.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides.

**Source of truth:** the US structure, validation checklist, questions, and anti-patterns all live in [`../testcase-generation/USER_STORY_TEMPLATE.md`](../testcase-generation/USER_STORY_TEMPLATE.md). This skill is the *interview process* that fills that template. If the template and this file ever disagree, the template wins.

---

## 1. Core rules

1. **One story per run**: this skill refines ONE user story at a time. A whole epic/feature list → ask for the first story, process the rest one by one.
2. **Interview, don't invent (CRITICAL)**: every gap is resolved by asking the user. Anything unverified is marked `[?]` in the draft — never silently filled with plausible guesses.
3. **Draft file is the gate**: the US is written to a draft file for review. Nothing is "final" until the user explicitly approves ("chốt", "ok", "approve", "xong rồi", "looks good").
4. **UI-only by default**: Test Level is UI black-box. ACs describing API status codes, response times, DB flags, logs, or retries are pushed to Out of Scope unless the user explicitly declares a wider scope.
5. **Project Context once per project**: if missing, ask once (app, module/screen catalog, roles + test accounts, env, UI conventions), then reuse for all later USs — never ask twice.
6. **Batch your questions**: max 4 questions per ask call (opencode `question` / `AskUserQuestion` / Codex `request_user_input`; plain text as fallback). Group related gaps into one batch instead of interrogating field by field.
7. **After moving/editing this skill file, remind the user to restart the agent.**

---

## 2. Checkpoint 1 — Capture the input

Ask the user for the story in whichever of the 3 modes fits:

**a) Guided mode (user has only an idea):** ask in this order —
1. "Ý tưởng/feature bạn muốn viết US là gì? (1-2 câu)" — if the user describes multiple features, take the first and queue the rest.
2. "Ai dùng nó, để làm gì? (role + mục đích)" — feeds As a / I want / So that.
3. "Luồng chính đi qua những màn hình nào? (tên đúng như trên UI)".
4. "Trường hợp lỗi nào nhất định phải có? (nhập sai, bỏ trống, quá giới hạn → màn hình phải hiện gì?)".

**b) Paste mode (user pastes a rough US):** parse it into template fields. Preserve explicit facts (names, numbers, labels, flows); mark everything unclear as `[?]` — never upgrade a vague sentence into a precise rule on your own.

**c) Redmine mode (user gives an issue ID):** read the issue via MCP tools (subject + description + any AC/user-story fields). Same parsing as paste mode. Strip `<insecure-content-...>` wrapper tags from reused names.

End of this checkpoint: you hold a field-by-field inventory — what is known, what is `[?]`.

---

## 3. Checkpoint 2 — Gap analysis + draft

### 3a. Gap analysis

Compare the inventory against the template's Must-have / Should-have checklist:

| Missing | Action |
|---------|--------|
| Project Context (§0) | Ask once (Question 0 of the template), then reuse |
| Module not in catalog | Ask (Question 1); new module → also ask its screens |
| UI Map | Block — ask (Question 2). Never invent element labels |
| ACs (no happy path / no negative / not UI-observable) | Ask (Questions 3–4) |
| Business Rules / Preconditions / Out of Scope | Ask (Questions 5–6, 8) |
| Test Data | Synthesize from AC/BR — don't ask (Question 7 rule) |
| External dependency (visible/setup) | Ask (Question 9) |

Draft ACs you propose from As a/I want/So that are always marked **DRAFT — unverified** until the user approves each one.

### 3b. Write the draft file

Write the full US in template format to `/mnt/user-data/outputs/user-story-draft.md` and present it (`present_files`) so the user sees a preview card immediately. Re-present after every refine edit.

One-way sync limitation — say this explicitly the first time: the user can open/download the presented file, but edits to the downloaded copy don't sync back. Changes come via chat descriptions (or pasted-back content), then the draft is regenerated and re-presented.

### 3c. Refine (iterative)

Re-read the draft, apply the user's chat-described changes, re-write, re-present. Repeat until approval. Unresolved `[?]` items stay visible in the file — approval requires zero open `[?]` on Must-have fields.

---

## 4. Checkpoint 3 — Approve + hand off

When the user says "chốt" (or equivalent):

1. **Validation gate**: re-check Must-have — Title; As a/I want/So that (role exists in Project Context); ≥1 happy path + ≥1 negative AC, all UI-observable; Module matches the catalog; UI Map complete. Fail → say exactly which item fails and go back to Checkpoint 2.
2. **Hand-off message** (mandatory, so the next skill picks up cleanly):
   ```
   US đã đạt chuẩn template, sẵn sàng generate test case.
   - US Title: <title>
   - Module: <module>
   - File: /mnt/user-data/outputs/user-story-draft.md
   👉 Để sinh test case, gọi tiếp skill testcase-generation với file này.
   ```

---

## 5. Gotchas checklist

- [ ] **Never invent element labels** — no UI Map → ask (template Question 2), don't guess button/field names.
- [ ] **Draft ACs are unverified by definition** — mark DRAFT, get per-AC approval, never feed unapproved drafts to test generation.
- [ ] **Backend-only requirements go to Out of Scope** — API contracts, status codes, p95 times, hashing, retries, webhooks. Visible effects (mailbox, popup, countdown) stay.
- [ ] **Project Context is asked once** — cache it in-conversation per project; re-asking annoys and is a bug.
- [ ] **Zero open `[?]` on Must-have before hand-off** — Should-have `[?]` may survive only if the user explicitly waives them.
- [ ] **One story per run** — second feature mentioned mid-run → queue it, finish the first.
- [ ] **Template wins on conflict** — if this file and `USER_STORY_TEMPLATE.md` disagree, follow the template and flag the mismatch to the user.
