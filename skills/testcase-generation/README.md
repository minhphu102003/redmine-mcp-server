# testcase-generation skill

A user-facing agent skill that generates test cases from a user story and pushes them to a Google Sheet ("TestCases") with auto-generated IDs, headers, and a companion "Bugs" sheet ready for bug reporting.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting.

---

## 1. How the skill works

| Step | What happens |
|---|---|
| 1 | **Clarify** — confirms the user story source and target spreadsheet |
| 2 | **Parse** — reads the user story, extracts test scenarios |
| 3 | **Validate** — checks for missing US fields, asks user if needed |
| 4 | **Draft** — writes test cases to `.tmp/testcases-draft.md` for review |
| 5 | **Refine** — user edits the draft file, agent re-reads on request |
| 6 | **Approve** — user says "chốt" / "ok" / "approve" → agent reads final draft |
| 7 | **Push** — auto-generates TC-IDs, ensures Bugs sheet, writes to Google Sheet |

Key rules: **nothing touches Google Sheets until the user explicitly approves.** Max ~10 detailed test cases per turn — the rest go in self-contained outlines.

---

## 2. Installation

### One-liner installer (recommended)

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### Manual copy

| Location | Works with |
|---|---|
| `.agents/skills/testcase-generation/` (inside your repo) | opencode + Agent SDK |
| `.opencode/skills/testcase-generation/` (inside your repo) | opencode |

```bash
cp -r <path-to-this-repo>/skills/testcase-generation .agents/skills/
```

Then **restart your agent**.

### Prerequisites

- Redmine MCP server running (Google Sheets auth is handled server-side)
- "TestCases" sheet must exist (or will be created during init)

---

## 3. Usage

### Create test cases from a user story

> "Tạo test case từ user story này..."
> "Create test cases for the login feature"
> "Generate test cases from this story"

### Workflow

1. Agent parses the user story → writes draft to `.tmp/testcases-draft.md`
2. You open the file and edit directly (add/remove/modify test cases)
3. When satisfied → say "chốt" / "approve" / "ok"
4. Agent pushes to Google Sheet

### Questions the skill will ask

1. Where is the user story? (file path, pasted text, or Redmine issue ID)
2. Which spreadsheet ID? (or use memory from `.google-sheets`)

### Result

- Draft file `.tmp/testcases-draft.md` with all test cases
- After approval: test cases pushed to Google Sheet with auto-generated IDs
- "Bugs" sheet created with headers if not already present

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| Skill not triggering | Restart agent; check frontmatter in SKILL.md |
| Draft file not created | Check write permissions for `.tmp/` directory |
| "Spreadsheet not found" | Check `.google-sheets` memory or run `redmine init` |
| Test cases not appearing after push | Read sheet back to verify; may have wrong range filter |
| Want to edit after push | Modify draft file → run skill again to re-push |

---

## 5. Keeping the skill up to date

```bash
git pull --rebase
# re-run installer
```

Restart agent after update.
