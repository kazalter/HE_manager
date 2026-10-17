"""Assemble official Electron binaries; preserve all framework links and verify hashes."""
import pathlib,json,hashlib,urllib.request,shutil,zipfile,stat,os,sys,plistlib
root=pathlib.Path(__file__).resolve().parents[1]
platform=sys.argv[1];arch='arm64' if platform=='darwin' else 'x64'
version=json.loads((root/'node_modules/electron/package.json').read_text())['version']
name=f'electron-v{version}-{platform}-{arch}.zip'
expected=json.loads((root/'node_modules/electron/checksums.json').read_text())[name]
archive=root/'.downloads'/name
if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
    temporary=archive.with_suffix('.partial')
    with urllib.request.urlopen(f'https://github.com/electron/electron/releases/download/v{version}/{name}',timeout=90) as response,temporary.open('wb') as output:shutil.copyfileobj(response,output)
    if hashlib.sha256(temporary.read_bytes()).hexdigest()!=expected:raise RuntimeError('Electron checksum mismatch')
    temporary.replace(archive)
output=root/'release'/f'HE Manager-{platform}-{arch}'
if output.exists():shutil.rmtree(output)
output.mkdir(parents=True)
with zipfile.ZipFile(archive) as zipped:
    for info in zipped.infolist():
        relative=pathlib.PurePosixPath(info.filename)
        if relative.is_absolute() or '..' in relative.parts:raise RuntimeError('Unsafe Electron archive path')
        target=output/info.filename
        mode=info.external_attr>>16
        if stat.S_ISLNK(mode):
            target.parent.mkdir(parents=True,exist_ok=True)
            link=zipped.read(info).decode()
            if os.path.isabs(link):raise RuntimeError('Unsafe absolute symlink')
            os.symlink(link,target)
        else:
            zipped.extract(info,output)
            if target.is_file() and mode:target.chmod(mode&0o777)
if platform=='darwin':
    app=output/'HE Manager.app'
    (output/'Electron.app').rename(app)
    (app/'Contents/MacOS/Electron').rename(app/'Contents/MacOS/HE Manager')
    plist=app/'Contents/Info.plist'
    data=plistlib.loads(plist.read_bytes())
    data.update(CFBundleExecutable='HE Manager',CFBundleName='HE Manager',CFBundleDisplayName='HE Manager',CFBundleIdentifier='com.kaz.he-manager',CFBundleShortVersionString='0.1.0',CFBundleVersion='0.1.0',CFBundleIconFile='he.icns',NSLocalNetworkUsageDescription='HE Manager 需要连接你指定的局域网媒体服务器，读取媒体库并播放内容。')
    plist.write_bytes(plistlib.dumps(data))
    shutil.copy2(root/'resources/icons/he.icns',app/'Contents/Resources/he.icns')
else:(output/'electron.exe').rename(output/'HE Manager.exe')
print('Verified and assembled',name,flush=True)
