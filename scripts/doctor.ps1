# doctor.ps1 — diagnose YouTube-Clipper bootstrap state.
# Exits 0 iff every probe is green.

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$rows = New-Object System.Collections.Generic.List[object]

function Probe($name, $script) {
    try {
        $detail = & $script
        $rows.Add([PSCustomObject]@{ check = $name; status = "OK";   detail = ("$detail" -replace "\r?\n.*", "") })
    } catch {
        $rows.Add([PSCustomObject]@{ check = $name; status = "FAIL"; detail = $_.Exception.Message })
    }
}

Probe "ffmpeg"              { (& ffmpeg -version 2>$null | Select-Object -First 1) }
Probe "yt-dlp"              { (& yt-dlp --version 2>$null) }
Probe "uv"                  { (& uv --version 2>$null) }
Probe "node"                { (& node --version 2>$null) }
Probe "npm"                 { (& npm --version 2>$null) }
Probe "config.toml present" { if (Test-Path "$repoRoot\config\config.toml") { "yes" } else { throw "missing $repoRoot\config\config.toml" } }
Probe ".secrets.env present"{ if (Test-Path "$repoRoot\config\.secrets.env") { "yes" } else { throw "missing $repoRoot\config\.secrets.env (copy .secrets.env.example)" } }
Probe "extension dist built"{
    $dist = "$repoRoot\apps\extension\dist"
    if (-not (Test-Path "$dist\manifest.json")) { throw "extension not built — run scripts/install.ps1 or `npm run build` in apps/extension" }
    "yes"
}
Probe "daemon venv"         {
    if (-not (Test-Path "$repoRoot\apps\daemon\.venv")) { throw "daemon venv missing — run scripts/install.ps1" }
    "yes"
}
Probe "daemon /health"      {
    try {
        $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:7777/health" -TimeoutSec 2
        if ($r.StatusCode -ne 200) { throw "status $($r.StatusCode)" }
        ($r.Content -replace "[\r\n]+"," ").Substring(0,[Math]::Min(60,$r.Content.Length))
    } catch {
        throw "not running — start with scripts/start-daemon.ps1"
    }
}
Probe "ollama reachable"    {
    try {
        # 127.0.0.1 explicitly — PowerShell resolves 'localhost' to ::1 first on Windows
        # and Ollama by default only binds IPv4.
        $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:11434/api/version" -TimeoutSec 3
        if ($r.StatusCode -ne 200) { throw "status $($r.StatusCode)" }
        $r.Content
    } catch {
        throw "ollama not reachable on 127.0.0.1:11434 (only needed if you'll use the Ollama summarizer)"
    }
}

$rows | Format-Table -AutoSize

$bad = $rows | Where-Object { $_.status -eq "FAIL" }
if ($bad) {
    Write-Host ""
    Write-Host "Some checks failed. See the FAIL rows above." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host ""
    Write-Host "All green." -ForegroundColor Green
    exit 0
}
