# install-skills-user.ps1
# NOTE: keep this file ASCII-only with NO BOM. raw.githubusercontent.com
# serves the BOM through to 'irm', and Windows PowerShell 5.1 then fails
# to parse the param() block when the script is run via 'irm ... | iex'.
# Install QA/tester skills to the current user's home directory so multiple
# agent clients (opencode, ChatGPT desktop, ...) can auto-scan them.
# Target: $env:USERPROFILE\.agents\skills  (fixed, no -Target needed)
# Source: GitHub raw (default) -- same behavior as install-skills*.ps1 when piped.
# Usage: irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex

param(
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop",
    [string]$GitHubToken = $env:GITHUB_TOKEN
)

$ErrorActionPreference = "Stop"

# Load the shared helper. When piped via 'irm ... | iex' there is no script
# file on disk ($PSScriptRoot is empty), so fetch the helper from GitHub raw.
$libCandidate = ""
if ($PSScriptRoot) {
    $candidate = Join-Path $PSScriptRoot "_lib\Install-Skill.ps1"
    if (Test-Path -LiteralPath $candidate) { $libCandidate = $candidate }
}
if ($libCandidate) {
    . $libCandidate
} else {
    $libUrl = "https://raw.githubusercontent.com/{0}/{1}/scripts/_lib/Install-Skill.ps1" -f $Repo, $Branch
    $headers = @{}
    if ($GitHubToken) { $headers["Authorization"] = "token $GitHubToken" }
    try {
        $libCode = Invoke-RestMethod -Uri $libUrl -Headers $headers -UseBasicParsing
    } catch {
        throw "Cannot load shared helper from $libUrl -- $_"
    }
    # Strip a leading BOM if the server sends one: PS 5.1 misparses it
    # inside [scriptblock]::Create (first-line comment becomes command '?#').
    $libCode = $libCode.TrimStart([char]0xFEFF)
    . ([scriptblock]::Create($libCode))
}

# 6 tester skills (same list as install-skills-tester.ps1) + boss oversight
$skills = @(
    "redmine-init",
    "testcase-generation",
    "bug-reporting",
    "bug-to-redmine",
    "status-sync",
    "reopen-bug",
    "boss-project-oversight"
)

if (-not $env:USERPROFILE) {
    throw "USERPROFILE env not set -- cannot determine user-level install target."
}
$destRoot = Join-Path $env:USERPROFILE ".agents\skills"
New-Item -ItemType Directory -Path $destRoot -Force | Out-Null

Write-Host "Installing user-level skills to: $destRoot" -ForegroundColor Cyan
Write-Host ""

foreach ($skill in $skills) {
    $dest = Join-Path $destRoot $skill
    # Boss-only: ship the widget template alongside the skill payload.
    $extraExt = @()
    if ($skill -eq "boss-project-oversight") { $extraExt = @(".html") }
    try {
        Install-SkillFromGitHub -SkillName $skill -Repo $Repo -Branch $Branch -DestDir $dest -GitHubToken $GitHubToken -ExtraExtensions $extraExt
        $files = Get-ChildItem -Path $dest -File | Select-Object -ExpandProperty Name
        Write-Host ("  [OK] {0}  ({1} file(s): {2})" -f $skill, $files.Count, ($files -join ", "))
    } catch {
        Write-Host ("  [FAIL] {0}  ({1})" -f $skill, $_.Exception.Message) -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
Write-Host ""
Write-Host "Auto-scan coverage:" -ForegroundColor Yellow
Write-Host "  * opencode      -> ~/.agents/skills/  (verified)"
Write-Host "  * ChatGPT app   -> ~/.agents/skills/  (confirmed by user)"
Write-Host ""
Write-Host "To update later: re-run this script (idempotent, overwrites in place)."
Write-Host "To uninstall:    Remove-Item -Recurse -Force $destRoot"
