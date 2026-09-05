---
name: user-story-writing
description: Use when user wants to write or refine a user story: viet US, hoan thien US, US thieu gi, chuan hoa US. Interviews to fill US template, hands off to testcase-generation. NOT for test cases or bugs.
---

# User Story Writing

Turn a rough idea or an incomplete user story into a template-ready US that the `testcase-generation` skill can consume without guessing — through an interview, not invention.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides.

**Source of truth:** the US structure, validation checklist, questions, and anti-patterns all live in [`./USER_STORY_TEMPLATE.md`](./USER_STORY_TEMPLATE.md) (vendored copy of `../testcase-generation/USER_STORY_TEMPLATE.md` so the Claude Desktop ZIP stays standalone). This skill is the *interview process* that fills that template. If the template and this file ever disagree, the vendored template wins — flag the mismatch to the user.

---

## 1. Core rules

1. **One story per run**: this skill refines ONE user story at a time. A whole epic/feature list → ask for the first story, process the rest one by one.
2. **Interview, don't invent (CRITICAL)**: every gap is resolved by asking the user or by a user-approved DRAFT (see rule 8). Anything unverified is marked `[?]` in the draft — never silently filled with plausible guesses.
3. **Draft file is the gate**: the US is written to a draft file for review. Nothing is "final" until the user explicitly confirms — summarize zero open `[?]` on Must-have, then ask the user to reply "chốt" to approve. A bare "ok" acknowledging receipt does NOT count as approval.
4. **UI-only by default**: Test Level is UI black-box. ACs describing API status codes, response times, DB flags, logs, or retries are pushed to Out of Scope unless the user explicitly declares a wider scope.
5. **Project Context once per project (per conversation)**: if missing, ask once (app, module/screen catalog, roles + test accounts, env, UI conventions), then reuse for all later USs in this conversation — never ask twice in the same conversation. Claude Desktop has no cross-session memory, so a new session asks again — say this plainly.
6. **Batch your questions**: max 4 questions per ask call (opencode `question` / `AskUserQuestion` / Codex `request_user_input`; plain text as fallback). Group related gaps into one batch instead of interrogating field by field.
7. **After first install/move of this skill, remind the user to restart the agent once (not on every edit).**
8. **Draft ACs first, interview the gaps**: after Capture, write 6–7 DRAFT ACs (1–2 happy path + edge cases you infer — see the edge-case catalog in 3a) instead of opening with blank questions. Users usually think happy case only; your draft is what shows them the full picture. Approval gate (mandatory): present every proposal in chat FIRST — nothing enters the draft file unreviewed. The user reviews each AC and each vagueness-table row (keep/edit/drop); only kept/edited items go into the file, the rest stay `[?]` or are dropped. Only ask about: (a) root facts a draft cannot guess (exact labels, limit numbers), (b) vague points needing a business decision. Every proposal stays DRAFT until approved; anything unconfirmed stays `[?]` — never finalize a guess, never write an unreviewed proposal into the file.

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

Compare the inventory against the template's Must-have / Should-have checklist. Default move is **propose first** — ask only what a draft cannot cover:

| Missing | Propose first (default) | Ask only when |
|---------|------------------------|---------------|
| Project Context (§0) | Pre-fill from anything the user already said (app hints, roles mentioned), mark gaps `[?]` | Ask once (Question 0) for what no context covers, then reuse |
| Module not in catalog | Propose the module from the story; new module → draft its likely screens from the flow described | Ask (Question 1) to confirm the name + screens |
| UI Map | Draft the flow from the screens mentioned; never invent element labels — mark them `[label?]` | Block — ask (Question 2) for exact labels + entry/exit |
| ACs (no happy path / no negative / not UI-observable) | Write 6–7 DRAFT ACs: 1–2 happy + edge cases from the catalog below (Questions 3–4 as inspiration, not interrogation) | Ask only for root facts (numbers, exact texts) |
| Business Rules / Preconditions / Out of Scope | Propose standard rules from the domain (Questions 5–6, 8 as inspiration) | Ask to confirm numbers and scope calls |
| Test Data | Synthesize from AC/BR — don't ask (Question 7 rule) | — |
| External dependency (visible/setup) | Propose likely setup needs from the flow | Ask (Question 9) to confirm |

### Edge-case proposal catalog (scan every story against these; matching dimension → draft an AC, missing info → vagueness table, never an immediate question)
- Invalid input (wrong format/type) → negative AC
- Empty (nothing selected, blank field, submit disabled?) → negative AC
- Boundary (count/size/pages: max, max+1, zero) → boundary ACs
- Duplicate (same name/content twice: skip or error?) → AC + vagueness row if ambiguous
- Partial failure (1 item fails in a batch: block all or skip one?) → AC + vagueness row
- Async (processing state, timeout, exit mid-way, reopen still shows status?) → state ACs
- Permission/role (who can/can't, given the roles in context) → permission AC if roles exist
- Concurrency/recovery (two actors, crash/retry) → only if the flow hints at it; else skip silently

### Vagueness table (the default output for ambiguity — proposed in chat FIRST, recorded in the file only after review)
Each row: vague point | which edge ACs it affects | 2–3 recommended options (concrete, using the user's real screens) | user decision (keep/edit/drop per row).
Recommendations must reuse facts the user already gave (their screens, their numbers); plain business language, no jargon — explain any term in one line.
Chat-first rule: present the table in chat and collect keep/edit/drop per row BEFORE writing the file. The file copy records only reviewed rows — decided items as final text, explicitly deferred ones as `[?]`; never copy an unreviewed row into the file.

**Example — same gap, two styles (always use the second):**
- Ask-style (don't): "Negative case nào bạn muốn có?"
- Propose-style (do): "Tôi đề xuất sẵn 3 AC: (1) chọn `tool.exe` → toast lỗi, file bị loại khỏi lô; (2) file thứ 21 → disabled, không chọn được; (3) 1 file lỗi parse → block cả lô. Bạn duyệt/sửa/bỏ từng cái nhé. Còn 1 điểm mơ hồ: file trùng tên tính là lỗi (block lô) hay tự bỏ qua (lô tiếp tục)? Tôi recommend tự bỏ qua vì bạn đã nói trùng tên là case thường gặp..."

All DRAFT ACs stay **DRAFT — unverified** until the user approves each one. Refine merges 6–7 down to ~5 per the template.

### 3b. Write the draft file

Write the full US in template format to `/mnt/user-data/outputs/user-story-draft.md` and present it (`present_files`) so the user sees a preview card immediately. Re-present after every refine edit.

The first draft has two blocks: (1) the full US with the approved ACs, (2) the reviewed vagueness table. Order of work: present proposals (ACs + table rows) in chat → collect keep/edit/drop → THEN write the file from approved items only. When presenting the file, summarize the reviewed table in chat too (one line per row: point → decision taken) — the file carries the detail, the chat carries the decision record.

One-way sync limitation — say this explicitly the first time: the user can open/download the presented file, but edits to the downloaded copy don't sync back. Changes come via chat descriptions (or pasted-back content), then the draft is regenerated and re-presented.

### 3c. Refine (iterative)

Re-read the draft, apply the user's chat-described changes, re-write, re-present. Repeat until approval. Unresolved `[?]` items stay visible in the file — approval requires zero open `[?]` on Must-have fields.

---

## 4. Checkpoint 3 — Approve + hand off

When the user replies "chốt" to the approval summary (equivalents: "approve", "xong rồi", "looks good" — a bare "ok" alone does NOT count):

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
- [ ] **Project Context is asked once per conversation** — cache it in-conversation per project; re-asking in the same conversation is a bug. A new session asking again is expected (no cross-session memory) — say so.
- [ ] **Draft edge ACs before asking** — users think happy case only; the 6–7 DRAFT + vagueness table is what shows them the full picture.
- [ ] **Every edge DRAFT needs its vagueness row** — if an edge AC hinges on an undecided meaning, that meaning must appear in the table, not hide inside the AC.
- [ ] **Never write an unreviewed proposal into the draft file** — chat approval (keep/edit/drop) comes first; the file holds approved items + `[?]` for deferred ones only.
- [ ] **Zero open `[?]` on Must-have before hand-off** — Should-have `[?]` may survive only if the user explicitly waives them.
- [ ] **One story per run** — second feature mentioned mid-run → queue it, finish the first.
- [ ] **Template wins on conflict** — if this file and `USER_STORY_TEMPLATE.md` disagree, follow the template and flag the mismatch to the user.
