# user-story-writing skill

A user-facing agent skill that interviews you to turn a rough idea or an incomplete user story into a template-ready US — validated against the `testcase-generation` US template and ready to feed test case generation.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting. The US structure itself lives in [`../testcase-generation/USER_STORY_TEMPLATE.md`](../testcase-generation/USER_STORY_TEMPLATE.md) (single source of truth).

---

## 1. How the skill works

| Step | What happens |
|---|---|
| 1 | **Capture** — you describe the idea, paste a rough US, or give a Redmine issue ID |
| 2 | **Gap analysis** — agent compares your input against the US template checklist |
| 3 | **Interview** — agent asks batched questions (max 4 per round), never invents answers |
| 4 | **Draft** — full US written to `/mnt/user-data/outputs/user-story-draft.md` for review |
| 5 | **Refine** — you request changes in chat, agent rewrites and re-presents |
| 6 | **Approve + hand off** — you say "chốt" → validation gate → handoff to `testcase-generation` |

Key rules: **Project Context is asked once per project, then reused.** Unverified points stay marked `[?]` — approval requires zero open `[?]` on Must-have fields. Default scope is UI black-box testing.

---

## 2. Installation

### One-liner installer (recommended)

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### Manual copy

| Location | Works with |
|---|---|
| `.agents/skills/user-story-writing/` (inside your repo) | opencode + Agent SDK |
| `.opencode/skills/user-story-writing/` (inside your repo) | opencode |

```bash
cp -r <path-to-this-repo>/skills/user-story-writing .agents/skills/
```

Then **restart your agent**.

---

## 3. Usage

### Write a US from an idea

> "Viết US giúp mình: cho phép học sinh đăng nhập bằng email..."
> "Hoàn thiện user story này..."
> "US này còn thiếu gì để generate test case?"

### Workflow

1. Agent interviews you (batched questions, plain language)
2. Draft US appears as a file preview — review it
3. Request changes in chat until satisfied → say "chốt"
4. Agent hands off: US Title + Module + file path for `testcase-generation`

### Result

- Draft file `/mnt/user-data/outputs/user-story-draft.md` with the complete US
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

```bash
git pull --rebase
# re-run installer
```

Restart agent after update.
