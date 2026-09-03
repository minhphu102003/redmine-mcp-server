# NOTE: keep this file ASCII-only (no em-dash, no smart-quote) so it parses
# correctly via 'irm ... | iex' on Windows PowerShell 5.1, which can strip
# BOM from raw.githubusercontent.com responses.
param(
    [string]$Target = "",
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop",
    [string]$CommitWorkflowPath = ""
)

$ErrorActionPreference = "Stop"

$libPath = Join-Path $PSScriptRoot "_lib\Install-Skill.ps1"
. $libPath

$skills = @("redmine-init", "redmine-issue-workflow", "redmine-planning", "redmine-daily-report")

if ([string]::IsNullOrWhiteSpace($Target)) {
    try {
        $root = & git rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -eq 0 -and $root) {
            $Target = $root
        }
    } catch {
    }
}

if ([string]::IsNullOrWhiteSpace($Target)) {
    $Target = (Get-Location).Path
}

$destRoot = Join-Path $Target ".agents\skills"
New-Item -ItemType Directory -Path $destRoot -Force | Out-Null

$localSkills = if ($PSScriptRoot) { Join-Path $PSScriptRoot "..\skills" } else { "" }
$local = $false
if ($localSkills -and (Test-Path -LiteralPath $localSkills)) {
    $local = $true
}

foreach ($skill in $skills) {
    $dest = Join-Path $destRoot $skill

    if ($local) {
        Install-SkillFromLocal -SkillName $skill -SourceDir (Join-Path $localSkills $skill) -DestDir $dest
        Write-Host "Installed: $dest (local copy)"
    } else {
        Install-SkillFromGitHub -SkillName $skill -Repo $Repo -Branch $Branch -DestDir $dest
        Write-Host "Installed: $dest (from github)"
    }

    $destFile = Join-Path $dest "SKILL.md"

    if ($skill -eq "redmine-issue-workflow" -and -not [string]::IsNullOrWhiteSpace($CommitWorkflowPath)) {
        $content = [System.IO.File]::ReadAllText($destFile)
        $content = $content.Replace("{{COMMIT_WORKFLOW_PATH}}", $CommitWorkflowPath)
        [System.IO.File]::WriteAllText($destFile, $content)
        Write-Host "Configured COMMIT_WORKFLOW_PATH -> '$CommitWorkflowPath'"

        if ($CommitWorkflowPath -ne "none") {
            $wfPath = Join-Path $Target $CommitWorkflowPath
            if (-not (Test-Path -LiteralPath $wfPath)) {
                Write-Host "WARNING: commit workflow file not found at '$wfPath' - the commit pre-step will be skipped."
            }
        }
    }
}

Write-Host ""
Write-Host "Dev skills installed into: $destRoot"
Write-Host "opencode and Agent SDK auto-scan .agents/skills/. You are free to move the folders anywhere else."
if ([string]::IsNullOrWhiteSpace($CommitWorkflowPath)) {
    Write-Host "Commit-workflow placeholder left empty - the commit pre-step is skipped (the skill works on an existing commit/PR)."
} elseif ($CommitWorkflowPath -eq "none") {
    Write-Host "Commit-workflow pre-step disabled (none)."
} else {
    Write-Host "Commit-workflow pre-step configured: $CommitWorkflowPath"
}
