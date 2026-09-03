# install-skills-claude-desktop.ps1
# NOTE: keep this file ASCII-only with NO BOM. raw.githubusercontent.com
# serves the BOM through to 'irm', and Windows PowerShell 5.1 then fails
# to parse the param() block when the script is run via 'irm ... | iex'.
# Create ZIP files for each skill for Claude Desktop import
# Usage: irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1

$ErrorActionPreference = "Stop"

$RepoOwner = "minhphu102003"
$RepoName = "redmine-mcp-server"
$Branch = "develop"
$RawBase = "https://raw.githubusercontent.com/${RepoOwner}/${RepoName}/${Branch}"
$ApiBase = "https://api.github.com/repos/${RepoOwner}/${RepoName}/contents"
$OutputDir = "claude-desktop-skills"

# Skills list for Claude Desktop (QA-focused + boss oversight)
$SkillNames = @(
    "redmine-init",
    "testcase-generation",
    "bug-reporting",
    "bug-to-redmine",
    "status-sync",
    "reopen-bug",
    "boss-project-oversight"
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
        $WebResponse = Invoke-WebRequest -Uri $ApiUrl -UseBasicParsing
        $JsonContent = $WebResponse.Content
        $Response = ConvertFrom-Json -InputObject $JsonContent
        # Boss-only: also ship the widget template (.html) with the skill.
        $wantHtml = $SkillName -eq "boss-project-oversight"
        foreach ($Item in $Response) {
            if ($Item.type -ne "file") { continue }
            $isMd = $Item.name -match "\.md$" -and $Item.name -ne "README.md"
            $isHtml = $wantHtml -and $Item.name -like "*.html" -and $Item.name -notlike "README.*"
            if (-not ($isMd -or $isHtml)) { continue }
            $DownloadUrl = "${RawBase}/skills/${SkillName}/$($Item.name)"
            $DestPath = Join-Path $SkillDir $Item.name
            try {
                Invoke-WebRequest -Uri $DownloadUrl -OutFile $DestPath -UseBasicParsing
            } catch {
                Write-Host "  Warning: Could not download $($Item.name) for $SkillName" -ForegroundColor Yellow
            }
        }
    } catch {
        Write-Host "  Warning: Could not list files for $SkillName - $_" -ForegroundColor Yellow
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
    $HtmlFiles = @()
    if ($SkillName -eq "boss-project-oversight") {
        $HtmlFiles = @(Get-ChildItem -Path $SkillDir -Filter "*.html")
    }
    if ($MdFiles.Count -eq 0) {
        Write-Host "  Skipping $SkillName.zip (no .md files)" -ForegroundColor Yellow
        continue
    }

    # Remove old ZIP if exists
    if (Test-Path $ZipPath) {
        Remove-Item -Path $ZipPath -Force
    }

    # Create ZIP with all .md files (plus the boss widget template if present)
    $zipPaths = @("$SkillDir\*.md")
    if ($HtmlFiles.Count -gt 0) { $zipPaths += "$SkillDir\*.html" }
    Compress-Archive -Path $zipPaths -DestinationPath $ZipPath -Force

    $ZipSize = [math]::Round((Get-Item $ZipPath).Length / 1KB, 1)
    $FileCount = $MdFiles.Count + $HtmlFiles.Count
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
