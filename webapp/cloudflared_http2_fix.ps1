# cloudflared_http2_fix.ps1
# Run as Administrator.  Switches the Cloudflare Tunnel connector(s) to HTTP/2
# (stable on this network) and adds a second connector for load balancing.
# The tunnel token is read from the existing Cloudflared service registry, so
# no secret needs to be typed.

$ErrorActionPreference = 'Stop'
$svc    = 'Cloudflared'
$cf     = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$task   = 'CloudflaredLB'
$svcKey = "HKLM:\SYSTEM\CurrentControlSet\Services\$svc"

if (-not (Test-Path $cf)) { throw "cloudflared not found: $cf" }

# 1) Recover the tunnel token from the service ImagePath in the registry.
$imgPath = (Get-ItemProperty -Path $svcKey -Name ImagePath -ErrorAction Stop).ImagePath
$tok = ($imgPath -replace '.*--token\s+([^\s"]+).*', '$1').Trim()
if ($tok.Length -lt 20) { throw 'Could not read the tunnel token from the service.' }

# 2) Reconfigure the existing service to use HTTP/2 (primary connector).
Write-Host "Stopping '$svc' ..."
sc.exe stop $svc 2>&1 | Out-Null
Start-Sleep -Seconds 2

$newBin = $imgPath -replace ' tunnel run ', ' tunnel --protocol http2 run '
Write-Host "Setting '$svc' ImagePath to HTTP/2 ..."
Set-ItemProperty -Path $svcKey -Name ImagePath -Value $newBin
$check = (Get-ItemProperty -Path $svcKey -Name ImagePath).ImagePath
if ($check -notmatch '--protocol http2') { throw 'ImagePath update did not take effect.' }

sc.exe start $svc
if ($LASTEXITCODE -ne 0) { throw "sc start failed for $svc" }

# 3) Add a second connector as a SYSTEM scheduled task (HTTP/2) for load
#    balancing / failover.
Write-Host "Creating scheduled task '$task' for the second connector ..."
$action    = New-ScheduledTaskAction -Execute $cf -Argument "tunnel --protocol http2 --no-autoupdate run --token $tok"
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $task

Start-Sleep -Seconds 3
Write-Host ""
Write-Host "Result:"
sc.exe query $svc 2>&1 | Select-String 'SERVICE_NAME|STATE'
Get-ScheduledTask -TaskName $task | Select-Object TaskName, State
Write-Host ""
Write-Host "Verify in Cloudflare Zero Trust -> Networks -> Tunnels:"
Write-Host "  - 2 connectors connected, both protocol HTTP/2, tunnel Healthy."
