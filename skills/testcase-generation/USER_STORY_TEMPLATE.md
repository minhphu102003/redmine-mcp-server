# User Story Template (for QA Test Case Generation)

A well-defined User Story (US) template that gives enough information for the `testcase-generation` skill to create test cases without guessing business logic.

---

## Template

```markdown
# US-XXX: <Title>

## User Story
**As a** [specific role — not "a user" or "the system"]
**I want** [capability — what the user does]
**So that** [real business value — why it matters]

## Context
- Background: [why this story is needed now, what problem it solves]
- Affected users: [which personas, how many]
- Affected modules/screens: [which UI pages, APIs, services]

## Acceptance Criteria
Each AC is a pass/fail check — covers happy path + important edge cases.

- [ ] **AC1**: <Given/When/Then or simple statement> — happy path
- [ ] **AC2**: <edge case 1 — invalid input, authz, etc.>
- [ ] **AC3**: <edge case 2 — boundary values, error handling>
- [ ] **AC4**: <business rule — what MUST be true for acceptance>
- [ ] **AC5**: <state-dependent — if behavior depends on starting state>

## Business Rules
- Rule 1: <e.g. "Only Admin role can delete">
- Rule 2: <e.g. "Email format must be RFC 5322 compliant">
- Rule 3: <e.g. "Discount only applies if cart total > $100">

## Preconditions
- What must be true before the user can do this action:
  - User must be logged in
  - User must have <role>
  - Data state: <e.g. "At least one item in cart">

## Test Data
- Valid: <example valid inputs and expected outputs>
- Invalid: <example invalid inputs and expected error messages>
- Boundary: <min/max, empty, null, very long strings>

## Out of Scope
- What this story deliberately does NOT cover:
  - <feature X>
  - <integration with Y>

## Notes & Assumptions
- Assumption 1: <e.g. "Email service is up and responsive">
- Assumption 2: <e.g. "User locale is en-US">
- Open questions: [?] <any unclear business points>
```

---

## Why each section matters for QA

| Section | What testers extract |
|---------|---------------------|
| User Story | Test scenarios — what the user does and why |
| Context | Test environment setup, which modules to focus on |
| Acceptance Criteria | **Direct mapping to test cases** — each AC → at least 1 test case |
| Business Rules | Negative test cases, permission tests, validation tests |
| Preconditions | Setup steps for each test case |
| Test Data | Concrete inputs/expected outputs for test cases |
| Out of Scope | Boundary — don't write tests for these |
| Notes & Assumptions | Edge cases to consider, things to verify with the user |

---

## Validation checklist (what `testcase-generation` checks)

The agent reads the US file and **validates these fields**. Missing → ask the user. After validation, the agent runs a **technique analysis** (Step 2.75) to determine which test design techniques (EP, BVA, Decision Table, State Transition, Error Guessing, Pairwise, Use Case) apply to this US.

### Must have (block generation if missing):
- [ ] **Title** — short, descriptive
- [ ] **User Story** — As a / I want / So that
- [ ] **Acceptance Criteria** — at least 1, ideally 3-5
- [ ] **Module/Feature** — which part of the system

### Should have (ask if missing):
- [ ] **Business Rules** — any non-obvious constraints
- [ ] **Preconditions** — what must be true before
- [ ] **Test Data examples** — concrete valid/invalid inputs
- [ ] **Out of Scope** — to avoid writing unnecessary tests

### Nice to have (skip if missing):
- [ ] **Context** — extra background
- [ ] **Notes & Assumptions** — edge cases to consider

---

## Questions the agent should ask when info is missing

If the US file lacks info, the agent asks these **specific questions** (one batch), in Vietnamese or English depending on user language:

### 1. Module/Feature missing
> "Which module/feature does this US belong to? (e.g. Login, Payment, User Profile...)"

### 2. Acceptance Criteria missing or too vague
> "Acceptance criteria are <missing/vague>. You can:
> - Describe the main flows (happy path) and edge cases (invalid input, authz, errors)
> - Or paste additional spec/requirements
> - Or I'll create a draft based on As a/I want/So that, you review later"

### 3. Business Rules missing
> "Any special business rules? (e.g. 'only Admin can delete', 'discount only applies when...', 'email format must...')
> If none, I won't write test cases for permissions/validation."

### 4. Preconditions missing
> "What conditions must be true before the user can do this action? (e.g. 'logged in', 'has item in cart', 'role = X')"

### 5. Test Data — synthesize from AC, don't ask

Test data is **derived from AC/Business Rules**, not asked. Generate standard valid/invalid variants (e.g. `user@example.com`, `Password123!`, empty, special chars). Only ask if US references a specific value (e.g. "use account ID 12345").

### 6. Out of Scope unclear
> "What is NOT part of this story? (e.g. 'doesn't include social login', 'doesn't handle timeout')
> If unclear, I'll assume narrow scope — only test the ACs, no expansion."

### 7. Edge cases unclear
> "Do you need test cases for special edge cases? (e.g. concurrent access, large data, special characters in input, offline mode)
> If unclear, I'll add standard edge cases (empty, boundary, special chars) for this module."

### 8. Integration concerns
> "Does this story involve external services/APIs? (e.g. 'call payment gateway', 'integrate email service')
> If yes, I'll create test cases for happy path + error handling (timeout, 500, etc.)"

---

## What the agent MUST NOT do (anti-patterns)

These are the "don't auto-assume" rules. If the agent does any of these, it's making business decisions it shouldn't:

1. **Don't auto-define business rules** — if US doesn't say "only Admin can delete", don't write test for that
2. **Don't auto-define edge cases** — if US doesn't say "handle timeout", don't add timeout test
3. **Don't auto-define validation rules** — if US doesn't specify email format, don't assume
4. **Don't auto-define workflows** — if US doesn't say "send email after save", don't add that step
5. **Don't auto-define priority** — if US doesn't say "performance critical", don't add perf tests
6. **Don't auto-define UI details** — if US doesn't mention a Cancel button, don't test for it

---

## Example: A well-defined US

```markdown
# US-042: User Login with Email

## User Story
**As a** registered user
**I want** to log in with my email and password
**So that** I can access my personal dashboard

## Context
- Background: Currently users can only register but not log in. Need login to access dashboard.
- Affected users: All registered users (~5000)
- Affected modules: Login page, Auth API, Dashboard redirect

## Acceptance Criteria
- [ ] **AC1**: Valid email + valid password → redirect to dashboard, show success toast
- [ ] **AC2**: Invalid email format → show error "Invalid email format", no API call
- [ ] **AC3**: Valid email + wrong password → show error "Email or password is incorrect", password field cleared
- [ ] **AC4**: Empty email or password → show error "Please fill in all fields", submit button disabled
- [ ] **AC5**: 5 failed attempts in 5 minutes → account locked for 15 minutes, show error

## Business Rules
- Rule 1: Email must match RFC 5322 format
- Rule 2: Password must be hashed with bcrypt before API call
- Rule 3: Session token expires after 24 hours
- Rule 4: Login is case-insensitive for email
- Rule 5: User cannot login if account is disabled (is_active = false)

## Preconditions
- User must be registered (exists in DB)
- User account must be active (is_active = true)
- Network connection available

## Test Data
- Valid email: "user@example.com"
- Invalid email format: "user@", "user.example.com", "user@.com"
- Valid password: "Password123!"
- Wrong password: "WrongPassword"
- Empty: "" or "  " (whitespace only)

## Out of Scope
- Social login (Google, Facebook)
- 2FA / OTP
- Remember me functionality
- Password reset flow

## Notes & Assumptions
- Assumption: Backend auth service is up and responding
- Assumption: Email service is available for "forgot password" link in error message
- [?] Open: Should we show specific error ("wrong password" vs "email not found")? Security trade-off.
```

From this US, the agent can extract:
- **4-5 happy path test cases** (AC1) — Use Case testing
- **2-3 invalid input test cases** (AC2, AC3, AC4) — Equivalence Partitioning
- **1-2 security/edge test cases** (AC5) — Error Guessing + BVA
- **Permission test cases** (Business Rule 5) — Decision Table
- **Validation test cases** (Business Rule 1, 4) — EP + BVA

Total: ~10-15 test cases, all traceable to specific ACs or Business Rules, each backed by a systematic test design technique.
