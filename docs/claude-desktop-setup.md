# Claude Desktop Integration

Hướng dẫn kết nối Claude Desktop với Redmine MCP Server (đã deploy sẵn).

## Yêu cầu

| Thành phần | Phiên bản tối thiểu | Kiểm tra |
|------------|---------------------|----------|
| **Node.js** | v18+ | `node --version` |
| **npx** |随 Node.js | `npx --version` |
| **Claude Desktop** | Windows Store hoặc官网 | Mở app kiểm tra |

### Cài đặt Node.js (nếu chưa có)

Tải từ https://nodejs.org/ → chọn **LTS** → cài đặt mặc định.

### Lấy Redmine API Key

1. Đăng nhập vào Redmine của bạn
2. Vào **My account** → **API access key** → **Show**
3. Copy key đó (dùng cho bước cấu hình bên dưới)

> **Lưu ý**: Mỗi user có API key riêng. Không share key của bạn với người khác.

---

## Bước 1: Tìm file config

### Cách 1: Từ UI (khuyến nghị)

1. Mở Claude Desktop
2. Vào **Settings** (biểu tượng ⚙️) → **Developer** (hoặc **Advanced**)
3. Nhấn **Edit Config** → file `claude_desktop_config.json` sẽ mở trong editor

### Cách 2: Truy cập thủ công

File config nằm tại:

```
C:\Users\<username>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
```

---

## Bước 2: Thêm MCP Server

Mở file `claude_desktop_config.json` và thêm nội dung sau vào object `mcpServers`:

```json
{
  "mcpServers": {
    "redmine": {
      "command": "C:\\Program Files\\nodejs\\npx.cmd",
      "args": [
        "-y",
        "mcp-remote",
        "http://127.0.0.1:8000/mcp",
        "--transport",
        "http-only",
        "--header",
        "X-Redmine-URL:https://redmine.example.com",
        "--header",
        "X-Redmine-API-Key:YOUR_PERSONAL_API_KEY"
      ]
    }
  }
}
```

**Thay thế:**

| Placeholder | Giá trị |
|-------------|---------|
| `https://redmine.example.com` | URL Redmine của công ty bạn |
| `YOUR_PERSONAL_API_KEY` | API Key lấy từ bước "Lấy Redmine API Key" ở trên |

---

## Bước 3: Verify

1. **Restart Claude Desktop** hoàn toàn (right-click tray → Exit → mở lại)
2. Hỏi Claude: **"List all your available MCP tools"**
3. Nếu thấy **37 tools** (list_redmine_projects, create_redmine_issue, ...) → OK
4. Thử gọi 1 tool: **"List all Redmine projects"**

---

## Troubleshooting

### Claude Desktop không thấy tools

1. **Kiểm tra config**: Mở lại `claude_desktop_config.json` → đảm bảo JSON hợp lệ
2. **Restart hoàn toàn**: Right-click tray icon → **Exit** → đợi 5s → mở lại
3. **Kiểm tra log**: Xem `C:\Users\<username>\AppData\Local\Claude\logs\main.log`

### Tools hiện nhưng fail khi gọi

1. **Kiểm tra server**: Mở browser truy cập `http://127.0.0.1:8000/health` → phải thấy `{"status":"healthy"}`
2. **Kiểm tra header**: Đảm bảo `X-Redmine-URL` và `X-Redmine-API-Key` đúng
3. **Kiểm tra log server**: Liên hệ admin server xem log

### Lỗi "No Redmine authentication available"

- Header không được gửi hoặc sai format
- Kiểm tra lại `--header` trong config, đảm bảo đúng format: `Header-Name:value`

### npx không tìm thấy

- Kiểm tra path: `where npx`
- Nếu dùng nvm hoặc cài Node.js ở ổ khác, cập nhật `command` trong config

---

## Bước 4: Import Skills (QA testers)

Nếu bạn là tester và muốn dùng QA skills (testcase-generation, bug-reporting, ...):

1. Tải ZIP files từ: `dist/claude-desktop-skills/`
2. Mở Claude Desktop → **Settings** → **Customize** → **Skills**
3. Nhấn **Add Skill** → **Upload ZIP file**
4. Chọn skill ZIP cần import (ví dụ: `testcase-generation.zip`)
5. Repeat cho các skill khác

**Danh sách skills:**

| Skill | Mô tả |
|-------|-------|
| `testcase-generation` | Tạo test case từ user story |
| `bug-reporting` | Ghi bug lên Google Sheet |
| `bug-to-redmine` | Tạo Redmine issue từ bug trên sheet |
| `status-sync` | Đồng bộ trạng thái Redmine → Sheet |
| `reopen-bug` | Mở lại bug đã fix |
| `redmine-init` | Khởi tạo project mapping |
| `redmine-daily-report` | Báo cáo daily |
| `redmine-issue-workflow` | Workflow issue |
| `redmine-planning` | Lập kế hoạch |

---

## Tham khảo

- [Tool Reference](./tool-reference.md) - Danh sách chi tiết tất cả tools
- [Troubleshooting](./troubleshooting.md) - Các lỗi thường gặp
