# install-skills-codex.ps1
# NOTE: keep this file ASCII-only with NO BOM. raw.githubusercontent.com
# serves the BOM through to 'irm', and Windows PowerShell 5.1 then fails
# to parse the param() block when the script is run via 'irm ... | iex'.
# Copy ALL local skills (.\skills\*) to the current user's home directory so
# Codex (and any client auto-scanning ~/.agents/skills) can load them.
# Target: $env:USERPROFILE\.agents\skills  (fixed, no -Target needed)
# Source: local .\skills folder (must run from a local clone).
# Usage: .\scripts\install-skills-codex.ps1

$ErrorActionPreference = "Stop"

# Load the shared helper from disk (local run always has a script file).
$libCandidate = Join-Path $PSScriptRoot "_lib\Install-Skill.ps1"
if (-not (Test-Path -LiteralPath $libCandidate)) {
    throw "Shared helper not found: $libCandidate"
}
. $libCandidate

$skillsRoot = Join-Path $PSScriptRoot "..\skills"
if (-not (Test-Path -LiteralPath $skillsRoot)) {
    throw "Skills folder not found: $skillsRoot"
}

if (-not $env:USERPROFILE) {
    throw "USERPROFILE env not set -- cannot determine user-level install target."
}
$destRoot = Join-Path $env:USERPROFILE ".agents\skills"
New-Item -ItemType Directory -Path $destRoot -Force | Out-Null

# Discover every skill = a subfolder containing SKILL.md (future-proof:
# new skills are picked up automatically, no list to maintain).
$skills = Get-ChildItem -Path $skillsRoot -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") } |
    Select-Object -ExpandProperty Name

if ($skills.Count -eq 0) {
    throw "No skills found under $skillsRoot"
}

Write-Host ("Installing {0} local skill(s) to: {1}" -f $skills.Count, $destRoot) -ForegroundColor Cyan
Write-Host ""

$failed = 0
foreach ($skill in $skills) {
    $dest = Join-Path $destRoot $skill
    # Ship .html payloads (widget/picker templates) when the skill has any.
    # Extra *.md payloads (schemas, templates) are copied by the helper.
    $extraExt = @()
    if (Get-ChildItem -Path (Join-Path $skillsRoot $skill) -Filter "*.html" -File) {
        $extraExt = @(".html")
    }
    try {
        Install-SkillFromLocal -SkillName $skill -SourceDir (Join-Path $skillsRoot $skill) -DestDir $dest -ExtraExtensions $extraExt
        $files = Get-ChildItem -Path $dest -File | Select-Object -ExpandProperty Name
        Write-Host ("  [OK] {0}  ({1} file(s): {2})" -f $skill, $files.Count, ($files -join ", "))
    } catch {
        $failed++
        Write-Host ("  [FAIL] {0}  ({1})" -f $skill, $_.Exception.Message) -ForegroundColor Red
    }
}

Write-Host ""
if ($failed -gt 0) {
    throw "$failed skill(s) failed to install."
}
Write-Host "Done." -ForegroundColor Cyan
Write-Host ""
Write-Host "Codex auto-scans ~/.agents/skills/ -- restart the client if it was already running."
Write-Host "To update later: re-run this script (idempotent, overwrites in place)."
Write-Host "To uninstall:    Remove-Item -Recurse -Force $destRoot"
