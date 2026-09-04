# Redmine MCP Server

> 🌐 English: [README.md](./README.md) · Tiếng Việt: [README.vi.md](./README.vi.md)

让 AI 助手替你操作 Redmine。连接一次、安装一个 skill，之后只需对话 — *"create a Redmine issue for this commit"*、*"An 这周表现如何？"*、*"为这个 story 生成测试用例"* — 每一步确认即可。其余工作由助手完成。

## 你是谁？选择你的通道

| 👔 老板 / 管理者 | 💻 开发者 | 🧪 测试 |
|---|---|---|
| 一次只问一名员工 — *"An 在做什么？"*、*"有延期任务吗？"* — 按项目分组的日/周绩效可视化组件。只读，不会误改数据。 | Commit 和 PR 自动变成 Redmine issue：命名、描述、已验证 ID、changelog、工时记录。你只需确认。 | 用户故事变成测试用例，bug 在 Google Sheets 和 Redmine 之间流转，状态同步回来。你负责评审和批准。 |

每个通道都由下面的 agent skill 驱动。用一句话告诉助手你在哪个通道，剩下的交给它。

## 5 分钟快速开始

### 1. 获取 Redmine API key

登录 Redmine，打开 **My account → API access key → Show** 并复制 key。

> Redmine 6.1+ 可使用按用户的 OAuth2 登录代替共享 key — 见 [OAuth Setup](./docs/oauth-setup.md)。管理者注意：oversight skill 需要 **admin** key 才能获取人员列表。

### 2. 用 Docker 启动服务器

```bash
cp .env.example .env.docker
# 在 .env.docker 中填写 REDMINE_URL 和 REDMINE_API_KEY，然后：
docker compose up --build -d
curl http://localhost:8000/health
```

全部配置项（认证模式、只读模式、SSL 等）见 [.env.example](./.env.example)。

### 3. 安装你通道的 skill（一行命令）

**开发者**（issue 流程、规划、日报）：

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-dev.ps1 | iex
```

**测试**（基于 Google Sheets 的 QA 测试管理）：

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-tester.ps1 | iex
```

**两者都要**（全部 skill）：

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### 这些命令在哪里运行？

- 💻 **开发者 — 在你的 repo 里运行。** 在你工作的仓库中打开终端并粘贴命令。脚本通过 `git` 找到 repo 根目录，把 skill 放进 `<repo>/.agents/skills/`（opencode 和 Agent SDK 会自动扫描）。没有 repo 就没有 skill — dev 流程需要代码在旁边。
- 🧪 **测试 — 不需要 repo。** 如果你在某个 repo 里工作，上面的 tester 命令照常用。否则跳过，用下面的桌面应用方式：user 级安装或 ZIP 上传会把 QA skill 放到 Claude Desktop、Codex 或 opencode desktop 能看到的位置 — 不需要仓库。
- 👔 **老板 — 不需要 repo，也不需要会用终端。** 安装桌面应用（[Claude Desktop](https://claude.ai/download)、[Codex](https://developers.openai.com/codex/) 或 [opencode](https://opencode.ai/docs) desktop），连接服务器一次（第 4 步），再通过下面的 user 级安装或 ZIP 上传获取 oversight skill。之后只需聊天。

然后重启助手并打个招呼：

- 👔 *"给我员工列表"* → 选一个名字 → *"这周"*
- 💻 在 repo 里运行一次 `redmine init`，然后 *"为这个 commit 创建 Redmine issue"*
- 🧪 *"为这个用户故事生成测试用例"*（需要下面的 Google Sheets 配置）

> **内置 GitHub 支持** — dev 流程通过 `gh` CLI 读取 commit/PR（device flow，无需粘贴 token）：`gh auth login`。

### 4. 把助手连接到服务器

服务器在 `http://127.0.0.1:8000/mcp` 提供 MCP。以 opencode 为例（`opencode.json`）：

```json
{
  "mcp": {
    "redmine": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "X-Redmine-URL": "https://redmine.yourcompany.com",
        "X-Redmine-API-Key": "your_api_key"
      }
    }
  }
}
```

`X-Redmine-*` header 仅在 `dynamic` 认证模式下需要；默认 `legacy` 模式使用 `.env.docker` 中的 key。Claude Desktop、VS Code、Grok、Codex 和 Cline 的配置见 [integrations.md](./docs/integrations.md)。secret 不要进 git（`"{env:REDMINE_API_KEY}"`、`env_http_headers` 等）。修改后重启助手。

### 5. Google Sheets（仅测试）

QA skill 通过 service account 在 Google Sheets 中跟踪测试用例和 bug：

1. 在 [Google Cloud Console](https://console.cloud.google.com) 中：启用 **Google Sheets API**，创建 **Service Account**，添加 **JSON key**，保存为 `credentials/service-account.json`。
2. 把表格共享（Editor 权限）给 service account 邮箱，例如 `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`。
3. 当 `redmine init`（tester 流程）询问时粘贴表格 URL/ID。Sheet ID 即 `docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit` 中间那段。

## 全部 skill

| Skill | 通道 | 你说什么 → 得到什么 |
|---|---|---|
| [`redmine-init`](./skills/redmine-init/README.md) | 💻 Dev | *“映射这个 repo”* → repo ↔ Redmine 项目关联，成员/tracker 缓存 |
| [`redmine-issue-workflow`](./skills/redmine-issue-workflow/README.md) | 💻 Dev | *“为这个 commit 建 issue”* → 创建已验证 issue，合并 PR → 记录状态/工时 |
| [`redmine-planning`](./skills/redmine-planning/README.md) | 💻 Dev | *“拆分这个 story”* → 含估算、分派、依赖的任务 |
| [`redmine-daily-report`](./skills/redmine-daily-report/README.md) | 💻 Dev | *“日报”* → 昨天的业务版 + 技术版总结 |
| [`boss-project-oversight`](./skills/boss-project-oversight/README.md) | 👔 老板 | *“An 这周的绩效”* → 按项目的交互组件（只读，admin key） |
| [`testcase-generation`](./skills/testcase-generation/README.md) | 🧪 测试 | *“为这个故事写测试用例”* → 评审过的用例写入 Sheets |
| [`bug-reporting`](./skills/bug-reporting/README.md) | 🧪 测试 | *“记录这个 bug”* → Sheets 中自动 ID 的 bug 行 |
| [`bug-to-redmine`](./skills/bug-to-redmine/README.md) | 🧪 测试 | *“把 bug 推到 Redmine”* → 创建 issue，ID 回写 |
| [`status-sync`](./skills/status-sync/README.md) | 🧪 测试 | *“开发改完了吗？”* → 表格状态从 Redmine 同步 |
| [`reopen-bug`](./skills/reopen-bug/README.md) | 🧪 测试 | *“重开 BUG-001”* → 按允许的工作流重开 issue，表格更新 |

### Claude Desktop 用户（测试 & 老板：不需要 repo）

Claude Desktop 以 ZIP 文件导入 skill — 适合不在仓库里工作的场景。构建方法：

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1
```

然后 **Settings → Customize → Skills → Add Skill → Upload ZIP**（每个 skill 重复一次）：

| ZIP | 通道 |
|---|---|
| `redmine-init` | 💻 Dev 入门 |
| `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug` | 🧪 测试 |
| `boss-project-oversight` | 👔 老板 |

### User 级安装（opencode global / ChatGPT desktop）

当你希望 skill **处处可用**而不只限于一个 repo 时推荐 — opencode 和 ChatGPT 桌面应用都会自动扫描 `%USERPROFILE%\.agents\skills\`。这是在桌面应用（opencode、Codex、ChatGPT）里工作、不涉及仓库的 🧪 测试和 👔 老板最省事的路径：

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex
```

安装 7 个 skill（`redmine-init`、`testcase-generation`、`bug-reporting`、`bug-to-redmine`、`status-sync`、`reopen-bug`、`boss-project-oversight`）及模板文件（不含 `README.md`）。重复运行时遇到 GitHub rate limit？先设置 `$env:GITHUB_TOKEN = "<your_pat>"`（`public_repo` scope 足够）。卸载：`Remove-Item -Recurse -Force $env:USERPROFILE\.agents\skills`。

## 🎬 视频指南（测试 & 老板）

简短 walkthrough — 先看再跟着上面的步骤操作。（录制完成后链接会发布在这里；每行在此之前保留占位。）

| 通道 | 视频 | 链接 |
|---|---|---|
| 🧪 测试 | 配置：桌面应用 + 服务器连接 + QA skill 安装 | *coming soon* <!-- VIDEO-TESTER-SETUP: replace with https://... --> |
| 🧪 测试 | 使用：第一次端到端运行（story → 测试用例 → bug → Redmine） | *coming soon* <!-- VIDEO-TESTER-USAGE: replace with https://... --> |
| 👔 老板 | 配置：桌面应用 + 只读连接 + oversight skill | *coming soon* <!-- VIDEO-BOSS-SETUP: replace with https://... --> |
| 👔 老板 | 使用：员工列表 → 选一个人 → 日/周绩效组件 | *coming soon* <!-- VIDEO-BOSS-USAGE: replace with https://... --> |

## 内部原理

服务器提供 **39 个 MCP tool** 供 skill 代为调用：issue（创建/列表/更新/关联）、工时、wiki 页面、人员与绩效汇总、全局搜索，以及 Google Sheets 和 memory 工具。见 [MCP Tools](./docs/mcp-tools.md) 和 [Tool Reference](./docs/tool-reference.md)。

| 认证模式 | 适用场景 |
|---|---|
| `legacy`（默认） | 单用户 / 共享凭证 — `.env` 中的一个 API key |
| `oauth` | 按用户登录，Redmine 6.1+ — 见 [OAuth Setup](./docs/oauth-setup.md) |
| `dynamic` | 多租户 / 共享 VPS — 助手按每次请求发送 `X-Redmine-URL` + `X-Redmine-API-Key` |

用 `REDMINE_AUTH_MODE=legacy|oauth|dynamic` 设置。公网部署：优先 `oauth`/`dynamic`；老板的机器：加 `REDMINE_MCP_READ_ONLY=true`。

## Docs

- [MCP Tools](./docs/mcp-tools.md) — 全部 tool 和 MCP resource
- [Tool Reference](./docs/tool-reference.md) — 详细参数参考
- [Docker & VPS deployment](./docs/docker-deployment.md) — 本地 Docker 细节、加固 VPS + HTTPS 配置
- [Claude Desktop setup](./docs/claude-desktop-setup.md) — Claude Desktop 上的 MCP + skill
- [OAuth Setup](./docs/oauth-setup.md) — 按用户的 OAuth2（Redmine 6.1+）
- [Troubleshooting](./docs/troubleshooting.md) — 常见问题
- [Contributing](./docs/contributing.md) — 开发环境配置
- [Changelog](./CHANGELOG.md)

## License

MIT — 见 [LICENSE](./LICENSE)。
