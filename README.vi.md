# Redmine MCP Server

> 🌐 English: [README.md](./README.md)

Agent AI của bạn làm việc với Redmine thay cho bạn. Kết nối một lần, cài skill, rồi chỉ việc trò chuyện — *"create a Redmine issue for this commit"*, *"An tuần này làm việc thế nào?"*, *"sinh test case cho story này"* — và xác nhận từng bước. Phần còn lại agent tự lo.

## Bạn là ai? Chọn làn của mình

| 👔 Sếp / Quản lý | 💻 Developer | 🧪 Tester |
|---|---|---|
| Hỏi về từng nhân viên một — *"An đang làm gì?"*, *"có task nào trễ hạn không?"* — rồi nhận widget hiệu suất ngày/tuần theo từng dự án. Chỉ đọc, không thể vô tình làm đổi dữ liệu. | Commit và PR tự thành Redmine issue: đặt tên, mô tả, kiểm chứng ID, changelog, log giờ. Bạn chỉ việc xác nhận. | User story thành test case, bug luân chuyển giữa Google Sheets và Redmine, trạng thái đồng bộ ngược lại. Bạn xem xét và phê duyệt. |

Mỗi làn được dẫn dắt bởi một agent skill bên dưới. Nói với agent một câu bạn thuộc làn nào, việc còn lại cứ để nó lo.

## Bắt đầu nhanh — 5 phút

### 1. Lấy Redmine API key

Đăng nhập Redmine, mở **My account → API access key → Show** rồi copy key.

> Redmine 6.1+ có thể đăng nhập OAuth2 theo từng user thay vì key chung — xem [OAuth Setup](./docs/oauth-setup.md). Quản lý lưu ý: skill giám sát cần key **admin** để lấy danh sách nhân sự.

### 2. Chạy server bằng Docker

```bash
cp .env.example .env.docker
# điền REDMINE_URL và REDMINE_API_KEY vào .env.docker, rồi chạy:
docker compose up --build -d
curl http://localhost:8000/health
```

Xem [.env.example](./.env.example) để biết mọi thiết lập (chế độ auth, chế độ chỉ đọc, SSL, ...).

### 3. Cài skill cho làn của bạn (một lệnh)

**Cho developer** (quy trình issue, lập kế hoạch, báo cáo ngày):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-dev.ps1 | iex
```

**Cho tester** (quản lý test QA với Google Sheets):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-tester.ps1 | iex
```

**Cho cả hai** (mọi skill):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### Chạy các lệnh trên ở đâu?

- 💻 **Developer — chạy bên trong repo của bạn.** Mở terminal trong repository bạn đang làm việc rồi dán lệnh vào. Script tự tìm repo root qua `git` và đặt skill vào `<repo>/.agents/skills/` (opencode và Agent SDK tự quét). Không có repo thì không có skill — quy trình dev cần code nằm cạnh bên.
- 🧪 **Tester — không cần repo.** Nếu bạn có làm việc trong repo thì dùng lệnh tester ở trên như bình thường. Nếu không, bỏ qua và dùng app desktop bên dưới: cách cài user-level hoặc tải ZIP đặt skill QA vào chỗ Claude Desktop, Codex hay opencode desktop nhìn thấy — không cần repository.
- 👔 **Sếp — không cần repo, không cần quen terminal.** Cài app desktop ([Claude Desktop](https://claude.ai/download), [Codex](https://developers.openai.com/codex/) hoặc [opencode](https://opencode.ai/docs) desktop), kết nối tới server một lần (bước 4), rồi lấy skill giám sát qua cách cài user-level hoặc tải ZIP bên dưới. Từ đó về sau chỉ việc trò chuyện.

Rồi khởi động lại agent và chào một câu:

- 👔 *"Cho tôi danh sách nhân viên"* → chọn một tên → *"tuần này"*
- 💻 Chạy `redmine init` một lần trong repo, rồi *"tạo Redmine issue cho commit này"*
- 🧪 *"Sinh test case cho user story này"* (cần setup Google Sheets bên dưới)

> **Đã tích hợp sẵn GitHub** — quy trình dev đọc commit/PR qua `gh` CLI (device flow, không cần dán token): `gh auth login`.

### 4. Kết nối agent tới server

Server nói MCP tại `http://127.0.0.1:8000/mcp`. Ví dụ với opencode (`opencode.json`):

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

Header `X-Redmine-*` chỉ cần ở chế độ auth `dynamic`; chế độ mặc định `legacy` dùng key trong `.env.docker`. Cấu hình cho Claude Desktop, VS Code, Grok, Codex và Cline xem tại [integrations.md](./docs/integrations.md). Giữ secret ngoài git (`"{env:REDMINE_API_KEY}"`, `env_http_headers`, ...). Khởi động lại agent sau khi sửa.

### 5. Google Sheets (chỉ tester)

Skill QA theo dõi test case và bug trong Google Sheets qua service account:

1. Trong [Google Cloud Console](https://console.cloud.google.com): bật **Google Sheets API**, tạo **Service Account**, thêm **JSON key**, lưu thành `credentials/service-account.json`.
2. Share spreadsheet (quyền Editor) cho email service account, ví dụ `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`.
3. Dán URL/ID sheet khi `redmine init` (luồng tester) hỏi tới. Sheet ID là đoạn giữa của `docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`.

## Mọi skill

| Skill | Làn | Bạn nói gì → nhận gì |
|---|---|---|
| [`redmine-init`](./skills/redmine-init/README.md) | 💻 Dev | *"map repo này"* → repo ↔ dự án Redmine được liên kết, cache thành viên/tracker |
| [`redmine-issue-workflow`](./skills/redmine-issue-workflow/README.md) | 💻 Dev | *"issue cho commit này"* → issue đã kiểm chứng được tạo, merge PR → log trạng thái/giờ |
| [`redmine-planning`](./skills/redmine-planning/README.md) | 💻 Dev | *"chia nhỏ story này"* → task đã estimate, gán người, có phụ thuộc |
| [`redmine-daily-report`](./skills/redmine-daily-report/README.md) | 💻 Dev | *"báo cáo ngày"* → tổng hợp hôm qua bản business + bản kỹ thuật |
| [`boss-project-oversight`](./skills/boss-project-oversight/README.md) | 👔 Sếp | *"hiệu suất tuần này của An"* → widget tương tác theo dự án (chỉ đọc, key admin) |
| [`testcase-generation`](./skills/testcase-generation/README.md) | 🧪 Tester | *"test case cho story này"* → case đã duyệt được ghi vào Sheets |
| [`bug-reporting`](./skills/bug-reporting/README.md) | 🧪 Tester | *"log bug này"* → dòng bug có ID tự tăng trên Sheets |
| [`bug-to-redmine`](./skills/bug-to-redmine/README.md) | 🧪 Tester | *"đẩy bug sang Redmine"* → issue được tạo, ID ghi ngược lại |
| [`status-sync`](./skills/status-sync/README.md) | 🧪 Tester | *"dev fix xong chưa?"* → trạng thái sheet đồng bộ từ Redmine |
| [`reopen-bug`](./skills/reopen-bug/README.md) | 🧪 Tester | *"mở lại BUG-001"* → issue mở lại đúng workflow, sheet cập nhật |

### Cho người dùng Claude Desktop (tester & sếp: không cần repo)

Claude Desktop nhập skill dưới dạng file ZIP — lý tưởng khi bạn không làm việc trong repository. Build ZIP bằng:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1
```

Rồi **Settings → Customize → Skills → Add Skill → Upload ZIP** (lặp lại cho mỗi skill):

| ZIP | Làn |
|---|---|
| `redmine-init` | 💻 Dev khởi đầu |
| `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug` | 🧪 Tester |
| `boss-project-oversight` | 👔 Sếp |

### Cài user-level (opencode global / ChatGPT desktop)

Nên dùng cách này khi bạn muốn skill **ở mọi nơi**, không chỉ một repo — opencode và app desktop ChatGPT đều tự quét `%USERPROFILE%\.agents\skills\`. Đây là đường dễ nhất cho 🧪 tester và 👔 sếp làm việc trong app desktop (opencode, Codex, ChatGPT) mà không dính tới repository:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex
```

Lệnh này cài 7 skill (`redmine-init`, `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug`, `boss-project-oversight`) kèm file mẫu (trừ `README.md`). Chạy lại mà dính giới hạn GitHub rate limit? Đặt `$env:GITHUB_TOKEN = "<your_pat>"` trước (`public_repo` scope là đủ). Gỡ cài đặt: `Remove-Item -Recurse -Force $env:USERPROFILE\.agents\skills`.

## 🎬 Video hướng dẫn (tester & sếp)

Video walkthrough ngắn — xem trước rồi làm theo các bước trên. (Link sẽ đăng tại đây khi quay xong; mỗi dòng giữ placeholder cho tới lúc đó.)

| Làn | Video | Link |
|---|---|---|
| 🧪 Tester | Setup: app desktop + kết nối server + cài skill QA | *coming soon* <!-- VIDEO-TESTER-SETUP: replace with https://... --> |
| 🧪 Tester | Usage: chạy end-to-end đầu tiên (story → test case → bug → Redmine) | *coming soon* <!-- VIDEO-TESTER-USAGE: replace with https://... --> |
| 👔 Sếp | Setup: app desktop + kết nối chỉ đọc + skill giám sát | *coming soon* <!-- VIDEO-BOSS-SETUP: replace with https://... --> |
| 👔 Sếp | Usage: danh sách nhân viên → chọn một người → widget hiệu suất ngày/tuần | *coming soon* <!-- VIDEO-BOSS-USAGE: replace with https://... --> |

## Bên trong hoạt động thế nào

Server phơi **39 MCP tool** để skill gọi thay bạn: issue (tạo/liệt kê/cập nhật/liên kết), time entries, trang wiki, nhân sự & tổng hợp hiệu suất, tìm kiếm toàn cục, cùng tool Google Sheets và memory. Xem [MCP Tools](./docs/mcp-tools.md) và [Tool Reference](./docs/tool-reference.md).

| Chế độ auth | Khi nào dùng |
|---|---|
| `legacy` (mặc định) | Một user / credential chung — một API key trong `.env` |
| `oauth` | Đăng nhập theo từng user, Redmine 6.1+ — xem [OAuth Setup](./docs/oauth-setup.md) |
| `dynamic` | Multi-tenant / VPS chung — agent gửi `X-Redmine-URL` + `X-Redmine-API-Key` theo từng request |

Đặt bằng `REDMINE_AUTH_MODE=legacy|oauth|dynamic`. Triển khai public: ưu tiên `oauth`/`dynamic`; máy của sếp: thêm `REDMINE_MCP_READ_ONLY=true`.

## Docs

- [MCP Tools](./docs/mcp-tools.md) — mọi tool và MCP resource
- [Tool Reference](./docs/tool-reference.md) — tham chiếu chi tiết tham số
- [Docker & VPS deployment](./docs/docker-deployment.md) — chi tiết Docker local, VPS tăng cường + HTTPS
- [Claude Desktop setup](./docs/claude-desktop-setup.md) — MCP + skill trên Claude Desktop
- [OAuth Setup](./docs/oauth-setup.md) — OAuth2 theo từng user (Redmine 6.1+)
- [Troubleshooting](./docs/troubleshooting.md) — lỗi thường gặp
- [Contributing](./docs/contributing.md) — setup phát triển
- [Changelog](./CHANGELOG.md)

## License

MIT — xem [LICENSE](./LICENSE).
