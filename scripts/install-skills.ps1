param(
    [string]$Target = "",
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop",
    [string]$CommitWorkflowPath = "",
    [string]$MessageDelivery = ""
)

$ErrorActionPreference = "Stop"

$skills = @("redmine-init", "redmine-issue-workflow", "redmine-planning", "redmine-daily-report", "testcase-generation", "bug-reporting", "bug-to-redmine", "status-sync", "reopen-bug")

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
        # Copy extra files (e.g. USER_STORY_TEMPLATE.md)
        $extraFiles = Get-ChildItem -Path (Join-Path $localSkills $skill) -File | Where-Object { $_.Name -ne "SKILL.md" -and $_.Name -ne "README.md" }
        foreach ($f in $extraFiles) {
            Copy-Item -Path $f.FullName -Destination $dest -Force
            Write-Host "Installed: $(Join-Path $dest $f.Name) (local copy)"
        }
        Write-Host "Installed: $destFile (local copy)"
    } else {
        $url = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}/SKILL.md" -f $Repo, $Branch, $skill
        try {
            Invoke-WebRequest -Uri $url -OutFile $destFile
            Write-Host "Installed: $destFile (from $url)"
        } catch {
            throw "Failed to download skill '$skill' from $url. Check that the repo is public and the branch exists."
        }
        # Download extra files for redmine-init
        if ($skill -eq "redmine-init") {
            $extraFiles = @("member-rules-catalog.md", "google-sheets-schema.md")
            foreach ($extraFile in $extraFiles) {
                $extraUrl = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}/{3}" -f $Repo, $Branch, $skill, $extraFile
                $extraPath = Join-Path $dest $extraFile
                try {
                    Invoke-WebRequest -Uri $extraUrl -OutFile $extraPath
                    Write-Host "Installed: $extraPath (from $extraUrl)"
                } catch {
                    Write-Host "WARNING: Failed to download $extraFile — the skill may not work correctly."
                }
            }
        }
        # Download extra files for testcase-generation
        if ($skill -eq "testcase-generation") {
            $extraUrl = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}/USER_STORY_TEMPLATE.md" -f $Repo, $Branch, $skill
            $extraFile = Join-Path $dest "USER_STORY_TEMPLATE.md"
            try {
                Invoke-WebRequest -Uri $extraUrl -OutFile $extraFile
                Write-Host "Installed: $extraFile (from $extraUrl)"
            } catch {
                Write-Host "WARNING: Failed to download USER_STORY_TEMPLATE.md — the skill may not work correctly."
            }
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
