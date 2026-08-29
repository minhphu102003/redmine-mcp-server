# install-skills-claude-desktop.ps1
# Create ZIP files for each skill for Claude Desktop import
# Usage: irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1

$ErrorActionPreference = "Stop"

$RepoOwner = "minhphu102003"
$RepoName = "redmine-mcp-server"
$Branch = "develop"
$RawBase = "https://raw.githubusercontent.com/$RepoOwner/$RepoName/$Branch"
$ApiBase = "https://api.github.com/repos/$RepoOwner/$RepoName/contents"
$OutputDir = "claude-desktop-skills"

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

    # Use GitHub Contents API to list all files in the skill directory
    $ApiUrl = "${ApiBase}/skills/${SkillName}?ref=${Branch}"
    try {
        $Response = Invoke-RestMethod -Uri $ApiUrl -UseBasicParsing
        foreach ($Item in $Response) {
            if ($Item.type -eq "file" -and $Item.name -match "\.md$") {
                $DownloadUrl = "$RawBase/skills/$SkillName/$($Item.name)"
                $DestPath = Join-Path $SkillDir $Item.name
                try {
                    Invoke-WebRequest -Uri $DownloadUrl -OutFile $DestPath -UseBasicParsing
                } catch {
                    Write-Host "  Warning: Could not download $($Item.name) for $SkillName" -ForegroundColor Yellow
                }
            }
        }
    } catch {
        Write-Host "  Warning: Could not list files for $SkillName" -ForegroundColor Yellow
    }

    # Verify SKILL.md was downloaded (required)
    if (-not (Test-Path (Join-Path $SkillDir "SKILL.md"))) {
        Write-Host "  ERROR: SKILL.md not found for $SkillName - skipping" -ForegroundColor Red
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

    $MdFiles = Get-ChildItem -Path $SkillDir -Filter "*.md"
    if ($MdFiles.Count -eq 0) {
        Write-Host "  Skipping $SkillName.zip (no .md files)" -ForegroundColor Yellow
        continue
    }

    # Remove old ZIP if exists
    if (Test-Path $ZipPath) {
        Remove-Item -Path $ZipPath -Force
    }

    # Create ZIP with all .md files in skill directory
    Compress-Archive -Path "$SkillDir\*.md" -DestinationPath $ZipPath -Force

    $ZipSize = [math]::Round((Get-Item $ZipPath).Length / 1KB, 1)
    $FileCount = $MdFiles.Count
    Write-Host "  Created: $SkillName.zip ($ZipSize KB, $FileCount files)" -ForegroundColor Green
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
