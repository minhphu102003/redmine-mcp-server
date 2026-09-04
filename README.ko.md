# Redmine MCP Server

> 🌐 English: [README.md](./README.md) · Tiếng Việt: [README.vi.md](./README.vi.md)

AI 에이전트가 Redmine 작업을 대신 처리합니다. 한 번 연결하고 skill을 설치한 뒤에는 대화만 하세요 — *"create a Redmine issue for this commit"*, *"이번 주 An의 업무 성과는?"*, *"이 스토리의 테스트 케이스를 만들어줘"* — 각 단계만 확인하면 됩니다. 나머지는 에이전트가 처리합니다.

## 당신은 누구인가요? 레인을 선택하세요

| 👔 보스 / 매니저 | 💻 개발자 | 🧪 테스터 |
|---|---|---|
| 한 번에 한 직원씩 질문하세요 — *"An은 지금 뭐 하고 있지?"*, *"기한이 지난 작업이 있나?"* — 프로젝트별로 묶은 일/주 단위 성과 위젯을 받습니다. 읽기 전용이라 실수로 변경될 일이 없습니다. | 커밋과 PR이 자동으로 Redmine 이슈가 됩니다. 이름, 설명, 검증된 ID, changelog, 시간 기록까지. 당신은 확인만 하세요. | 유저 스토리가 테스트 케이스가 되고, 버그는 Google Sheets와 Redmine를 오가며, 상태가 다시 동기화됩니다. 검토하고 승인하세요. |

각 레인은 아래 agent skill이 담당합니다. 에이전트에게 한 문장으로 자신의 레인을 알려주면 나머지는 알아서 진행됩니다.

## 퀵 스타트 — 5분

### 1. Redmine API 키 발급

Redmine에 로그인한 뒤 **My account → API access key → Show**를 열어 키를 복사하세요.

> Redmine 6.1+에서는 공용 키 대신 사용자별 OAuth2 로그인을 사용할 수 있습니다 — [OAuth Setup](./docs/oauth-setup.md) 참조. 매니저 참고: oversight skill은 인원 조회를 위해 **admin** 키가 필요합니다.

### 2. Docker로 서버 실행

```bash
cp .env.example .env.docker
# .env.docker에 REDMINE_URL과 REDMINE_API_KEY를 입력한 뒤:
docker compose up --build -d
curl http://localhost:8000/health
```

모든 설정(auth 모드, 읽기 전용 모드, SSL 등)은 [.env.example](./.env.example) 참조.

### 3. 레인에 맞는 skill 설치 (한 줄 명령)

**개발자용** (이슈 워크플로, 플래닝, 일일 보고):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-dev.ps1 | iex
```

**테스터용** (Google Sheets 기반 QA 테스트 관리):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-tester.ps1 | iex
```

**둘 다** (모든 skill):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### 이 명령들은 어디서 실행하나요?

- 💻 **개발자 — 작업 중인 repo 안에서 실행하세요.** 작업 중인 저장소에서 터미널을 열고 명령을 붙여넣으세요. 스크립트가 `git`으로 repo root를 찾아 `<repo>/.agents/skills/`에 skill을 설치합니다(opencode와 Agent SDK가 자동 스캔). repo가 없으면 skill도 없습니다 — dev 워크플로는 코드가 옆에 있어야 합니다.
- 🧪 **테스터 — repo가 필요 없습니다.** repo에서 작업한다면 위 tester 명령을 그대로 쓰면 됩니다. 아니라면 건너뛰고 아래 데스크톱 앱 방식을 쓰세요. 유저 레벨 설치나 ZIP 업로드가 QA skill을 Claude Desktop, Codex, opencode desktop이 볼 수 있는 위치에 넣어줍니다. 저장소가 필요 없습니다.
- 👔 **보스 — repo도 터미널도 필요 없습니다.** 데스크톱 앱([Claude Desktop](https://claude.ai/download), [Codex](https://developers.openai.com/codex/) 또는 [opencode](https://opencode.ai/docs) desktop)을 설치하고 서버에 한 번 연결한 뒤(4단계) 아래 유저 레벨 설치나 ZIP 업로드로 oversight skill을 가져오세요. 이후에는 대화만 하면 됩니다.

그런 다음 에이전트를 다시 시작하고 인사하세요:

- 👔 *"직원 목록 보여줘"* → 이름 선택 → *"이번 주"*
- 💻 repo에서 `redmine init`을 한 번 실행한 뒤 *"create a Redmine issue for this commit"*
- 🧪 *"이 유저 스토리의 테스트 케이스를 만들어줘"*(아래 Google Sheets 설정 필요)

> **GitHub 연동 내장** — dev 워크플로는 `gh` CLI로 커밋/PR을 읽습니다(device flow, 토큰 붙여넣기 불필요): `gh auth login`.

### 4. 에이전트를 서버에 연결

서버는 `http://127.0.0.1:8000/mcp`에서 MCP를 지원합니다. opencode 예시(`opencode.json`):

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

`X-Redmine-*` 헤더는 `dynamic` auth 모드에서만 필요합니다. 기본 `legacy` 모드는 `.env.docker`의 키를 사용합니다. Claude Desktop, VS Code, Grok, Codex, Cline 설정은 [integrations.md](./docs/integrations.md)에 있습니다. 시크릿은 git에 올리지 마세요(`"{env:REDMINE_API_KEY}"`, `env_http_headers` 등). 수정 후 에이전트를 다시 시작하세요.

### 5. Google Sheets (테스터만)

QA skill은 서비스 계정으로 Google Sheets에서 테스트 케이스와 버그를 관리합니다:

1. [Google Cloud Console](https://console.cloud.google.com)에서 **Google Sheets API** 활성화, **Service Account** 생성, **JSON 키** 추가 후 `credentials/service-account.json`으로 저장.
2. 스프레드시트를 서비스 계정 이메일(Editor 권한)에 공유. 예: `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`.
3. `redmine init`(tester 플로우)이 물어볼 때 시트 URL/ID를 붙여넣으세요. Sheet ID는 `docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`의 중간 부분입니다.

## 전체 skill

| Skill | 레인 | 이렇게 말하세요 → 이렇게 받습니다 |
|---|---|---|
| [`redmine-init`](./skills/redmine-init/README.md) | 💻 Dev | *"이 repo를 매핑해줘"* → repo ↔ Redmine 프로젝트 연결, 멤버/tracker 캐시 |
| [`redmine-issue-workflow`](./skills/redmine-issue-workflow/README.md) | 💻 Dev | *"이 커밋의 이슈를 만들어줘"* → 검증된 이슈 생성, PR 머지 → 상태/시간 기록 |
| [`redmine-planning`](./skills/redmine-planning/README.md) | 💻 Dev | *"이 스토리를 나눠줘"* → 추정치·담당자·의존성이 있는 태스크 |
| [`redmine-daily-report`](./skills/redmine-daily-report/README.md) | 💻 Dev | *"일일 보고"* → 어제 일의 business + 기술 요약 |
| [`boss-project-oversight`](./skills/boss-project-oversight/README.md) | 👔 보스 | *"이번 주 An의 성과"* → 프로젝트별 인터랙티브 위젯 (읽기 전용, admin 키) |
| [`testcase-generation`](./skills/testcase-generation/README.md) | 🧪 테스터 | *"이 스토리의 테스트 케이스"* → 검토된 케이스를 Sheets에 기록 |
| [`bug-reporting`](./skills/bug-reporting/README.md) | 🧪 테스터 | *"이 버그를 기록해줘"* → Sheets에 자동 ID 버그 행 |
| [`bug-to-redmine`](./skills/bug-to-redmine/README.md) | 🧪 테스터 | *"버그를 Redmine에 올려줘"* → 이슈 생성, ID 역기록 |
| [`status-sync`](./skills/status-sync/README.md) | 🧪 테스터 | *"개발자가 수정을 끝냈나?"* → Redmine에서 시트 상태 동기화 |
| [`reopen-bug`](./skills/reopen-bug/README.md) | 🧪 테스터 | *"BUG-001 다시 열어줘"* → 허용된 워크플로로 이슈 재오픈, 시트 업데이트 |

### Claude Desktop 사용자 (테스터 & 보스: repo 불필요)

Claude Desktop은 skill을 ZIP 파일로 가져옵니다 — 저장소 안에서 일하지 않을 때 적합합니다. 빌드 방법:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1
```

그런 다음 **Settings → Customize → Skills → Add Skill → Upload ZIP** (skill마다 반복):

| ZIP | 레인 |
|---|---|
| `redmine-init` | 💻 Dev 스타터 |
| `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug` | 🧪 테스터 |
| `boss-project-oversight` | 👔 보스 |

### 유저 레벨 설치 (opencode global / ChatGPT desktop)

하나의 repo가 아니라 **어디서든** skill을 쓰고 싶을 때 권장합니다 — opencode와 ChatGPT 데스크톱 앱 모두 `%USERPROFILE%\.agents\skills\`를 자동 스캔합니다. 저장소 없이 데스크톱 앱(opencode, Codex, ChatGPT)에서 일하는 🧪 테스터와 👔 보스에게 가장 쉬운 경로입니다:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex
```

7개 skill(`redmine-init`, `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug`, `boss-project-oversight`)과 템플릿 파일(`README.md` 제외)을 설치합니다. 재실행 시 GitHub rate limit에 걸리면 먼저 `$env:GITHUB_TOKEN = "<your_pat>"`을 설정하세요(`public_repo` scope면 충분). 제거: `Remove-Item -Recurse -Force $env:USERPROFILE\.agents\skills`.

## 🎬 영상 가이드 (테스터 & 보스)

짧은 walkthrough — 먼저 시청한 뒤 위 단계를 따라 하세요. (녹화되는 대로 링크가 게시됩니다. 그때까지 각 행의 placeholder가 유지됩니다.)

| 레인 | 영상 | 링크 |
|---|---|---|
| 🧪 테스터 | 셋업: 데스크톱 앱 + 서버 연결 + QA skill 설치 | *coming soon* <!-- VIDEO-TESTER-SETUP: replace with https://... --> |
| 🧪 테스터 | 사용법: 첫 end-to-end 실행 (스토리 → 테스트 케이스 → 버그 → Redmine) | *coming soon* <!-- VIDEO-TESTER-USAGE: replace with https://... --> |
| 👔 보스 | 셋업: 데스크톱 앱 + 읽기 전용 연결 + oversight skill | *coming soon* <!-- VIDEO-BOSS-SETUP: replace with https://... --> |
| 👔 보스 | 사용법: 직원 목록 → 한 사람 선택 → 일/주 성과 위젯 | *coming soon* <!-- VIDEO-BOSS-USAGE: replace with https://... --> |

## 내부 동작 방식

서버는 skill이 대신 호출하는 **39개 MCP tool**을 제공합니다. 이슈(생성/목록/업데이트/관계), 시간 기록, 위키 페이지, 인원 및 성과 요약, 전역 검색, 그리고 Google Sheets와 memory tool. [MCP Tools](./docs/mcp-tools.md)와 [Tool Reference](./docs/tool-reference.md) 참조.

| Auth 모드 | 사용 시점 |
|---|---|
| `legacy` (기본값) | 단일 사용자 / 공용 credential — `.env`의 API 키 하나 |
| `oauth` | 사용자별 로그인, Redmine 6.1+ — [OAuth Setup](./docs/oauth-setup.md) 참조 |
| `dynamic` | 멀티테넌트 / 공용 VPS — 에이전트가 요청마다 `X-Redmine-URL` + `X-Redmine-API-Key` 전송 |

`REDMINE_AUTH_MODE=legacy|oauth|dynamic`으로 설정. 공개 배포는 `oauth`/`dynamic` 권장. 보스 PC에는 `REDMINE_MCP_READ_ONLY=true` 추가.

## Docs

- [MCP Tools](./docs/mcp-tools.md) — 모든 tool과 MCP 리소스
- [Tool Reference](./docs/tool-reference.md) — 상세 파라미터 레퍼런스
- [Docker & VPS deployment](./docs/docker-deployment.md) — 로컬 Docker 상세, 강화 VPS + HTTPS 설정
- [Claude Desktop setup](./docs/claude-desktop-setup.md) — Claude Desktop의 MCP + skill
- [OAuth Setup](./docs/oauth-setup.md) — 사용자별 OAuth2 (Redmine 6.1+)
- [Troubleshooting](./docs/troubleshooting.md) — 자주 발생하는 문제
- [Contributing](./docs/contributing.md) — 개발 환경 설정
- [Changelog](./CHANGELOG.md)

## License

MIT — [LICENSE](./LICENSE) 참조.
