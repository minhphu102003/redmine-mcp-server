param(
    [string]$Target = "",
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop"
)

$ErrorActionPreference = "Stop"

$skills = @("redmine-init", "testcase-generation", "bug-reporting", "bug-to-redmine", "status-sync", "reopen-bug")

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
}

Write-Host ""
Write-Host "Tester skills installed into: $destRoot"
Write-Host "opencode and Agent SDK auto-scan .agents/skills/. You are free to move the folders anywhere else."
Write-Host ""
Write-Host "QA skills installed: testcase-generation, bug-reporting, bug-to-redmine, status-sync, reopen-bug"
Write-Host "Also installed: redmine-init (needed for .redmine and .google-sheets memory)"
