# stop-daemon.ps1 — find whatever owns TCP/7777 and stop it.

$ErrorActionPreference = "Stop"

$pids = Get-NetTCPConnection -LocalPort 7777 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
if ($pids) {
    foreach ($procId in $pids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "Stopped daemon (PID $procId)"
        } catch {
            Write-Warning "Failed to stop PID $procId : $_"
        }
    }
} else {
    Write-Host "Daemon not running on port 7777."
}
