---
name: redmine-daily-report
description: Use when the user wants a personal daily work report written from yesterday's activity — commits in the current repo plus Redmine issues updated yesterday — in a fixed two-part template (Business for leaders + Technical for the dev team), e.g. "daily report", "viết báo cáo ngày", "viết daily report", "daily update", "report hôm qua", "tạo report", "gửi report". Always ends with a mandatory user approval of the final text before anything is handed over or sent; delivery to a chat channel only happens when a send capability is configured at install time via the {{MESSAGE_DELIVERY}} placeholder, otherwise the final draft is presented for copy-paste. Scope: ONE personal report per run — team/aggregate reports are declined. Use ONLY for daily personal reports, not for weekly reports, sprint planning, or general Redmine queries.
---

# Redmine Daily Report

Write a **personal daily work report** from yesterday's real activity: commits in the current repository + Redmine issues that changed yesterday — in a fixed two-part template: a **Business** part (what the work means for the business, written for leaders at any level) and a **Technical** part (what actually moved, written for the dev team). The user can review and approve the result. Everything in this skill is a **proposal until the user explicitly approves**; nothing is ever sent anywhere without that approval.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Redmine MCP tools, `git`, shell). No platform/planning MCP server is required: reports are built from git + Redmine data the agent already has access to.

---

## 1. Core rules

1. **Mandatory approval gate**: the final report text must be **explicitly approved by the user** before it is presented for copy-paste or sent. Approval = the user confirms the final draft (e.g. "chốt", "ok", "send"). Even when the user says "gửi luôn" (send right away), still show the exact final text and confirm the destination before sending. The report is never final without this gate.
2. **Delivery is optional, config-driven**: sending to a channel only happens if a delivery config was set at install time (the `{{MESSAGE_DELIVERY}}` placeholder). Empty / still `{{...}}` / `none` → present the final report as a copy-paste block and stop. Never invent a send step that is not configured.
3. **Personal scope, one report per run**: the report covers **one person** — by default the user running the session. If the user asks for a team/aggregate report, decline: *"Skill này chỉ viết daily report cá nhân — bạn muốn report cho ai, tôi viết từng người một."* Run again per person.
4. **Live data first** — never trust memory or tool-description defaults. Exception: a fresh `.redmine` cache (≤ 14 days) is a trusted fast path for its static lists (project, members, statuses, `user_mappings`). Stale cache → warn and suggest `redmine init`; no cache → live lookups (the `redmine-init` skill creates it).
5. **Never invent activity**: every "Shipped" line must trace to a closed issue, merged PR, or commit the agent actually read; every "In flight" line to an open issue. Empty data → say so ("no tracked activity for that date") and ask the user whether to fill lines manually — do not fabricate.
6. **Business claims trace to confirmed context**: the **Business** part is *derived, never invented*. Every business statement must trace to confirmed context: the issue's user story (the `So that` value), the version/sprint goal, the project context, or the user's own words. If the link between the work and a business problem is not evident from that context → mark it `[?]` and ask the user (rule 7). Never write impact claims ("increased revenue", "customers are happier") on your own.
7. **Blockers come from the user**: a blocker is never deduced or guessed. Ask the user directly. A "Blocked"-style status on an issue is only a *hint* to ask about, never a stated blocker.
8. **Ask-before-draft**: clarify date, person, and any ambiguity first (Step 1); unresolved points stay visible as `[?]` in the draft until the user answers them.
9. **Report content is English** (the fixed template); keep the template verbatim — no extra sections, no emoji, ≤ 10 lines total. The **Business** part uses plain, jargon-free language a leader in any function understands; the **Technical** part may use implementation detail for the dev team.
10. **No state written**: this skill never modifies `.redmine` (the report is ephemeral) and never creates/updates Redmine issues.
11. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names you reuse.

---

## 2. Step 1 — Clarify the report

Ask before gathering anything (structured ask tool, plain text as fallback — 1–4 questions per call):

1. **Date**: default = **yesterday** (the last working day). If yesterday is a non-working day (Monday report → Sunday/Saturday), ask the user whether to use the previous working day (e.g. Friday). "Today" is accepted if the user asks for a mid-day report.
2. **Person**: default = the current user — detect via `git config user.name` / `user.email` and map through `.redmine` `user_mappings` (or the live members list, matching by name/email; no confident match → ask). Confirm with the user; another person → the same per-person flow.
3. **Scope of commits**: ask whether to include all commits in the current repo for that date, or only the user's own (author-filtered). Default: all commits, with authors shown in parentheses.

No other questions are needed — the template is fixed (Step 3).

---

## 3. Step 2 — Gather yesterday's data

**Date window**: let `D` = the confirmed report date; window = `D 00:00` → `D+1 00:00` (local time, `YYYY-MM-DD`).

1. **Redmine context (fast path)**: read `.redmine` at the git worktree root if present and fresh (≤ 14 days) — project, members, statuses (`is_closed`), `user_mappings`. Stale → warn + suggest `redmine init`. Missing anything needed → fetch live (list projects → identify the repo's project; confirm with the user only if ambiguous).
2. **Commits in the current repo** (`git log` in the worktree the agent runs in):
   - `git log --since="<D> 00:00" --until="<D+1> 00:00" --format="%h %s%n%b%n(%an)"` (add `--author=<name>` if the user chose author-filtered).
   - **Read the commit body (`%b`) when present** — the subject may be a short label; the body describes what was actually done and the approach/flow. Commit content is reportable; the **hash never is** (nobody outside your machine can access it) — report commit-derived work by content, never by `commit:<sha>`.
   - Work that exists **only as local commits** (no merged PR, no closed issue) → surface it to the user during the draft: *"có N commit local chưa có PR/issue — có muốn đưa vào report không?"* — include only if the user says yes (described by content, still without the hash).
   - No commits → note "no commits in <repo> for <D>"; do not invent.
3. **Redmine issues that changed yesterday** (this is the "issue tracking" half — what moved on Redmine that day):
   - Query issues of the repo's project with a `updated_on >= <D>` filter (`filters={'updated_on': '>=<D>'}`), paged (`limit` max, `include_pagination_info`), then **client-side** drop any issue whose `updated_on` is on or after `D+1` (the filter is a lower bound).
   - For the result set, note: id, subject, status (is it a *closed* status?), done_ratio, assignee, `updated_on`, and the issue URL `<redmine-url>/issues/<id>` (ask the user for the Redmine base URL if not known).
   - If needed for the status change, read the issue (journals optional) — the goal is a compact line, not a history dump.
   - No issues → say so; do not invent.
4. **Business context** (feeds the Business part — the why, not the what):
   - For the issues touched, read the parent **story** (or the issue itself when it is a story): extract the user-story `So that` value, the acceptance-criteria context, and the issue/version description — these are the only allowed sources of business framing.
   - Note the target **version** (fixed_version_id): its name and description (sprint/release goal). If the work does not belong to any version or story, there is no confirmed business framing → the Business line becomes `[?]` and is asked of the user.
5. **Merged PRs (optional)**: only if the user wants PR links and `gh` is available and authenticated: merged PRs where the merge/close date falls in the window (`gh pr list --state merged --limit N` / `gh api` for merged date). For each PR, **read the full description (body)** — `gh api "repos/<owner>/<repo>/pulls/<n>"` returns `title` + `body`. The body is the source of what was actually done and the approach used; the title alone is never enough (titles often differ from the real change). Optional — never required.
6. **Blockers**: ask the user directly: *"Hôm qua có blocker gì không? (cần gì + từ ai)"* — "none" if the user says none.

---

## 4. Step 3 — Draft the report

Fill the fixed two-part template exactly (English, ≤ 10 lines; use `—` for an empty section):

```markdown
**Daily Report — {Name} — {YYYY-MM-DD}**

**Business:**
- {1–2 bullets: which business problem advanced yesterday + what it means — jargon-free, for leaders}
- {business-level risk / anything leaders must know today, or `—`}

**Technical:**
- **Shipped:** {closed issues with links, merged PRs, commit work summaries (no hash) — outcomes only}
- **In flight:** {open issues with links and % done — most important first}
- **Blocked on:** {user-provided blocker with ask + owner, or "none"}
```

### Business part (for leaders)

- **Derived, never invented** (rule 6): every statement traces to confirmed context gathered in Step 2 (story `So that` value, version/sprint goal, project context, or the user's own words). No context → write `[?]` and ask the user.
- **Structure**: one line per business outcome — [what advanced] → [what it means for the business]. Example: *"Refund flow handles failed provider calls — refunds complete reliably, fewer support tickets."* Plain language, no issue IDs, no tech jargon; a leader in any function understands it.
- **Risk line**: only real, confirmed risks (delayed milestone, waiting on a decision, scope change) — confirmed with the user, never deduced.

### Technical part (for the dev team)

- **Shipped** = closed Redmine issues (live `is_closed`), merged PRs, and commit-derived work — every line with a link others can access where one exists (issue URL, `PR #<n>`).
  - **Never show a commit by its hash** — `commit:<sha>` is meaningless to everyone outside your machine. Commit-derived work is reported by **content**: what the commit does and its flow, from the commit body (Step 2).
  - **Write what was actually done, from the PR description / commit body** (Step 2), never the PR/commit title verbatim — titles are labels and may differ from the real change. Example: instead of `PR #247 (refund validation)` write `PR #247 — refund amount is validated against the paid total, invalid refunds return 422 with a clear message; flow: validate → call provider → retry with backoff on timeout → confirm`.
  - **Include the solution flow / approach when the description states it** (steps, fallbacks, retries, key decisions) — that is the part the team needs.
  - **No body/description available** (empty PR body, bare commit) → write `[?]` and ask the user what was actually done; never paraphrase the title into an invented description.
  - Keep each line short: one line per artifact.
- **In flight** = open issues assigned to the person (or touched by them) with `done_ratio` (e.g. `#42 Fix checkout (70%)`).
- **Blocked on** = exactly what the user said (rule 7); "none" when nothing.
- Implementation detail is welcome here (files, APIs, components) — this part is for the team that understands it.

Any unresolved point stays as `[?]` in the draft until answered.

---

## 5. Step 4 — Approval gate (mandatory)

1. Present the full draft. The user edits/rewords lines — apply every adjustment and re-present. Repeat until the user **explicitly approves the final text** ("chốt" / "ok" / "send").
2. Do not hand over or send while a `[?]` is unresolved.
3. Only after approval, proceed to Step 5.

---

## 6. Step 5 — Delivery (optional, config-driven)

Read the `{{MESSAGE_DELIVERY}}` placeholder in this file (set at install time):

| Value | Behavior |
|---|---|
| empty / still `{{...}}` / `none` (default) | **No sending.** Present the final approved report as a single copy-paste block and stop. |
| a real config (e.g. "send via the Slack MCP `send_message` tool to channel `#daily-report`") | Follow it exactly, **after** the approval gate: confirm the destination channel once if it is not explicit in the config, then send the *exact approved text*. If the configured tool is unavailable in the current session → fall back to the copy-paste block and say why; never fake a send. |

Rules: the approved text is sent verbatim; sending happens only after approval (Step 4) — approval of the text and the send are the same gate, and the destination is confirmed first.

---

## 7. Gotchas checklist

- [ ] Report date defaults to **yesterday** — confirm it; Monday reports → ask about the previous working day.
- [ ] Commit window uses local dates; Redmine `updated_on` is also day-based — drop anything updated after the window client-side.
- [ ] Empty data is reported as empty — never invent commits, issues, or blockers.
- [ ] **Never show a commit hash** (`commit:<sha>`) — commit-derived work is described by content + flow instead.
- [ ] **Shipped lines describe the real work from the PR description / commit body** (with the solution flow when stated) — never the PR/commit title verbatim; no body → `[?]` and ask, never paraphrase the title.
- [ ] **Business lines always trace to confirmed context** (story `So that`, version goal, project context, user's words) — no context → `[?]` and ask, never invent impact claims.
- [ ] Blockers come from the user, never from guessing.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] Team/aggregate reports are declined — one person per run.
- [ ] `.redmine` is read-only in this skill — never write to it.
- [ ] Delivery only via a configured `{{MESSAGE_DELIVERY}}`; otherwise copy-paste block.
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / Claude Code) for the skill to load.
