# install-skills-claude-code.ps1
# Install MCP skills to Claude Code skills directory
# Usage: .\scripts\install-skills-claude-code.ps1

$ErrorActionPreference = "Stop"

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
        Copy-Item -Path $SourcePath -Destination $TargetPath -Recurse
        Write-Host "  Update $SkillName" -ForegroundColor Yellow
        $Updated++
    } else {
        # Install new skill
        Copy-Item -Path $SourcePath -Destination $TargetPath -Recurse
        Write-Host "  Install $SkillName" -ForegroundColor Green
        $Installed++
    }
}

Write-Host ""
Write-Host "Done: $Installed installed, $Updated updated, $Skipped skipped" -ForegroundColor Cyan
Write-Host "Skills location: $TargetDir" -ForegroundColor Gray
