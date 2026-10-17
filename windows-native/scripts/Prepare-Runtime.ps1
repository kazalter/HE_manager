param([Parameter(Mandatory=$true)][string]$Archive)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$lock=Get-Content "$root/runtime-lock/dependencies.json" -Raw | ConvertFrom-Json
if((Get-FileHash $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.libmpv.sha256){throw 'libmpv archive SHA256 mismatch'}
New-Item "$root/.runtime" -ItemType Directory -Force | Out-Null
& tar.exe -xf $Archive -C "$root/.runtime"
if($LASTEXITCODE){throw 'Archive extraction failed. Extract the locked archive with 7-Zip and retry.'}
if((Get-FileHash "$root/.runtime/libmpv-2.dll" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.libmpv.dllSha256){throw 'libmpv DLL SHA256 mismatch'}
$repo=Split-Path $root -Parent
Copy-Item "$repo/desktop/resources/test/sample.mp4" "$root/resources/sample.mp4" -Force
Copy-Item "$repo/desktop/resources/shaders" "$root/resources" -Recurse -Force
Copy-Item "$repo/desktop/resources/licenses" "$root/resources" -Recurse -Force
