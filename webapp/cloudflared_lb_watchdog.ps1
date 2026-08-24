# cloudflared_lb_watchdog.ps1
# Runs the second tunnel connector (HTTP/2) in a loop.  When the connector
# process exits, it waits 30 seconds and restarts it, indefinitely.  The token
# is read from the Cloudflared service so no secret is stored here.

$ErrorActionPreference = 'Continue'
$cf      = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$svcKey  = 'HKLM:\SYSTEM\CurrentControlSet\Services\Cloudflared'

try {
    $token = ((Get-ItemProperty -Path $svcKey -Name ImagePath -ErrorAction Stop).ImagePath -replace '.*--token\s+([^\s"]+).*', '$1').Trim()
} catch {
    $token = ''
}

while ($true) {
    if (-not (Test-Path $cf) -or $token.Length -lt 20) {
        Start-Sleep -Seconds 30
        continue
    }
    $p = Start-Process -FilePath $cf -ArgumentList "tunnel --protocol http2 --no-autoupdate run --token $token" -WindowStyle Hidden -PassThru
    if ($p) { $p.WaitForExit() }
    Start-Sleep -Seconds 30
}
