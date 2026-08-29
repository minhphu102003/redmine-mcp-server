# install-skills-claude-desktop.ps1
# Create ZIP files for each skill for Claude Desktop import
# Usage: .\scripts\install-skills-claude-desktop.ps1

$ErrorActionPreference = "Stop"

$SourceDir = Join-Path (Join-Path $PSScriptRoot "..") "skills"
$OutputDir = Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "dist") "claude-desktop-skills"

# Ensure output directory exists
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Get all skills from source
$Skills = Get-ChildItem -Path $SourceDir -Directory

Write-Host "Creating ZIP files for Claude Desktop..." -ForegroundColor Cyan
Write-Host ""

foreach ($Skill in $Skills) {
    $SkillName = $Skill.Name
    $SkillPath = $Skill.FullName
    $ZipPath = Join-Path $OutputDir "$SkillName.zip"

    # Remove old ZIP if exists
    if (Test-Path $ZipPath) {
        Remove-Item -Path $ZipPath -Force
    }

    # Create ZIP with all files in skill directory
    Compress-Archive -Path "$SkillPath\*" -DestinationPath $ZipPath -Force

    $ZipSize = [math]::Round((Get-Item $ZipPath).Length / 1KB, 1)
    Write-Host "  Created: $SkillName.zip ($ZipSize KB)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done! ZIP files saved to: $OutputDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "To import into Claude Desktop:" -ForegroundColor Yellow
Write-Host "  1. Open Claude Desktop" -ForegroundColor White
Write-Host "  2. Go to Settings > Customize > Skills" -ForegroundColor White
Write-Host "  3. Click 'Add Skill' > Upload ZIP file" -ForegroundColor White
Write-Host "  4. Select a ZIP file from: $OutputDir" -ForegroundColor White
