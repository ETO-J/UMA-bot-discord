# cloudflared_lb_watchdog_setup.ps1
# Run as Administrator.  Replaces the CloudflaredLB scheduled task so it runs
# the watchdog loop (30s, unlimited connector restarts) instead of running
# cloudflared directly.  The task itself also gets a 1-minute / 99-retry
# safety net in case the watchdog script ever dies.

$ErrorActionPreference = 'Stop'
$task     = 'CloudflaredLB'
$watchdog = 'C:\Users\Administrator\bpdiscord\webapp\cloudflared_lb_watchdog.ps1'

if (-not (Test-Path $watchdog)) { throw "Watchdog script not found: $watchdog" }

# Stop the existing task so its cloudflared process is replaced cleanly.
Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdog`""
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $task

Start-Sleep -Seconds 3
Write-Host "Watchdog task installed. State:"
Get-ScheduledTask -TaskName $task | Select-Object TaskName, State
Write-Host ""
Write-Host "The task now runs the watchdog loop: connector restarts every 30s, indefinitely."
Write-Host "Task-level fallback: restart every 1 minute, up to 99 times (only if the watchdog itself dies)."
