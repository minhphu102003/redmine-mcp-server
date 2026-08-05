# AI Agent CLI Integrations

Hướng dẫn kết nối Redmine MCP Server với các AI agent CLI. Mỗi CLI là một mục nhỏ trong file này.

| CLI | Hướng dẫn | Trạng thái |
|-----|-----------|------------|
| **Grok CLI** | [bên dưới](#grok-cli) | Sẵn sàng |
| **opencode** | [bên dưới](#opencode) | Sẵn sàng |

---

## Grok CLI

Kết nối Grok (xAI) với Redmine MCP Server qua giao thức HTTP MCP.

### Yêu cầu

- Grok CLI đã cài đặt và đăng nhập: `grok --version`
- Redmine MCP Server đang chạy (mặc định tại `http://127.0.0.1:8000`)
- Xác định auth mode của server (`REDMINE_AUTH_MODE`) để biết cần header nào:

| Auth mode | Header cần thiết |
|-----------|------------------|
| `dynamic` (khuyến nghị) | `X-Redmine-URL` + `X-Redmine-API-Key` — **bắt buộc** |
| `legacy` | Không cần header |
| `oauth` | Grok tự mở browser flow khi lần đầu sử dụng |

### Cách nhanh (CLI)

```bash
grok mcp add redmine --transport http http://127.0.0.1:8000/mcp \
  -H "X-Redmine-URL: https://redmine.example.com" \
  -H "X-Redmine-API-Key: YOUR_PERSONAL_API_KEY"
```

Lệnh này ghi vào `~/.grok/config.toml` (phạm vi user, dùng được ở mọi project). Muốn giới hạn trong project hiện tại, thêm `-s project` (ghi vào `.grok/config.toml` trong thư mục dự án).

### Cách thủ công (TOML)

Sửa `~/.grok/config.toml` (hoặc `.grok/config.toml` nếu dùng `-s project`):

```toml
[mcp_servers.redmine]
url = "http://127.0.0.1:8000/mcp"
enabled = true

[mcp_servers.redmine.headers]
X-Redmine-URL = "https://redmine.example.com"
X-Redmine-API-Key = "YOUR_PERSONAL_API_KEY"
```

### Xác minh

1. Kiểm tra server đã được load: `grok mcp list` và `grok inspect`
2. **Khởi động lại Grok** sau khi sửa config
3. Thử hỏi Grok: *"list redmine issues"* — nếu tool chạy được là thành công

### Troubleshooting

| Hiện tượng | Nguyên nhân | Xử lý |
|------------|-------------|-------|
| `401` trên `/.well-known/*` trong log server | Bước dò OAuth của Grok trước khi fallback sang headers | Bình thường, vô hại |
| `401` trên `POST /mcp` | Thiếu header, hoặc entry MCP cũ không có headers | Thêm `X-Redmine-URL` + `X-Redmine-API-Key`; xóa entry cũ bằng `grok mcp remove <tên>` |
| `POST /mcp 200` + `ListToolsRequest` | Kết nối thành công | Không cần làm gì |

> **Lưu ý:** Định dạng `{"servers": {...}}` (`"type": "http"`, `"url"`, `"headers"`) là định dạng của VS Code (`.vscode/mcp.json`), **không phải** định dạng Grok CLI. Grok CLI dùng TOML trong `~/.grok/config.toml` như trên.

---

## opencode

Kết nối opencode với Redmine MCP Server qua giao thức HTTP MCP.

### Yêu cầu

- Redmine MCP Server đang chạy (mặc định tại `http://127.0.0.1:8000`)
- Xác định auth mode của server (`REDMINE_AUTH_MODE`):

| Auth mode | Header cần thiết |
|-----------|------------------|
| `dynamic` (khuyến nghị) | `X-Redmine-URL` + `X-Redmine-API-Key` — **bắt buộc** |
| `legacy` | Không cần header |
| `oauth` | Thêm khối `oauth` (hoặc để opencode tự dò OAuth) |

### Cấu hình (global)

Mở/sửa `~/.config/opencode/opencode.json` (Windows: `C:\Users\<user>\.config\opencode\opencode.json`), thêm khối `mcp`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "redmine": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "X-Redmine-URL": "https://redmine.example.com",
        "X-Redmine-API-Key": "YOUR_PERSONAL_API_KEY"
      },
      "enabled": true
    }
  }
}
```

- **Global**: config trên áp dụng cho mọi project
- **Project**: đặt `opencode.json` (hoặc `.opencode/opencode.json`) ngay trong thư mục dự án — cấu hình project ghi đè global
- **Không lộ key trong git**: nếu project đẩy lên git, dùng biến môi trường thay cho key dạng literal: `"X-Redmine-API-Key": "{env:REDMINE_API_KEY}"`

### Xác minh

1. **Khởi động lại opencode** sau khi sửa config
2. Kiểm tra server xuất hiện (ví dụ `/mcp` hoặc thông báo MCP servers connected)
3. Thử hỏi: *"list redmine issues"* — nếu tool chạy được là thành công

### Troubleshooting

| Hiện tượng | Nguyên nhân | Xử lý |
|------------|-------------|-------|
| `401` trên `POST /mcp` | Thiếu header, hoặc `type` sai (`"http"` thay vì `"remote"`) | Kiểm tra lại khối `mcp` trong config: phải dùng `"type": "remote"` + đủ 2 header |
| Tool không xuất hiện sau khi sửa config | opencode không hot-reload config | Khởi động lại opencode |
