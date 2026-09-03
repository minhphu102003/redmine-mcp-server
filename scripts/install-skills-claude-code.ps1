# install-skills-claude-code.ps1
# NOTE: keep this file ASCII-only with NO BOM. raw.githubusercontent.com
# serves the BOM through to 'irm', and Windows PowerShell 5.1 then fails
# to parse the param() block when the script is run via 'irm ... | iex'.
# Install MCP skills to Claude Code skills directory
# Usage: .\scripts\install-skills-claude-code.ps1

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    throw "install-skills-claude-code.ps1 must be run from a local clone (it copies from .\skills\). Usage: .\scripts\install-skills-claude-code.ps1"
}

$libPath = Join-Path $PSScriptRoot "_lib\Install-Skill.ps1"
. $libPath

$SourceDir = Join-Path (Join-Path $PSScriptRoot "..") "skills"
$TargetDir = Join-Path (Join-Path $env:USERPROFILE ".claude") "skills"

# Ensure target directory exists
if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    Write-Host "Created: $TargetDir" -ForegroundColor Green
}

# Get all skills from source
$Skills = Get-ChildItem -Path $SourceDir -Directory

$Installed = 0
$Updated = 0
$Skipped = 0

foreach ($Skill in $Skills) {
    $SkillName = $Skill.Name
    $SourcePath = $Skill.FullName
    $TargetPath = Join-Path $TargetDir $SkillName

    $SourceManifest = Join-Path $SourcePath "SKILL.md"
    $TargetManifest = Join-Path $TargetPath "SKILL.md"

    if (-not (Test-Path $SourceManifest)) {
        Write-Host "  Skip  $SkillName (no SKILL.md)" -ForegroundColor Yellow
        $Skipped++
        continue
    }

    if (Test-Path $TargetPath) {
        # Compare timestamps
        $SourceTime = (Get-Item $SourceManifest).LastWriteTime
        $TargetTime = (Get-Item $TargetManifest).LastWriteTime

        if ($SourceTime -le $TargetTime) {
            Write-Host "  Same  $SkillName" -ForegroundColor Gray
            $Skipped++
            continue
        }

        # Update existing skill
        Remove-Item -Path $TargetPath -Recurse -Force
        Install-SkillFromLocal -SkillName $SkillName -SourceDir $SourcePath -DestDir $TargetPath
        Write-Host "  Update $SkillName" -ForegroundColor Yellow
        $Updated++
    } else {
        # Install new skill
        Install-SkillFromLocal -SkillName $SkillName -SourceDir $SourcePath -DestDir $TargetPath
        Write-Host "  Install $SkillName" -ForegroundColor Green
        $Installed++
    }
}

Write-Host ""
Write-Host "Done: $Installed installed, $Updated updated, $Skipped skipped" -ForegroundColor Cyan
Write-Host "Skills location: $TargetDir" -ForegroundColor Gray
