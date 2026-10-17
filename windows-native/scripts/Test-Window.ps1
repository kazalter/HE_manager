param([ValidateSet('ui','patterns','scales','soak')][string]$Mode='ui',[int]$Seconds=1800,[string]$Toolchain='C:\HEManagerBuild\toolchain')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if(Get-Process HEManager.Windows -ErrorAction SilentlyContinue){throw 'Close the current prototype before testing.'}
$env:DOTNET_ROOT=Join-Path $Toolchain 'dotnet'
Push-Location $root
try {
    & "$env:DOTNET_ROOT/dotnet.exe" build HEManager.UITests/HEManager.UITests.csproj -c Release -o .artifacts/uitests
    if($LASTEXITCODE){throw 'UI test build failed'}
    $runner=Join-Path $root '.artifacts/Run-UIProbe.ps1'
    $log=Join-Path $root ".artifacts/window-test-$Mode.log"
    # These arguments contain only workspace paths and test mode; no user tokens.
    $testExe=Join-Path $root '.artifacts/uitests/HEManager.UITests.exe'
    $appExe=Join-Path $root '.artifacts/x64/HEManager.Windows.exe'
    $escapedTest=$testExe.Replace("'","''");$escapedApp=$appExe.Replace("'","''");$escapedLog=$log.Replace("'","''")
    "& '$escapedTest' '$escapedApp' $Mode $Seconds *> '$escapedLog'`nexit `$LASTEXITCODE" | Set-Content $runner -Encoding UTF8
    $task='HEManager-WN01-Window-'+[guid]::NewGuid().ToString('N')
    $action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
    $principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    try {
        Register-ScheduledTask -TaskName $task -Action $action -Principal $principal | Out-Null
        Start-ScheduledTask $task
        $until=(Get-Date).AddSeconds($(if($Mode -in @('soak','scales')){$Seconds+120}else{300}))
        do {Start-Sleep -Milliseconds 500;$state=(Get-ScheduledTask $task).State} while($state -in @('Running','Queued') -and (Get-Date) -lt $until)
        if($state -in @('Running','Queued')){throw "Window test timed out: $log"}
        Get-Content $log
        if((Get-ScheduledTaskInfo $task).LastTaskResult -ne 0){throw "Window test failed: $log"}
    } finally {Unregister-ScheduledTask $task -Confirm:$false -ErrorAction SilentlyContinue}
} finally {Pop-Location}
