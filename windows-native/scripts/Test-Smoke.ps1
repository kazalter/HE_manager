param([string]$Executable=(Join-Path (Split-Path $PSScriptRoot -Parent) '.artifacts/x64/HEManager.Windows.exe'),[int]$TimeoutSeconds=180)
$ErrorActionPreference='Stop'
if(Get-Process HEManager.Windows -ErrorAction SilentlyContinue){throw 'Close the existing prototype before running the smoke probe.'}
$report=Join-Path $env:LOCALAPPDATA 'HEManager/WN01'
if(Test-Path "$report/smoke.json"){Remove-Item "$report/smoke.json"}
$task='HEManager-WN01-'+[guid]::NewGuid().ToString('N')
$principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$action=New-ScheduledTaskAction -Execute $Executable -Argument '--smoke' -WorkingDirectory (Split-Path $Executable)
try {
    Register-ScheduledTask -TaskName $task -Action $action -Principal $principal | Out-Null
    Start-ScheduledTask $task
    $until=(Get-Date).AddSeconds($TimeoutSeconds)
    do {Start-Sleep -Milliseconds 500;$state=(Get-ScheduledTask $task).State} while($state -in @('Running','Queued') -and (Get-Date) -lt $until)
    if($state -in @('Running','Queued')){throw 'Smoke probe timed out; inspect player.log and the running prototype.'}
    if((Get-ScheduledTaskInfo $task).LastTaskResult -ne 0){throw 'Prototype process failed'}
    if(!(Test-Path "$report/smoke.json")){throw 'No completed smoke report'}
    $data=Get-Content "$report/smoke.json" -Raw | ConvertFrom-Json
    if(@($data.session | Select-Object -Unique).Count -ne 1){throw 'Playback session was recreated'}
    if(@($data | Where-Object graphicsError -ne 0).Count){throw 'D3D11 render failure'}
    if($data[-1].frames -le $data[0].frames){throw 'Frames did not advance'}
    $beforeReload=$data | Where-Object tick -eq 180
    $afterReload=$data | Where-Object tick -ge 200 | Select-Object -Last 1
    if(!$beforeReload -or !$afterReload -or $afterReload.frames -le $beforeReload.frames -or [double]::Parse($afterReload.time,[Globalization.CultureInfo]::InvariantCulture) -lt 0.5){throw 'Reloaded video did not advance frames and position'}
    if(@($data | Where-Object pixelSpread -gt 32).Count -lt 3){throw 'GPU texture readback lacks nonblank video evidence'}
    foreach($mode in @('off','efficiency','quality')){
        $group=@($data | Where-Object preset -eq $mode)
        if(!$group.Count){throw "Missing preset: $mode"}
        if($mode -eq 'off'){
            if(@($group | Where-Object {($_.passes -join ';') -match 'Anime4K'}).Count){throw 'Original mode retained Anime4K passes'}
        } else {
            $pattern=if($mode -eq 'efficiency'){'*Restore-CNN-(M)*'}else{'*Restore-CNN-(VL)*'}
            if(!@($group | Where-Object {($_.passes -join ';') -like $pattern}).Count){throw "No matching active Anime4K render pass evidence: $mode"}
        }
    }
    if(!@($data | Where-Object {$_.hwdec -eq 'd3d11va'}).Count){throw 'No hardware decode evidence'}
    if(!@($data | Where-Object fullscreen -eq $true).Count){throw 'No fullscreen observation'}
    $log=Get-Content "$report/player.log" -Raw
    if(([regex]::Matches($log,'fullscreen=True;')).Count -ne 20){throw 'Expected 20 fullscreen/restore cycles'}
    if($log -match 'video output initialization failed|Stop did not become idle|System\..*Exception'){throw 'Playback/lifecycle failure in log'}
    $steady=$log.Substring($log.IndexOf('fullscreen=True;'))
    if($steady -match 'not being called or stuck|mpv_render_report_swap\(\) not being called'){throw 'Render stalls persisted after shader warmup'}
    $coldWarnings=([regex]::Matches($log,'not being called')).Count
    Write-Output "Cold shader compilation timing warnings: $coldWarnings; full performance acceptance remains pending."
    if($log -notmatch 'shutdown complete'){throw 'Missing clean shutdown'}
    if(Get-Process HEManager.Windows -ErrorAction SilentlyContinue){throw 'Prototype process remained after exit'}
    Write-Output "PASS: embedded D3D11 frames, GPU readback, hardware decode, active Anime4K passes, 20 same-session fullscreen cycles, video reload and clean exit. Evidence: $report"
} finally {Unregister-ScheduledTask $task -Confirm:$false -ErrorAction SilentlyContinue}
