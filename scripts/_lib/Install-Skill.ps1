# Install-Skill.ps1
# Shared helpers for install-skills*.ps1 scripts.
# NOTE: keep this file ASCII-only (no em-dash, no smart-quote) so it parses
# correctly via 'irm ... | iex' on Windows PowerShell 5.1, which can strip
# BOM from raw.githubusercontent.com responses.
# Both functions:
#   - Always copy SKILL.md (entry point).
#   - Always copy every *.md file in the skill folder EXCEPT README.md
#     (README is a meta-doc, not a skill payload).
#   - Skip silently if the source folder is empty (caller decides what to do).

function Install-SkillFromLocal {
    param(
        [Parameter(Mandatory)] [string]$SkillName,
        [Parameter(Mandatory)] [string]$SourceDir,
        [Parameter(Mandatory)] [string]$DestDir
    )

    if (-not (Test-Path -LiteralPath $SourceDir)) {
        throw "Source skill folder not found: $SourceDir"
    }

    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null

    $skillMd = Join-Path $SourceDir "SKILL.md"
    if (-not (Test-Path -LiteralPath $skillMd)) {
        throw "SKILL.md not found in $SourceDir -- cannot install '$SkillName'"
    }
    Copy-Item -Path $skillMd -Destination (Join-Path $DestDir "SKILL.md") -Force

    $extra = Get-ChildItem -Path $SourceDir -Filter "*.md" -File |
        Where-Object { $_.Name -ne "SKILL.md" -and $_.Name -ne "README.md" }
    foreach ($f in $extra) {
        Copy-Item -Path $f.FullName -Destination $DestDir -Force
    }
}

function Install-SkillFromGitHub {
    param(
        [Parameter(Mandatory)] [string]$SkillName,
        [Parameter(Mandatory)] [string]$Repo,
        [Parameter(Mandatory)] [string]$Branch,
        [Parameter(Mandatory)] [string]$DestDir,
        [string]$GitHubToken = $env:GITHUB_TOKEN
    )

    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null

    $apiUrl = "https://api.github.com/repos/{0}/contents/skills/{1}?ref={2}" -f $Repo, $SkillName, $Branch
    $headers = @{}
    if ($GitHubToken) { $headers["Authorization"] = "token $GitHubToken" }

    try {
        $response = Invoke-WebRequest -Uri $apiUrl -Headers $headers -UseBasicParsing |
            ConvertFrom-Json
    } catch {
        throw "Failed to list files for skill '$SkillName' at $apiUrl -- $_"
    }

    if ($null -eq $response -or $response.Count -eq 0) {
        throw "No files found for skill '$SkillName' at $apiUrl"
    }

    $rawBase = "https://raw.githubusercontent.com/{0}/{1}/skills/{2}" -f $Repo, $Branch, $SkillName
    foreach ($item in $response) {
        if ($item.type -ne "file") { continue }
        if ($item.name -notmatch "\.md$") { continue }
        if ($item.name -eq "README.md") { continue }
        $raw = "$rawBase/$($item.name)"
        $out = Join-Path $DestDir $item.name
        try {
            Invoke-WebRequest -Uri $raw -OutFile $out -UseBasicParsing | Out-Null
        } catch {
            Write-Warning "Failed to download $raw"
        }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $DestDir "SKILL.md"))) {
        throw "SKILL.md missing for '$SkillName' after install -- skill install failed"
    }
}
