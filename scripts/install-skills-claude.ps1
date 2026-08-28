param(
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop",
    [switch]$DevOnly,
    [switch]$TesterOnly
)

$ErrorActionPreference = "Stop"

$allSkills = @("redmine-init", "redmine-issue-workflow", "redmine-planning", "redmine-daily-report", "testcase-generation", "bug-reporting", "bug-to-redmine", "status-sync", "reopen-bug")

$devSkills = @("redmine-init", "redmine-issue-workflow", "redmine-planning", "redmine-daily-report")
$testerSkills = @("redmine-init", "testcase-generation", "bug-reporting", "bug-to-redmine", "status-sync", "reopen-bug")

if ($DevOnly) {
    $skills = $devSkills
    Write-Host "Installing DEV skills only..."
} elseif ($TesterOnly) {
    $skills = $testerSkills
    Write-Host "Installing TESTER skills only..."
} else {
    $skills = $allSkills
    Write-Host "Installing ALL skills..."
}

$claudeGlobalDir = Join-Path $env:USERPROFILE ".claude\skills"
New-Item -ItemType Directory -Path $claudeGlobalDir -Force | Out-Null

$localSkills = if ($PSScriptRoot) { Join-Path $PSScriptRoot "..\skills" } else { "" }
$local = $false
if ($localSkills -and (Test-Path -LiteralPath $localSkills)) {
    $local = $true
}

foreach ($skill in $skills) {
    $dest = Join-Path $claudeGlobalDir $skill
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    $destFile = Join-Path $dest "SKILL.md"

    if ($local) {
        Copy-Item -Path (Join-Path $localSkills "$skill\SKILL.md") -Destination $destFile -Force
        $extraFiles = Get-ChildItem -Path (Join-Path $localSkills $skill) -File | Where-Object { $_.Name -ne "SKILL.md" -and $_.Name -ne "README.md" }
        foreach ($f in $extraFiles) {
            Copy-Item -Path $f.FullName -Destination $dest -Force
            Write-Host "  Installed: $(Join-Path $skill $f.Name)"
        }
        Write-Host "  Installed: $skill/SKILL.md"
    } else {
        $url = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}/SKILL.md" -f $Repo, $Branch, $skill
        try {
            Invoke-WebRequest -Uri $url -OutFile $destFile
            Write-Host "  Installed: $skill/SKILL.md"
        } catch {
            throw "Failed to download skill '$skill' from $url"
        }
        if ($skill -eq "redmine-init") {
            $extraFiles = @("member-rules-catalog.md", "google-sheets-schema.md")
            foreach ($extraFile in $extraFiles) {
                $extraUrl = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}/{3}" -f $Repo, $Branch, $skill, $extraFile
                $extraPath = Join-Path $dest $extraFile
                try {
                    Invoke-WebRequest -Uri $extraUrl -OutFile $extraPath
                    Write-Host "  Installed: $skill/$extraFile"
                } catch {
                    Write-Host "  WARNING: Failed to download $extraFile"
                }
            }
        }
        if ($skill -eq "testcase-generation") {
            $extraUrl = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}/USER_STORY_TEMPLATE.md" -f $Repo, $Branch, $skill
            $extraFile = Join-Path $dest "USER_STORY_TEMPLATE.md"
            try {
                Invoke-WebRequest -Uri $extraUrl -OutFile $extraFile
                Write-Host "  Installed: $skill/USER_STORY_TEMPLATE.md"
            } catch {
                Write-Host "  WARNING: Failed to download USER_STORY_TEMPLATE.md"
            }
        }
    }
}

Write-Host ""
Write-Host "========================================"
Write-Host "Skills installed to: $claudeGlobalDir"
Write-Host "========================================"
Write-Host ""
Write-Host "Claude Code will auto-load skills from ~/.claude/skills/"
Write-Host "Restart Claude Code to use the new skills."
Write-Host ""
Write-Host "To verify, run in Claude Code:"
Write-Host "  /list-skills"
