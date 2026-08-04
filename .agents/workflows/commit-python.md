# commit-python workflow

Mục tiêu: chuẩn hoá quy trình commit cho project Python, đảm bảo code sạch, test pass, message đúng convention (`feat:`, `fix:`, `chore:`...).

## 1) Chuẩn bị nhánh

```bash
git checkout -b feat/<ten-ngan-gon>
# hoặc fix/<ten-ngan-gon>, chore/<ten-ngan-gon>
```

## 2) Đồng bộ môi trường

```bash
uv sync
```

## 3) Chạy quality gate trước commit

```bash
uv run pytest
# nếu có lint/typecheck thì chạy thêm
# uv run ruff check .
# uv run mypy .
```

## 4) Kiểm tra thay đổi

```bash
git status
git diff
```

Checklist nhanh:
- Không commit `.env`, secret, file tạm
- Không có debug code thừa
- Test liên quan đã cập nhật

## 5) Commit theo convention

```bash
git add .
git commit -m "feat: <mo-ta-ngan-gon>"
```

Ví dụ:
- `feat: add answer question use case`
- `fix: handle empty knowledge base safely`
- `chore: reorganize app into clean architecture layers`

## 6) Push và tạo PR

```bash
git push -u origin <branch-name>
```

Sau đó mở Pull Request vào `main` (không push thẳng `main`).

## 7) Mẫu PR description

```md
## Summary
- ...

## Changes
- ...

## Verification
- [x] uv run pytest
- [ ] lint/typecheck (nếu có)

## Risks
- ...
```

## 8) Nếu cần amend commit

```bash
git add .
git commit --amend
git push --force-with-lease
```

> Chỉ dùng `--force-with-lease` trên nhánh feature của chính bạn.