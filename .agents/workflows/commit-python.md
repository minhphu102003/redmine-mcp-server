---
description: Quy trình kiểm tra, tạo nhánh & Commit Code cho Python (uv)
---

# Quy trình tạo nhánh, kiểm tra & Push Code an toàn (Python)

Quy trình này áp dụng khi bạn đã code xong trên nhánh `dev` nhưng chưa commit, và muốn AI tự động sinh tên nhánh, check lỗi rồi đẩy lên.

1. **[AI THỰC HIỆN] Phân tích code sửa đổi:**
   - Trợ lý AI sẽ chạy `git status` và `git diff` để phân tích nội dung thay đổi.
   - AI tự động đề xuất tên nhánh chuẩn (`feat/`, `fix/`, `chore/`, `refactor/`).
   - Sinh ra Commit Message theo chuẩn Conventional Commits.
   - **AI báo cáo thông tin này để bạn xác nhận trước khi thực hiện.**

2. Chuyển sang nhánh mới (giữ lại các thay đổi chưa commit).
```bash
git checkout -b {TÊN_NHÁNH_AI_ĐỀ_XUẤT}
```

// turbo
3. Định dạng mã nguồn bằng Black.
```bash
uv run black .
```

// turbo
4. Kiểm tra lỗi cú pháp bằng Flake8.
```bash
uv run flake8 .
```

// turbo
5. Chạy bộ kiểm thử Pytest để đảm bảo không có lỗi logic. Nếu có lỗi sẽ dừng lại.
```bash
uv run pytest
```

6. Add, Commit và Push lên Repository.
```bash
git add .
git commit -m "{COMMIT_MESSAGE_AI_SINH_RA}"
git push -u origin {TÊN_NHÁNH_AI_ĐỀ_XUẤT}
```
