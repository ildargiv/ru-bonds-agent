# Установка агента «Облигационер» в Claude Code / Codex CLI на Windows (без WSL).
#   powershell -ExecutionPolicy Bypass -File install.ps1 claude
#   powershell -ExecutionPolicy Bypass -File install.ps1 codex
# Для Hermes Agent используйте install.sh в WSL.
param([ValidateSet("claude", "codex")][string]$Target = "claude")
$ErrorActionPreference = "Stop"
$Src = Join-Path $PSScriptRoot "skills\finance\ru-bonds"

function Copy-Skill($Dest) {
    New-Item -ItemType Directory -Force (Split-Path $Dest) | Out-Null
    if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
    Copy-Item -Recurse $Src $Dest
    Write-Host "Навык -> $Dest"
}

if ($Target -eq "claude") {
    Copy-Skill (Join-Path $HOME ".claude\skills\ru-bonds")
    $agents = Join-Path $HOME ".claude\agents"
    New-Item -ItemType Directory -Force $agents | Out-Null
    Copy-Item (Join-Path $PSScriptRoot "agents\claude-code\bonds.md") (Join-Path $agents "bonds.md") -Force
    Write-Host "Субагент -> $agents\bonds.md. Перезапустите сессию Claude Code."
} else {
    Copy-Skill (Join-Path $HOME ".codex\skills\ru-bonds")
    Write-Host "Перезапустите сессию Codex."
}
try { python -m pip install --user --quiet pypdf } catch { Write-Host "Для чтения PDF: pip install pypdf" }
