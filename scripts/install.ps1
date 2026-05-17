# install.ps1 — Bootstrap YouTube-Clipper from a clean checkout.
# Idempotent: re-runs are safe.
#
# Security notes:
#   - npm install runs with --ignore-scripts to defang post-install hooks
#     (defense against npm supply-chain worms like Shai-Hulud).
#   - All dependencies are pinned to exact versions in package.json /
#     package-lock.json. Run `npm audit` after install to see any CVEs.
#
# Requires:  uv, npm, ffmpeg, yt-dlp on PATH (or paths in config/config.toml).
#            Python 3.11/3.12 picked automatically by uv.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==> YouTube-Clipper install"
Write-Host "    repo: $repoRoot"
Write-Host ""

# ---- Daemon (Python) ----
Write-Host "==> Daemon: uv sync"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
}
Push-Location "$repoRoot\apps\daemon"
try {
    uv sync --extra dev
    Write-Host "    daemon deps OK"
} finally { Pop-Location }
Write-Host ""

# ---- Extension (Node/TS) ----
Write-Host "==> Extension: npm ci --ignore-scripts (worm-safe install)"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not found. Install Node 20+."
}
# Strip GH/NPM tokens from this process so a compromised post-install couldn't grab them.
$env:GH_TOKEN = $null
$env:NPM_TOKEN = $null
Push-Location "$repoRoot\apps\extension"
try {
    if (Test-Path "package-lock.json") {
        npm ci --ignore-scripts --no-audit --loglevel=warn
    } else {
        npm install --ignore-scripts --no-audit --loglevel=warn
    }
    Write-Host "    extension deps OK"

    Write-Host "==> Extension: npm audit (informational)"
    npm audit --audit-level=high --no-fund

    Write-Host "==> Extension: build"
    npm run build
} finally { Pop-Location }
Write-Host ""

# ---- Tool sanity ----
Write-Host "==> Checking tool dependencies on PATH"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "ffmpeg not on PATH. Either add it to PATH or set [paths] ffmpeg_bin in config/config.toml."
} else { Write-Host "    ffmpeg OK" }
if (-not (Get-Command yt-dlp -ErrorAction SilentlyContinue)) {
    Write-Warning "yt-dlp not on PATH. Either add it to PATH or set [paths] yt_dlp_bin in config/config.toml."
} else { Write-Host "    yt-dlp OK" }
Write-Host ""

# ---- Secrets ----
$secretsExample = "$repoRoot\config\.secrets.env.example"
$secretsFile    = "$repoRoot\config\.secrets.env"
if (-not (Test-Path $secretsFile)) {
    Write-Host "==> Creating config\.secrets.env from template"
    Copy-Item $secretsExample $secretsFile
    Write-Warning "Edit config\.secrets.env to set AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_KEY (or disable Azure in config.toml)."
} else {
    Write-Host "==> config\.secrets.env already exists, leaving untouched"
}
Write-Host ""

# ---- Final message ----
Write-Host "==> install complete"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit config\.secrets.env (Azure values), OR set [summarizer.azure] enabled=false in config\config.toml."
Write-Host "  2. (Optional) ollama pull qwen2.5:14b   if you'll use Ollama."
Write-Host "  3. scripts\start-daemon.ps1"
Write-Host "  4. Chrome -> chrome://extensions/ -> Developer mode -> Load unpacked -> select apps\extension\dist"
