# install-skills-claude-desktop.ps1
# Create ZIP files for each skill for Claude Desktop import
# Usage: irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1

$ErrorActionPreference = "Stop"

$RepoUrl = "https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop"
$OutputDir = "claude-desktop-skills"
$SkillsDir = "skills"

# Skills list for Claude Desktop (QA-focused)
$SkillNames = @(
    "redmine-init",
    "testcase-generation",
    "bug-reporting",
    "bug-to-redmine",
    "status-sync",
    "reopen-bug"
)

# Create temp directory for downloading
$TempDir = Join-Path $env:TEMP "redmine-skills-$(Get-Random)"
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

Write-Host "Downloading skills from GitHub..." -ForegroundColor Cyan

foreach ($SkillName in $SkillNames) {
    $SkillDir = Join-Path $TempDir $SkillName
    New-Item -ItemType Directory -Path $SkillDir -Force | Out-Null
    
    # Download SKILL.md
    $SkillMdUrl = "$RepoUrl/skills/$SkillName/SKILL.md"
    try {
        Invoke-WebRequest -Uri $SkillMdUrl -OutFile (Join-Path $SkillDir "SKILL.md") -UseBasicParsing
    } catch {
        Write-Host "  Warning: Could not download SKILL.md for $SkillName" -ForegroundColor Yellow
    }
    
    # Download README.md if exists
    $ReadmeUrl = "$RepoUrl/skills/$SkillName/README.md"
    try {
        Invoke-WebRequest -Uri $ReadmeUrl -OutFile (Join-Path $SkillDir "README.md") -UseBasicParsing
    } catch {
        # README.md is optional
    }
}

Write-Host ""
Write-Host "Creating ZIP files for Claude Desktop..." -ForegroundColor Cyan
Write-Host ""

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

foreach ($SkillName in $SkillNames) {
    $SkillDir = Join-Path $TempDir $SkillName
    $ZipPath = Join-Path $OutputDir "$SkillName.zip"
    
    if (-not (Test-Path $SkillDir)) {
        continue
    }
    
    # Remove old ZIP if exists
    if (Test-Path $ZipPath) {
        Remove-Item -Path $ZipPath -Force
    }
    
    # Create ZIP with all files in skill directory
    Compress-Archive -Path "$SkillDir\*" -DestinationPath $ZipPath -Force
    
    $ZipSize = [math]::Round((Get-Item $ZipPath).Length / 1KB, 1)
    Write-Host "  Created: $SkillName.zip ($ZipSize KB)" -ForegroundColor Green
}

# Cleanup temp directory
Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done! ZIP files saved to: $OutputDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "To import into Claude Desktop:" -ForegroundColor Yellow
Write-Host "  1. Open Claude Desktop" -ForegroundColor White
Write-Host "  2. Go to Settings > Customize > Skills" -ForegroundColor White
Write-Host "  3. Click 'Add Skill' > Upload ZIP file" -ForegroundColor White
Write-Host "  4. Select a ZIP file from: $OutputDir" -ForegroundColor White
