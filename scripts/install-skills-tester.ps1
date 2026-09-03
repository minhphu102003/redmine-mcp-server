param(
    [string]$Target = "",
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop"
)

$ErrorActionPreference = "Stop"

$libPath = Join-Path $PSScriptRoot "_lib\Install-Skill.ps1"
. $libPath

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

    if ($local) {
        Install-SkillFromLocal -SkillName $skill -SourceDir (Join-Path $localSkills $skill) -DestDir $dest
        Write-Host "Installed: $dest (local copy)"
    } else {
        Install-SkillFromGitHub -SkillName $skill -Repo $Repo -Branch $Branch -DestDir $dest
        Write-Host "Installed: $dest (from github)"
    }
}

Write-Host ""
Write-Host "Tester skills installed into: $destRoot"
Write-Host "opencode and Agent SDK auto-scan .agents/skills/. You are free to move the folders anywhere else."
Write-Host ""
Write-Host "QA skills installed: testcase-generation, bug-reporting, bug-to-redmine, status-sync, reopen-bug"
Write-Host "Also installed: redmine-init (needed for .redmine and .google-sheets memory)"
