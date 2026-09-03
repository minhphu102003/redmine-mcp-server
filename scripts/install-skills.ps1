# NOTE: keep this file ASCII-only with NO BOM. raw.githubusercontent.com
# serves the BOM through to 'irm', and Windows PowerShell 5.1 then fails
# to parse the param() block when the script is run via 'irm ... | iex'.
param(
    [string]$Target = "",
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop",
    [string]$CommitWorkflowPath = "",
    [string]$MessageDelivery = ""
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
    try {
        $libCode = Invoke-RestMethod -Uri $libUrl -UseBasicParsing
    } catch {
        throw "Cannot load shared helper from $libUrl -- $_"
    }
    # Strip a leading BOM if the server sends one: PS 5.1 misparses it
    # inside [scriptblock]::Create (first-line comment becomes command '?#').
    $libCode = $libCode.TrimStart([char]0xFEFF)
    . ([scriptblock]::Create($libCode))
}

$skills = @("redmine-init", "redmine-issue-workflow", "redmine-planning", "redmine-daily-report", "boss-project-oversight", "testcase-generation", "bug-reporting", "bug-to-redmine", "status-sync", "reopen-bug")

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

    # Boss-only: ship the widget template alongside the skill payload.
    $extraExt = @()
    if ($skill -eq "boss-project-oversight") { $extraExt = @(".html") }

    if ($local) {
        Install-SkillFromLocal -SkillName $skill -SourceDir (Join-Path $localSkills $skill) -DestDir $dest -ExtraExtensions $extraExt
        Write-Host "Installed: $dest (local copy)"
    } else {
        Install-SkillFromGitHub -SkillName $skill -Repo $Repo -Branch $Branch -DestDir $dest -ExtraExtensions $extraExt
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

    if ($skill -eq "redmine-daily-report" -and -not [string]::IsNullOrWhiteSpace($MessageDelivery)) {
        $content = [System.IO.File]::ReadAllText($destFile)
        $content = $content.Replace("{{MESSAGE_DELIVERY}}", $MessageDelivery)
        [System.IO.File]::WriteAllText($destFile, $content)
        Write-Host "Configured MESSAGE_DELIVERY -> '$MessageDelivery'"
    }
}

Write-Host ""
Write-Host "Skills installed into: $destRoot"
Write-Host "opencode and Agent SDK auto-scan .agents/skills/. You are free to move the folders anywhere else."
if ([string]::IsNullOrWhiteSpace($CommitWorkflowPath)) {
    Write-Host "Commit-workflow placeholder left empty - the commit pre-step is skipped (the skill works on an existing commit/PR)."
} elseif ($CommitWorkflowPath -eq "none") {
    Write-Host "Commit-workflow pre-step disabled (none)."
} else {
    Write-Host "Commit-workflow pre-step configured: $CommitWorkflowPath"
}
if ([string]::IsNullOrWhiteSpace($MessageDelivery)) {
    Write-Host "Message-delivery placeholder left empty - the daily-report skill presents the approved draft for copy-paste (no sending)."
} elseif ($MessageDelivery -eq "none") {
    Write-Host "Message-delivery disabled (none) - the daily-report skill never sends."
} else {
    Write-Host "Message-delivery configured: $MessageDelivery"
}
