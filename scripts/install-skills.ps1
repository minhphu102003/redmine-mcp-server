param(
    [string]$Target = "",
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop",
    [string]$CommitWorkflowPath = ""
)

$ErrorActionPreference = "Stop"

$skills = @("redmine-init", "redmine-issue-workflow", "redmine-planning")

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
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    $destFile = Join-Path $dest "SKILL.md"

    if ($local) {
        Copy-Item -Path (Join-Path $localSkills "$skill\SKILL.md") -Destination $destFile -Force
        Write-Host "Installed: $destFile (local copy)"
    } else {
        $url = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}/SKILL.md" -f $Repo, $Branch, $skill
        try {
            Invoke-WebRequest -Uri $url -OutFile $destFile
            Write-Host "Installed: $destFile (from $url)"
        } catch {
            throw "Failed to download skill '$skill' from $url. Check that the repo is public and the branch exists."
        }
    }

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
Write-Host "Skills installed into: $destRoot"
Write-Host "opencode and Claude Code / Agent SDK auto-scan .agents/skills/. You are free to move the folders anywhere else."
if ([string]::IsNullOrWhiteSpace($CommitWorkflowPath)) {
    Write-Host "Commit-workflow placeholder left empty - the commit pre-step is skipped (the skill works on an existing commit/PR)."
} elseif ($CommitWorkflowPath -eq "none") {
    Write-Host "Commit-workflow pre-step disabled (none)."
} else {
    Write-Host "Commit-workflow pre-step configured: $CommitWorkflowPath"
}
