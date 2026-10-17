param([string]$Toolchain='C:\HEManagerBuild\toolchain',[switch]$Locked)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$dotnet=Join-Path $Toolchain 'dotnet/dotnet.exe'
$env:DOTNET_ROOT=Split-Path $dotnet
$env:PATH="$env:DOTNET_ROOT;$env:PATH"
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
if(!(Test-Path "$root/.runtime/libmpv-2.dll")){throw 'Run Prepare-Runtime.ps1 first'}
$lock=Get-Content "$root/runtime-lock/dependencies.json" -Raw | ConvertFrom-Json
if((Get-FileHash "$root/.runtime/libmpv-2.dll" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.libmpv.dllSha256){throw 'libmpv DLL SHA256 mismatch'}
foreach($file in $lock.files.PSObject.Properties){
    if((Get-FileHash (Join-Path $root $file.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value){throw "Resource SHA256 mismatch: $($file.Name)"}
}
Push-Location $root
try {
    $out=Join-Path $root '.artifacts/x64'
    New-Item $out -ItemType Directory -Force | Out-Null
    $vcvars=Join-Path $Toolchain 'BuildTools/VC/Auxiliary/Build/vcvars64.bat'
    if(!(Test-Path $vcvars)){throw "Missing MSVC environment: $vcvars"}
    # Import the compiler environment for this process only.
    cmd /d /s /c "`"$vcvars`" -vcvars_ver=14.44 10.0.26100.0 >nul && set" | ForEach-Object {if($_ -match '^([^=]+)=(.*)$'){[Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process')}}
    & cl.exe /nologo /std:c++17 /EHsc /LD /MT /O2 HEManager.Graphics/Bridge.cpp /Fo"$out/Bridge.obj" /link /OUT:"$out/HEManager.Graphics.dll" d3d11.lib dxgi.lib
    if($LASTEXITCODE){throw 'C++ graphics bridge build failed'}
    $restoreArgs=@('restore','HEManager.Windows/HEManager.Windows.csproj','-p:Platform=x64')
    if($Locked){$restoreArgs+='--locked-mode'}
    & $dotnet @restoreArgs
    if($LASTEXITCODE){throw 'NuGet restore failed'}
    & $dotnet build HEManager.Windows/HEManager.Windows.csproj -c Release -p:Platform=x64 --no-restore -o "$out"
    if($LASTEXITCODE){throw 'WinUI build failed'}
    Copy-Item "$root/.runtime/libmpv-2.dll" $out -Force
    & "$PSScriptRoot/Write-BuildInfo.ps1" -Root $root -Output $out
    Write-Output "Built: $out/HEManager.Windows.exe"
} finally {Pop-Location}
