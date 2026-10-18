param([string]$BuildTools='C:\HEManagerBuild\toolchain\BuildTools')
$ErrorActionPreference='Stop'
if(!(Test-Path (Join-Path $BuildTools 'VC\Auxiliary\Build\vcvars64.bat'))) {
    $vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if(!(Test-Path $vswhere)){throw 'MSVC 14.44 Build Tools are required'}
    $BuildTools=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
    if(!$BuildTools){throw 'MSVC toolchain was not found'}
}
$root=$PSScriptRoot
$download=Join-Path $root '.downloads'
$out=Join-Path $root 'build\win32-x64'
$runtime=Join-Path $root 'runtime\win32'
$lock=Get-Content "$root\header-lock.json" -Raw | ConvertFrom-Json
foreach($entry in $lock.files.PSObject.Properties){
    if((Get-FileHash "$root\include\mpv\$($entry.Name)" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value){throw "mpv header checksum mismatch: $($entry.Name)"}
}
New-Item $out,$runtime -ItemType Directory -Force | Out-Null
if((Get-FileHash "$download\electron-headers.tar.gz" -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'a53b3e7ecc1a3320b7dcbc7b7256e29a7c794e956349063b0e466c9e5c76d22b'){throw 'Electron header checksum mismatch'}
if((Get-FileHash "$download\node.lib" -Algorithm SHA256).Hash.ToLowerInvariant() -ne '221dac8b3f9e9e7cabb1e782c347399b24f0a68d0778e294ee34714c59d6446e'){throw 'Electron import library checksum mismatch'}
if((Get-FileHash "$download\libmpv-win.7z" -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'd6638b2b40561e6071627f39ad60a38e15721dc87a49f244b897911ea2edfd9f'){throw 'libmpv archive checksum mismatch'}
New-Item "$download\headers" -ItemType Directory -Force | Out-Null
tar -xzf "$download\electron-headers.tar.gz" -C "$download\headers"
if($LASTEXITCODE){throw 'Header extraction failed'}
# The hosted Windows tar does not always include an LZMA codec.
$sevenZip=(Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
if(!$sevenZip) {
    $candidate=Join-Path $env:ProgramFiles '7-Zip\7z.exe'
    if(Test-Path $candidate){$sevenZip=$candidate}
}
if($sevenZip){& $sevenZip x -y "-o$runtime" "$download\libmpv-win.7z" | Out-Null}
else {tar -xf "$download\libmpv-win.7z" -C $runtime}
if($LASTEXITCODE){throw 'libmpv extraction failed; install 7-Zip if tar lacks LZMA support'}
if((Get-FileHash "$runtime\libmpv-2.dll" -Algorithm SHA256).Hash.ToLowerInvariant() -ne '3c7dedc13718d9c3f38d41f9f2a1aed01810850982020f34f03b67a13b0659e8'){throw 'libmpv DLL checksum mismatch'}
$vcvars=Join-Path $BuildTools 'VC\Auxiliary\Build\vcvars64.bat'
cmd /d /s /c "`"$vcvars`" -vcvars_ver=14.44 10.0.26100.0 >nul && set" | ForEach-Object {if($_ -match '^([^=]+)=(.*)$'){[Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process')}}
if($LASTEXITCODE){throw 'MSVC setup failed'}
Push-Location $root
try {
    & cl.exe /nologo /std:c++17 /EHsc /LD /MT /O2 /DNAPI_VERSION=8 /DNODE_GYP_MODULE_NAME=he_embedded "/I$download\headers\node_headers\include\node" embedded.cpp delay-load.cpp "/Fo$out\" /link "/OUT:$out\he_embedded.node" "/IMPLIB:$out\he_embedded.lib" "$download\node.lib" d3d11.lib dxgi.lib delayimp.lib /DELAYLOAD:node.exe
    if($LASTEXITCODE){throw 'Native addon build failed'}
} finally {Pop-Location}
$sourceHashes=@{}
foreach($name in @('embedded.cpp','surface.h','delay-load.cpp','header-lock.json','build-windows.ps1')){$sourceHashes[$name]=(Get-FileHash "$root\$name" -Algorithm SHA256).Hash.ToLowerInvariant()}
@{platform='win32-x64';electron='44.8.0';nodeAPI=8;msvc=$env:VCToolsVersion.TrimEnd('\');compilerFileVersion=(Get-Item (Get-Command cl.exe).Source).VersionInfo.FileVersion;windowsSdk='10.0.26100.0';sourceSha256=$sourceHashes;addonSha256=(Get-FileHash "$out\he_embedded.node" -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Depth 4 | Set-Content "$out\build-info.json" -Encoding UTF8
Write-Output "Built $out\he_embedded.node"
