# Google Sheets Schema

This file is created only for **testers** (role = Tester or Both). It maps Redmine projects to test management spreadsheets.

## Service Account

`redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`
Users create their own Google Sheet and share it with this email (Editor permission).

## Schema

```json
{
  "version": 1,
  "default_folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
  "projects": [
    {
      "redmine_project_id": 12,
      "redmine_project_name": "Example Project",
      "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
      "spreadsheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit",
      "spreadsheet_title": "Example Project - QA Test Management",
      "sheets": {
        "testcases": "TestCases",
        "bugs": "Bugs"
      },
      "created_at": "2026-08-26T00:00:00Z"
    }
  ],
  "fetched_at": "2026-08-26T00:00:00Z"
}
```

- `version`: `1`.
- `default_folder_id` (optional): Google Drive folder ID where new sheets are created. `null` = My Drive. Server-side only.
- `projects`: array of project-to-sheet mappings. A tester can have multiple projects, each with its own spreadsheet.
  - `redmine_project_id`: must match `project.id` in `.redmine`.
  - `spreadsheet_id`: the Google Sheets spreadsheet ID.
  - `spreadsheet_url`: direct link to the spreadsheet.
  - `sheets.testcases`: name of the TestCases sheet (default: "TestCases").
  - `sheets.bugs`: name of the Bugs sheet (default: "Bugs").
- `fetched_at`: current time, ISO 8601 with `Z` (UTC).
- Strip all `<insecure-content-...>` wrapper tags from names.
- The file contains no secrets (service account email only, not the key) — safe to commit.
