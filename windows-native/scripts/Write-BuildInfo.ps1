param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$files=[ordered]@{}
$hash=[Security.Cryptography.SHA256]::Create()
try {
    foreach($project in @('HEManager.Windows','HEManager.Core','HEManager.Media','HEManager.Graphics')){
        Get-ChildItem (Join-Path $Root $project) -File -Recurse | Where-Object {$_.FullName -notmatch '[\\/](obj|bin)[\\/]' -and $_.Extension -in @('.cs','.cpp','.h','.xaml','.csproj','.manifest','.json')} | Sort-Object FullName | ForEach-Object {
            $relative=$_.FullName.Substring($Root.Length+1).Replace('\','/')
            $bytes=[IO.File]::ReadAllBytes($_.FullName)
            if($_.Extension -ne '.h'){$bytes=[Text.Encoding]::UTF8.GetBytes([Text.Encoding]::UTF8.GetString($bytes).Replace("`r`n","`n"))}
            $files[$relative]=[BitConverter]::ToString($hash.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()
        }
    }
    $binaries=[ordered]@{}
    foreach($name in @('HEManager.Windows.dll','HEManager.Core.dll','HEManager.Media.dll','HEManager.Graphics.dll','libmpv-2.dll')){$binaries[$name]=(Get-FileHash (Join-Path $Output $name) -Algorithm SHA256).Hash.ToLowerInvariant()}
    [ordered]@{builtAtUtc=[DateTimeOffset]::UtcNow.ToString('O');msvc=$env:VCToolsVersion;windowsSdk=$env:WindowsSDKVersion;sources=$files;binaries=$binaries} | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Output 'build-info.json') -Encoding UTF8
} finally {$hash.Dispose()}
