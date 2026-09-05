> Vendored from `../testcase-generation/USER_STORY_TEMPLATE.md` — the original is the single source of truth. When the original changes, copy it over this file.
>

# User Story Template (for UI Black-Box Test Case Generation)

A well-defined User Story (US) template that gives enough information for the `testcase-generation` skill to create test cases without guessing business logic.

**Scope assumption (read first):** the tester tests **only on the UI** (black-box, no API testing, no backend access). Every Acceptance Criterion, step, and expected result must describe something **observable on screen**. Anything that can only be verified via API, database, logs, or code is out of scope unless stated otherwise.

**Project blindness assumption:** when generating test cases, the AI only sees the single US in front of it — it knows nothing about your project or its modules. Section 0 (Project Context) exists to fix exactly that: fill it **once per project**, then every US reuses it.

---

## 0. Project Context (fill ONCE per project, reuse for every US)

```markdown
# Project Context: <App Name>

## App overview
- What the app does (1-2 sentences): <e.g. "Internal chatbot that answers course questions for students">
- Platform: <e.g. "Web app (Chrome, desktop-first)" / "Mobile web">
- Environments:
  - Test env URL: <e.g. "https://test.example.com">
  - Test accounts live in: <e.g. "shared sheet / password manager — ask QA lead">

## Module / Screen catalog
| Module | Screens (exact names as shown on UI) | Purpose |
|--------|--------------------------------------|---------|
| Auth | Login, Register, Forgot Password | Sign in / sign up / recover access |
| Chat | Conversation list, Chat window, Settings | Talk to chatbot, manage sessions |
| <Module> | <Screen 1, Screen 2> | <what the user does here> |

## Roles & test accounts
| Role | Test account | Notes |
|------|--------------|-------|
| Student (fresh, no history) | <account> | Never shared personal info before |
| Student (with history) | <account> | Has prior conversations |
| Admin | <account> | Can access admin panel |

## UI conventions (whole app)
- Language(s) shown on UI: <e.g. "Vietnamese primary, some English labels">
- Common elements: <e.g. "toast bottom-right, 3s auto-dismiss; primary buttons blue">
- Known quirks: <e.g. "chat streams text word-by-word; history loads after ~1s">
```

> If this section is missing when generation starts, the agent asks for it **once**, then reuses it for all later USs of the same project — it never asks twice.

---

## Template (one block per US)

```markdown
# US-XXX: <Title>
**Module**: <name exactly as in the Module / Screen catalog (§0)>

## User Story
**As a** [specific role — must match a role in Project Context]
**I want** [capability — what the user does, in UI terms]
**So that** [real business value — why it matters]

## UI Map
- Screens involved: [exact screen names from the catalog, in visit order]
- Elements used (quote exact on-screen labels):
  - Screen A: button "<Label>", input "<Label>", link "<Label>"
  - Screen B: ...
- Navigation:
  - Entry: how the user reaches the first screen (e.g. "login → click Chat icon in sidebar")
  - Exit: where the user ends up (e.g. "stays on Chat window" / "redirected to Login")

## Acceptance Criteria
Each AC is a pass/fail check written in **Given/When/Then with UI-observable outcomes**.
Rules: max ~5 ACs. At least one happy path AND at least one negative case.

- [ ] **AC1**: <happy path — Given screen/state, When user action, Then what is SEEN on screen>
- [ ] **AC2**: <negative case 1 — invalid input: what error is SHOWN, where>
- [ ] **AC3**: <negative case 2 — empty/boundary: what is SHOWN or DISABLED>
- [ ] **AC4**: <business rule — what MUST be visible/true for acceptance (detail it in Business Rules below, don't repeat here)>
- [ ] **AC5**: <state-dependent — name the starting state; detail states/transitions in State / Lifecycle below, don't repeat here>

## Business Rules (only rules visible or enforceable on the UI)
- Rule 1: <e.g. "Login button stays disabled until both fields are non-empty">
- Rule 2: <e.g. "Error text appears below the field, red, and stays until next submit">
- Rule 3: <e.g. "After 5 failed logins, the account locks and the UI shows a lock message with remaining time">

## Preconditions (setup the tester can do through the UI or test accounts)
- Starting screen: <e.g. "Login page, logged out">
- Role/account: <e.g. "fresh student account from Project Context">
- Data state described by what the user sees: <e.g. "conversation list is empty">

## Test Data
- Valid: <example valid inputs and what the screen shows after>
- Invalid: <example invalid inputs and the exact error text shown>
- Boundary: <min/max, empty, whitespace-only, very long strings — with visible outcomes>

## Out of Scope
- What this story deliberately does NOT cover:
  - <feature X>
  - <backend/API-only behavior — e.g. response times, hashing, retry logic>
  - <integration Y beyond what the UI shows>

## Non-Functional Requirements (only what is observable on the UI)
- Performance (client-side): <e.g. "Login page displays fully within 3s on normal network">
- Security (visible): <e.g. "Password field masks input; logged-out user opening /dashboard URL is redirected to Login">
- Reliability (visible): <e.g. "If sending a message fails, an inline error with a Retry button appears">
- Accessibility: <e.g. "Form is fully usable by keyboard; error text is readable (not color-only)">
- Localization: <e.g. "All labels in Vietnamese; dates shown as dd/mm/yyyy">

## State / Lifecycle (described by what the user SEES, not backend flags)
- Entities with visible states: <e.g. Account, Conversation>
- States and how the user recognizes them:
  - Account: normal (can log in) → locked (login shows lock message with countdown)
  - Conversation: active (input box enabled) → ended (input box replaced by "New chat" button)
- Transition rules in user terms:
  - Account locks after 5 failed logins within 5 minutes; unlocks automatically after 15 minutes.

## Dependencies & Integration (ONLY effects the user can see + setup impact)
- Internal (visible effect):
  - <e.g. "After registration, a welcome email arrives within ~5 minutes — tester needs mailbox access">
- External (visible effect):
  - <e.g. "Login with Google button opens Google consent screen in a popup">
- Setup impact:
  - <e.g. "Needs a mailbox the tester can open; needs a Google test account">
- Explicitly NOT covered here: API contracts, status codes, timeouts, retries, webhooks — anything invisible on the UI.

## Notes & Assumptions
- Assumption 1: <e.g. "Test env is up; test accounts from Project Context work">
- Assumption 2: <e.g. "Tester uses Chrome desktop, normal network">
- Open questions: [?] <any unclear business points>
```

---

## Why each section matters for QA

| Section | What testers extract |
|---------|---------------------|
| Project Context (§0) | Which app/module/screen anything belongs to — cures project blindness |
| User Story | Test scenarios — what the user does and why |
| UI Map | Exact screens, element labels, navigation → executable steps without guessing names |
| Acceptance Criteria | **Direct mapping to test cases** — each AC → at least 1 test case |
| Business Rules | Negative test cases, permission tests, validation tests (UI-visible only) |
| Preconditions | Setup steps for each test case (doable via UI or test accounts) |
| Test Data | Concrete inputs + exact visible outputs for test cases |
| Out of Scope | Boundary — don't write tests for these |
| NFR (observable) | Client-side performance, visible security, keyboard/a11y, locale checks |
| State / Lifecycle | State-transition test cases in user terms |
| Dependencies (visible) | Setup needs (mailbox, third-party account) + visible-effect checks |
| Notes & Assumptions | Edge cases to consider, things to verify with the user |

---

## Validation checklist (what `testcase-generation` checks)

The agent reads the US file and **validates these fields**. Missing → ask the user. After validation, the agent runs a **technique analysis** (Step 2.75) to determine which test design techniques (EP, BVA, Decision Table, State Transition, Error Guessing, Pairwise, Use Case) apply to this US.

### Must have (block generation if missing):
- [ ] **Title** — short, descriptive
- [ ] **User Story** — As a / I want / So that (role must exist in Project Context)
- [ ] **Acceptance Criteria** — at least 1 happy path + at least 1 negative case, ideally 3-5 total, all UI-observable
- [ ] **Module/Feature** — must match the Module / Screen catalog (§0)
- [ ] **UI Map** — screens + exact element labels + entry/exit navigation

### Should have (ask if missing):
- [ ] **Project Context (§0)** — ask ONCE per project, then reuse (never ask twice)
- [ ] **Business Rules** — any non-obvious constraints (UI-visible only)
- [ ] **Preconditions** — what must be true before (achievable via UI/test accounts)
- [ ] **Test Data examples** — concrete valid/invalid inputs with exact visible outputs
- [ ] **Out of Scope** — to avoid writing unnecessary tests

### Nice to have (skip if missing):
- [ ] **NFR (observable)** — client-side performance, visible security, a11y, locale
- [ ] **State / Lifecycle** — if the feature has user-visible states
- [ ] **Dependencies (visible effects)** — only if setup or visible effects are involved
- [ ] **Notes & Assumptions** — edge cases to consider

---

## Questions the agent should ask when info is missing

If the US file lacks info, the agent asks these **specific questions** (one batch), in Vietnamese or English depending on user language:

### 0. Project Context missing (ask once per project, then reuse forever)
> "Mình chưa có Project Context của project này. Cho mình biết: (1) app làm gì, link test env; (2) danh sách modules/màn hình (tên đúng như trên UI); (3) các vai trò + tài khoản test; (4) quy ước UI chung. Điền 1 lần này, các US sau mình tự tái dùng, không hỏi lại."

### 1. Module/Feature missing or not in catalog
> "US này thuộc module nào trong catalog? (e.g. Login, Chat, Settings...) Nếu là module mới, cho mình biết nó gồm những màn hình nào."

### 2. UI Map missing
> "Cho mình UI Map: (1) các màn hình đi qua theo thứ tự; (2) tên nút/ô/link ĐÚNG như hiển thị trên UI (copy label thật); (3) vào từ đâu, xong ở đâu. Không có cái này mình sẽ phải bịa tên element — sai hết steps."

### 3. Acceptance Criteria missing, vague, or not UI-observable
> "Acceptance criteria đang <thiếu/mơ hồ/không kiểm chứng được trên UI>. Bạn có thể:
> - Mô tả flow chính + case lỗi bằng ngôn ngữ nhìn thấy được (vd: 'hiển thị lỗi X dưới ô email' thay vì 'trả về 400')
> - Hoặc paste thêm spec/requirements
> - Hoặc để mình viết nháp từ As a/I want/So that (đánh dấu DRAFT chưa verify — bạn phải duyệt từng AC trước khi generate, mình không dùng nháp chưa duyệt để sinh TC)"

### 4. Negative cases missing
> "US chưa có negative case nào. Thêm ít nhất 1 nhé (vd: nhập sai, bỏ trống, quá giới hạn → màn hình phải hiện gì?). Nếu thật sự không có, nói mình biết để mình không tự bịa."

### 5. Business Rules missing
> "Có business rule nào đặc biệt không? (e.g. 'nút disable đến khi...', 'khóa tài khoản sau...', 'hiển thị lỗi...').
> Chỉ lấy rule nhìn thấy/bị ép được trên UI — logic backend/API thì bỏ qua (out of scope).
> Nếu không có, mình sẽ không viết test case phân quyền/validation."

### 6. Preconditions missing
> "Trước khi test cần setup gì làm được bằng UI/tài khoản test? (e.g. 'đăng xuất trước', 'dùng tài khoản fresh', 'danh sách trống')"

### 7. Test Data — synthesize from AC, don't ask

Test data is **derived from AC/Business Rules**, not asked. Generate standard valid/invalid variants (e.g. `user@example.com`, `Password123!`, empty, special chars) with exact visible outcomes. Only ask if US references a specific value (e.g. "use account ID 12345").

### 8. Out of Scope unclear
> "Cái gì KHÔNG thuộc story này? (e.g. 'không gồm đăng nhập Google', 'không test API/timeout backend')
> Nếu chưa rõ, mình mặc định phạm vi hẹp: UI-only, chỉ test các AC, không mở rộng."

### 9. External dependency with visible effect or setup need
> "Story này có dính service bên ngoài mà user thấy được hoặc tester phải chuẩn bị không? (e.g. 'cần mở được mailbox', 'cần tài khoản Google test', 'email đến trong X phút')
> Nếu có, mình thêm test case hiệu ứng visible + ghi setup vào Preconditions. Phần hợp đồng API/timeout/retry thì out of scope."

---

## What the agent MUST NOT do (anti-patterns)

These are the "don't auto-assume" rules. If the agent does any of these, it's making business decisions it shouldn't:

1. **Don't auto-define business rules** — if US doesn't say "login button stays disabled", don't write test for that
2. **Don't auto-define edge cases** — if US doesn't say "handle timeout", don't add timeout test
3. **Don't auto-define validation rules** — if US doesn't specify email format, don't assume
4. **Don't auto-define workflows** — if US doesn't say "send email after save", don't add that step
5. **Don't auto-define priority** — if US doesn't say "performance critical", don't add perf tests
6. **Don't auto-define UI details** — if US doesn't mention a Cancel button, don't test for it; never invent element labels — ask (Question 2)
7. **Don't test what isn't observable on the UI** — no API status codes, response times, hashing, DB flags, logs, retries, webhooks. If it can't be seen on screen, it needs an explicit US statement to become a test case.

---

## Example: A well-defined US (UI-only)

```markdown
# US-042: User Login with Email
**Module**: Auth

## User Story
**As a** registered student
**I want** to log in with my email and password
**So that** I can access my personal dashboard

## UI Map
- Screens: Login → Dashboard (on success) / stays on Login (on failure)
- Elements:
  - Login: input "Email", input "Mật khẩu", button "Đăng nhập", link "Quên mật khẩu?", error area below each field, toast top-right
  - Dashboard: greeting "Xin chào, <tên>", sidebar icon "Chat"
- Navigation:
  - Entry: open test env URL while logged out → lands on Login
  - Exit success: Dashboard. Exit failure: stays on Login.

## Acceptance Criteria
- [ ] **AC1**: Given logged-out Login screen, when entering valid email + valid password and clicking "Đăng nhập", then Dashboard appears with greeting "Xin chào, <tên>" and a success toast
- [ ] **AC2**: Given Login screen, when entering badly-shaped email (e.g. "user@") and clicking "Đăng nhập", then error "Email không đúng định dạng" appears below the Email field, user stays on Login
- [ ] **AC3**: Given Login screen, when entering valid email + wrong password and clicking "Đăng nhập", then error "Email hoặc mật khẩu chưa đúng" appears, password field is cleared, user stays on Login
- [ ] **AC4**: Given Login screen with empty Email or empty Password, then button "Đăng nhập" is disabled and cannot be clicked
- [ ] **AC5**: Given 5 failed logins within 5 minutes, then the account locks: Login shows "Tài khoản tạm khóa, thử lại sau 15:00" with a live countdown; after countdown ends, login works again with correct credentials

## Business Rules
- Rule 1: Button "Đăng nhập" stays disabled until both fields are non-empty (whitespace-only counts as empty)
- Rule 2: Error text appears below the field, red, and stays until the next submit
- Rule 3: Lock message shows a live mm:ss countdown; login attempts during lock keep showing the lock message
- Rule 4: Email match is case-insensitive ("User@Example.com" works like "user@example.com")
- Rule 5: Disabled accounts cannot log in — Login shows "Tài khoản đã bị vô hiệu hóa, liên hệ quản trị viên"

## Preconditions
- Starting screen: Login page, logged out (clear session / incognito)
- Accounts: valid student account + a fresh student account (from Project Context)
- Network: normal connection, test env reachable

## Test Data
- Valid email: "user@example.com" → Dashboard + greeting
- Invalid email shape: "user@", "user.example.com", "user@.com" → error "Email không đúng định dạng" below field
- Valid password: "Password123!" → success
- Wrong password: "WrongPassword" → error "Email hoặc mật khẩu chưa đúng", password cleared
- Empty/whitespace: "" or "   " → button "Đăng nhập" disabled

## Out of Scope
- Social login (Google, Facebook)
- 2FA / OTP
- Remember me checkbox
- Password reset flow
- API response times, password hashing, session token internals

## Non-Functional Requirements (observable on UI)
- Performance: Login page displays fully within 3s on normal network
- Security (visible): password input masks characters; opening /dashboard URL while logged out redirects to Login
- Accessibility: form fully usable by keyboard; errors are text (not color-only)
- Localization: labels in Vietnamese; dates as dd/mm/yyyy

## State / Lifecycle (user-visible)
- Account: normal (can log in) → locked (lock message + countdown) → normal again after countdown
- Transition: 5 failed logins within 5 minutes trigger the lock; correct login after countdown succeeds

## Dependencies & Integration (visible effects only)
- None for this story (no mailbox, no third-party login involved)

## Notes & Assumptions
- Assumption: test env is up; test accounts from Project Context work
- Assumption: Chrome desktop, normal network
- [?] Open: should the error distinguish "wrong password" vs "email not found"? Security trade-off — confirm with PO.
```

From this US, the agent can extract:
- **4-5 happy path test cases** (AC1) — Use Case testing
- **2-3 invalid input test cases** (AC2, AC3, AC4) — Equivalence Partitioning
- **1-2 security/edge test cases** (AC5) — Error Guessing + BVA
- **Permission test cases** (Business Rule 5) — Decision Table
- **Validation test cases** (Business Rule 1, 2, 4) — EP + BVA

Total: ~10-15 test cases, all traceable to specific ACs or Business Rules, each backed by a systematic test design technique. Every step names real screens and exact on-screen labels — no invented element names, nothing verified below the UI.
```
