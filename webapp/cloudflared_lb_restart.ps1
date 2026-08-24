# cloudflared_lb_restart.ps1
# Run as Administrator.  Adds an "on failure, retry every 30s, effectively
# unlimited" restart policy to the CloudflaredLB scheduled task (the second
# tunnel connector).  Uses the task XML so the token in the action is preserved.

$ErrorActionPreference = 'Stop'
$task  = 'CloudflaredLB'
$NSURI = 'http://schemas.microsoft.com/windows/2004/02/mit/task'

$taskXml = Export-ScheduledTask -TaskName $task
if (-not $taskXml) { throw "Scheduled task '$task' not found." }

[xml]$doc = $taskXml
$ns = New-Object System.Xml.XmlNamespaceManager($doc.NameTable)
$ns.AddNamespace('t', $NSURI)

$settings = $doc.SelectSingleNode('//t:Settings', $ns)
if (-not $settings) { throw 'Settings element not found in the task XML.' }

# Remove any existing RestartOnFailure, then insert a fresh one (schema order:
# RestartOnFailure comes before NetworkSettings).
$existing = $settings.SelectSingleNode('t:RestartOnFailure', $ns)
if ($existing) { [void]$settings.RemoveChild($existing) }

# NOTE: the Windows Task Scheduler enforces a minimum restart interval of 1
# minute (PT1M); values below that (e.g. PT30S) are rejected as out of range.
$restart   = $doc.CreateElement('RestartOnFailure', $NSURI)
$interval  = $doc.CreateElement('Interval', $NSURI);  $interval.InnerText  = 'PT1M'
$count     = $doc.CreateElement('Count', $NSURI);     $count.InnerText     = '2147483647'
[void]$restart.AppendChild($interval)
[void]$restart.AppendChild($count)

$network = $settings.SelectSingleNode('t:NetworkSettings', $ns)
if ($network) { [void]$settings.InsertBefore($restart, $network) }
else          { [void]$settings.AppendChild($restart) }

Register-ScheduledTask -TaskName $task -Xml $doc.OuterXml -Force | Out-Null
Start-ScheduledTask -TaskName $task

Start-Sleep -Seconds 2
Write-Host "Updated. Task state:"
Get-ScheduledTask -TaskName $task | Select-Object TaskName, State
Write-Host ""
Write-Host "Restart policy: on failure, retry every 1 minute (Task Scheduler minimum), effectively unlimited (Count=2147483647)."
