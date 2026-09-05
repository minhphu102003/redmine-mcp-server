# user-story-writing skill

A user-facing agent skill that interviews you to turn a rough idea or an incomplete user story into a template-ready US — validated against the `testcase-generation` US template and ready to feed test case generation.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting. The US structure itself lives in [`./USER_STORY_TEMPLATE.md`](./USER_STORY_TEMPLATE.md) (vendored copy of [`../testcase-generation/USER_STORY_TEMPLATE.md`](../testcase-generation/USER_STORY_TEMPLATE.md); the original is the single source of truth).

---

## 1. How the skill works

| Step | What happens |
|---|---|
| 1 | **Capture** — you describe the idea, paste a rough US, or give a Redmine issue ID |
| 2 | **Gap analysis** — agent compares your input against the US template checklist |
| 3 | **Propose + interview** — agent drafts 6–7 ACs (happy + edge it infers) with concrete options, asks batched follow-ups (max 4 per round) only for gaps drafts can't cover |
| 4 | **Draft** — full US written to `/mnt/user-data/outputs/user-story-draft.md` and shown as a preview card for review (one-way sync: describe changes in chat, draft is regenerated and re-presented) |
| 5 | **Refine** — you request changes in chat, agent rewrites and re-presents |
| 6 | **Approve + hand off** — you say "chốt" → validation gate → handoff to `testcase-generation` |

Key rules: **Project Context is asked once per project per conversation, then reused.** The agent proposes 6–7 DRAFT ACs + edge cases first — you keep/edit/drop in chat, and only approved items enter the draft file (never unreviewed proposals). Unverified points stay marked `[?]` — approval requires zero open `[?]` on Must-have fields plus an explicit "chốt" reply (a bare "ok" does not count). Default scope is UI black-box testing.

---

## 2. Installation (Claude Desktop)

### ZIP installer (recommended)

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1
```

This creates `claude-desktop-skills/user-story-writing.zip` (includes `SKILL.md` + vendored `USER_STORY_TEMPLATE.md` so the ZIP stays standalone).

Then import:

1. Open Claude Desktop
2. Go to Settings > Customize > Skills
3. Click 'Add Skill' > Upload ZIP file
4. Select `claude-desktop-skills/user-story-writing.zip`

Then **restart Claude Desktop once after first install**.

---

## 3. Usage

### Write a US from an idea

> "Viết US giúp mình: cho phép học sinh đăng nhập bằng email..."
> "Hoàn thiện user story này..."
> "US này còn thiếu gì để generate test case?"

### Workflow

1. Agent proposes 6–7 ACs (happy + edge cases it infers) plus a vagueness table — in chat first
2. You review each proposal (keep/edit/drop) — only approved items enter the draft file, the rest stay `[?]` or are dropped
3. Request changes in chat until satisfied → confirm the zero-`[?]` summary → reply "chốt" (a bare "ok" does not count)
4. Agent hands off: US Title + Module + file path for `testcase-generation`

### Result

- Draft file `/mnt/user-data/outputs/user-story-draft.md` with the complete US (shown as a preview card; edits come via chat, then the draft is regenerated and re-presented)
- Handoff message to continue with test case generation

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| Skill not triggering | Restart agent; check frontmatter in SKILL.md |
| Agent invents element names | Stop it — point at the real UI labels; it must ask (Question 2) |
| Handoff blocked | Check which Must-have item fails; resolve the `[?]` items |
| Template mismatch | `USER_STORY_TEMPLATE.md` wins; report the conflict |

---

## 5. Keeping the skill up to date

```powershell
git pull --rebase
# re-run the Claude Desktop installer, then re-upload the new ZIP
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1
```

Restart Claude Desktop after update.
