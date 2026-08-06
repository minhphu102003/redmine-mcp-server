param(
    [string]$Target = "",
    [string]$Repo = "minhphu102003/redmine-mcp-server",
    [string]$Branch = "develop"
)

$ErrorActionPreference = "Stop"

$skills = @("redmine-init", "redmine-issue-workflow")

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
        Write-Host "Installed: $destFile (local copy)"
    } else {
        $url = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}/SKILL.md" -f $Repo, $Branch, $skill
        try {
            Invoke-WebRequest -Uri $url -OutFile $destFile
            Write-Host "Installed: $destFile (from $url)"
        } catch {
            throw "Failed to download skill '$skill' from $url. Check that the repo is public and the branch exists."
        }
    }
}

Write-Host ""
Write-Host "Skills installed into: $destRoot"
Write-Host "opencode and Claude Code / Agent SDK auto-scan .agents/skills/. You are free to move the folders anywhere else."
