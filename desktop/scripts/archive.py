"""Portable ZIPs retaining executable bits and macOS framework symlinks."""
import os,pathlib,stat,sys,zipfile
source=pathlib.Path(sys.argv[1]);output=pathlib.Path(sys.argv[2]);mac=sys.argv[3]=='darwin'
root=source/'HE Manager.app' if mac else source
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True) as archive:
    for current,directories,files in os.walk(root,followlinks=False):
        for name in directories+files:
            file=pathlib.Path(current)/name
            relative=file.relative_to(source)
            if file.is_symlink():
                info=zipfile.ZipInfo(relative.as_posix())
                info.create_system=3
                info.external_attr=file.lstat().st_mode<<16
                archive.writestr(info,os.readlink(file))
            elif file.is_file():archive.write(file,relative)
