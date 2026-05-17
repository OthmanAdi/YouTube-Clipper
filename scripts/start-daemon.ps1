# start-daemon.ps1 — load secrets, set config path, run uvicorn on 127.0.0.1:7777.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

# Load .secrets.env into process env.
$secretsFile = "$repoRoot\config\.secrets.env"
if (Test-Path $secretsFile) {
    Get-Content $secretsFile | ForEach-Object {
        if ($_ -match "^\s*#") { return }
        if ($_ -match "^\s*$") { return }
        $kv = $_.Split("=", 2)
        if ($kv.Length -eq 2) {
            $name = $kv[0].Trim()
            $val  = $kv[1].Trim().Trim('"').Trim("'")
            Set-Item -Path "env:$name" -Value $val
        }
    }
} else {
    Write-Warning "config\.secrets.env not found. Azure summarizer will fail until you create it (or disable Azure in config.toml)."
}

$env:YTCLIPPER_CONFIG = "$repoRoot\config\config.toml"

Push-Location "$repoRoot\apps\daemon"
try {
    Write-Host "==> daemon: http://127.0.0.1:7777"
    Write-Host "    config: $env:YTCLIPPER_CONFIG"
    Write-Host "    Ctrl+C to stop."
    uv run uvicorn youtube_clipper.api.app:app --host 127.0.0.1 --port 7777 --log-level warning
} finally { Pop-Location }
