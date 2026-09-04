# Redmine MCP Server

> 🌐 English: [README.md](./README.md) · Tiếng Việt: [README.vi.md](./README.vi.md)

AIエージェントがRedmine作業を代行します。一度接続してskillをインストールすれば、あとは話しかけるだけ — *"create a Redmine issue for this commit"*、*"今週のAnの実績は?"*、*"このストーリーのテストケースを作って"* — 各ステップを確認するだけです。残りはエージェントが処理します。

## あなたは誰ですか? レーンを選んでください

| 👔 ボス / マネージャー | 💻 開発者 | 🧪 テスター |
|---|---|---|
| 一度に一人ずつ尋ねてください — *"Anは今何をしている?"*、*"期限切れタスクはある?"* — プロジェクト別にまとめた日/週パフォーマンスウィジェットを受け取ります。読み取り専用なので誤って変更される心配がありません。 | コミットとPRが自動でRedmine 이슈になります。命名、説明、検証済みID、changelog、時間記録まで。あなたは確認するだけです。 | ユーザーストーリーがテストケースになり、バグはGoogle SheetsとRedmine間を行き来し、ステータスが同期されます。レビューして承認してください。 |

各レーンは以下のagent skillが担当します。エージェントに一文で自分のレーンを伝えれば、あとは 맡せてください。

## クイックスタート — 5分

### 1. Redmine APIキーを取得

Redmineにログインし、**My account → API access key → Show**を開いてキーをコピーします。

> Redmine 6.1+では共用キーの代わりにユーザーごとのOAuth2ログインが使えます — [OAuth Setup](./docs/oauth-setup.md)参照。マネージャー向け: oversight skillは人員取得のため**admin**キーが必要です。

### 2. Dockerでサーバーを起動

```bash
cp .env.example .env.docker
# .env.dockerにREDMINE_URLとREDMINE_API_KEYを設定してから:
docker compose up --build -d
curl http://localhost:8000/health
```

全設定(authモード、読み取り専用モード、SSL等)は[.env.example](./.env.example)参照。

### 3. レーン用のskillをインストール (ワンコマンド)

**開発者向け** (イシューワークフロー、プランニング、デイリーレポート):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-dev.ps1 | iex
```

**テスター向け** (Google SheetsによるQAテスト管理):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-tester.ps1 | iex
```

**両方** (全skill):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### これらのコマンドはどこで実行しますか?

- 💻 **開発者 — 作業中のrepo内で実行してください。** 作業中のリポジトリでターミナルを開き、コマンドを貼り付けます。スクリプトは`git`でrepo rootを探し、`<repo>/.agents/skills/`にskillを配置します(opencodeとAgent SDKが自動スキャン)。repoがなければskillもありません — devワークフローはコードが隣にある前提です。
- 🧪 **テスター — repoは不要です。** repo内で作業する場合は上記testerコマンドをそのまま使えます。そうでない場合はスキップして下のデスクトップアプリ方式を使ってください。ユーザーレベルのインストールやZIPアップロードがQA skillをClaude Desktop、Codex、opencode desktopの見える場所に配置します。リポジトリは不要です。
- 👔 **ボス — repoもターミナル操作も不要です。** デスクトップアプリ([Claude Desktop](https://claude.ai/download)、[Codex](https://developers.openai.com/codex/)、[opencode](https://opencode.ai/docs) desktop)をインストールし、サーバーに一度接続して(手順4)、下のユーザーレベルインストールやZIPアップロードでoversight skillを取得してください。以降はチャットするだけです。

その後エージェントを再起動して挨拶しましょう:

- 👔 *"従業員リストを見せて"* → 名前を選択 → *"今週"*
- 💻 repoで`redmine init`を一度実行してから*"create a Redmine issue for this commit"*
- 🧪 *"このユーザーストーリーのテストケースを作って"*(下のGoogle Sheets設定が必要)

> **GitHub連携内蔵** — devワークフローは`gh` CLIでコミット/PRを読み取ります(device flow、トークン貼り付け不要): `gh auth login`.

### 4. エージェントをサーバーに接続

サーバーは`http://127.0.0.1:8000/mcp`でMCPを話します。opencodeの例(`opencode.json`):

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

`X-Redmine-*`ヘッダーは`dynamic` authモードでのみ必要です。デフォルトの`legacy`モードは`.env.docker`のキーを使います。Claude Desktop、VS Code、Grok、Codex、Clineの設定は[integrations.md](./docs/integrations.md)にあります。シークレットはgitに入れないでください(`"{env:REDMINE_API_KEY}"`、`env_http_headers`等)。編集後はエージェントを再起動してください。

### 5. Google Sheets (テスターのみ)

QA skillはサービスアカウントでGoogle Sheets内のテストケースとバグを管理します:

1. [Google Cloud Console](https://console.cloud.google.com)で**Google Sheets API**を有効化し、**Service Account**を作成、**JSONキー**を追加して`credentials/service-account.json`として保存。
2. スプレッドシートをサービスアカウントのメールアドレス(Editor権限)に共有。例: `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`。
3. `redmine init`(testerフロー)に聞かれたらシートURL/IDを貼り付けます。Sheet IDは`docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`の中間部分です。

## 全skill

| Skill | レーン | こう言う → こうなる |
|---|---|---|
| [`redmine-init`](./skills/redmine-init/README.md) | 💻 Dev | *"このrepoをマップして"* → repo ↔ Redmineプロジェクト連携、メンバー/trackerキャッシュ |
| [`redmine-issue-workflow`](./skills/redmine-issue-workflow/README.md) | 💻 Dev | *"このコミットのイシューを"* → 検証済みイシュー作成、PRマージ → ステータス/時間記録 |
| [`redmine-planning`](./skills/redmine-planning/README.md) | 💻 Dev | *"このストーリーを分割して"* → 見積もり・担当・依存付きタスク |
| [`redmine-daily-report`](./skills/redmine-daily-report/README.md) | 💻 Dev | *"デイリーレポート"* → 昨日のビジネス+技術サマリー |
| [`boss-project-oversight`](./skills/boss-project-oversight/README.md) | 👔 ボス | *"今週のAnの実績"* → プロジェクト別インタラクティブウィジェット (読み取り専用、adminキー) |
| [`testcase-generation`](./skills/testcase-generation/README.md) | 🧪 テスター | *"このストーリーのテストケース"* → レビュー済みケースをSheetsに記録 |
| [`bug-reporting`](./skills/bug-reporting/README.md) | 🧪 テスター | *"このバグを記録して"* → Sheetsに自動IDバグ行 |
| [`bug-to-redmine`](./skills/bug-to-redmine/README.md) | 🧪 テスター | *"バグをRedmineに上げて"* → イシュー作成、ID逆書き込み |
| [`status-sync`](./skills/status-sync/README.md) | 🧪 テスター | *"開発者の修正は終わった?"* → Redmineからシート状態同期 |
| [`reopen-bug`](./skills/reopen-bug/README.md) | 🧪 テスター | *"BUG-001を再オープン"* → 許可ワークフローで再オープン、シート更新 |

### Claude Desktopユーザー (テスター&ボス: repo不要)

Claude DesktopはskillをZIPファイルでインポートします — リポジトリ内で作業しない場合に最適です。ビルド方法:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1
```

その後**Settings → Customize → Skills → Add Skill → Upload ZIP** (skillごとに繰り返し):

| ZIP | レーン |
|---|---|
| `redmine-init` | 💻 Devスターター |
| `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug` | 🧪 テスター |
| `boss-project-oversight` | 👔 ボス |

### ユーザーレベルインストール (opencode global / ChatGPT desktop)

一つのrepoだけでなく**どこでも**skillを使いたい場合におすすめ — opencodeとChatGPTデスクトップアプリはどちらも`%USERPROFILE%\.agents\skills\`を自動スキャンします。リポジトリなしでデスクトップアプリ(opencode、Codex、ChatGPT)を使う🧪テスターと👔ボスに最も簡単な方法です:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex
```

7つのskill(`redmine-init`、`testcase-generation`、`bug-reporting`、`bug-to-redmine`、`status-sync`、`reopen-bug`、`boss-project-oversight`)とテンプレートファイル(`README.md`除く)をインストールします。再実行時にGitHub rate limitに当たったら先に`$env:GITHUB_TOKEN = "<your_pat>"`を設定してください(`public_repo`スコープで十分)。アンインストール: `Remove-Item -Recurse -Force $env:USERPROFILE\.agents\skills`.

## 🎬 動画ガイド (テスター&ボス)

短いwalkthrough — 先に見てから上記手順に従ってください。(録画され次第リンクを掲載します。それまで各行のplaceholderを維持します。)

| レーン | 動画 | リンク |
|---|---|---|
| 🧪 テスター | セットアップ: デスクトップアプリ + サーバー接続 + QA skillインストール | *coming soon* <!-- VIDEO-TESTER-SETUP: replace with https://... --> |
| 🧪 テスター | 使い方: 初回end-to-end実行 (ストーリー → テストケース → バグ → Redmine) | *coming soon* <!-- VIDEO-TESTER-USAGE: replace with https://... --> |
| 👔 ボス | セットアップ: デスクトップアプリ + 読み取り専用接続 + oversight skill | *coming soon* <!-- VIDEO-BOSS-SETUP: replace with https://... --> |
| 👔 ボス | 使い方: 従業員リスト → 一人選択 → 日/週パフォーマンスウィジェット | *coming soon* <!-- VIDEO-BOSS-USAGE: replace with https://... --> |

## 内部の仕組み

サーバーはskillが代行呼び出しする**39のMCPツール**を公開しています。イシュー(作成/一覧/更新/関連)、時間記録、wikiページ、人員&パフォーマンスサマリー、全体検索、Google Sheets・memoryツール。 [MCP Tools](./docs/mcp-tools.md)と[Tool Reference](./docs/tool-reference.md)参照。

| Authモード | 使用場面 |
|---|---|
| `legacy` (デフォルト) | 単一ユーザー / 共通credential — `.env`のAPIキー一つ |
| `oauth` | ユーザーごとログイン、Redmine 6.1+ — [OAuth Setup](./docs/oauth-setup.md)参照 |
| `dynamic` | マルチテナント / 共用VPS — エージェントがリクエストごとに`X-Redmine-URL` + `X-Redmine-API-Key`送信 |

`REDMINE_AUTH_MODE=legacy|oauth|dynamic`で設定。公開デプロイは`oauth`/`dynamic`推奨。ボスPCには`REDMINE_MCP_READ_ONLY=true`を追加。

## Docs

- [MCP Tools](./docs/mcp-tools.md) — 全ツールとMCPリソース
- [Tool Reference](./docs/tool-reference.md) — 詳細パラメータリファレンス
- [Docker & VPS deployment](./docs/docker-deployment.md) — ローカルDocker詳細、強化VPS + HTTPS設定
- [Claude Desktop setup](./docs/claude-desktop-setup.md) — Claude DesktopのMCP + skill
- [OAuth Setup](./docs/oauth-setup.md) — ユーザーごとOAuth2 (Redmine 6.1+)
- [Troubleshooting](./docs/troubleshooting.md) — よくある問題
- [Contributing](./docs/contributing.md) — 開発環境セットアップ
- [Changelog](./CHANGELOG.md)

## License

MIT — [LICENSE](./LICENSE)参照。
