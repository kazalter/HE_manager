"""Download pinned upstream runtimes. Run with Python 3.12+ on the build machine."""
import argparse, hashlib, json, pathlib, shutil, subprocess, tarfile, urllib.request, zipfile, os
ROOT=pathlib.Path(__file__).resolve().parents[1]
LOCK=json.loads((ROOT/'runtime-lock.json').read_text())

def download(item):
    cache=ROOT/'.downloads'/item['file']
    cache.parent.mkdir(exist_ok=True)
    if not cache.exists() or hashlib.sha256(cache.read_bytes()).hexdigest()!=item['sha256']:
        temporary=cache.with_suffix('.partial')
        with urllib.request.urlopen(item['url'],timeout=90) as response,temporary.open('wb') as output:
            shutil.copyfileobj(response,output)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=item['sha256']:
            temporary.unlink()
            raise RuntimeError('Upstream checksum changed: '+item['file'])
        temporary.replace(cache)
    return cache

def unzip(archive,target):
    target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        for info in zipped.infolist():
            rel=pathlib.PurePosixPath(info.filename)
            if rel.is_absolute() or '..' in rel.parts: raise RuntimeError('Unsafe archive path')
            zipped.extract(info,target)
            file=target/info.filename
            mode=(info.external_attr>>16)&0o777
            if file.is_file() and mode:file.chmod(mode)

parser=argparse.ArgumentParser()
parser.add_argument('platform',choices=['darwin','win32','all'])
args=parser.parse_args()
for platform in (['darwin','win32'] if args.platform=='all' else [args.platform]):
    for kind,item in LOCK[platform].items():
        archive=download(item)
        target=ROOT/'resources/runtime'/platform/kind
        if target.exists():shutil.rmtree(target)
        if archive.suffix=='.zip':unzip(archive,target)
        else:
            executable=shutil.which('7z') or shutil.which('7zz')
            if not executable and os.name=='nt':
                candidate=pathlib.Path(os.environ.get('ProgramFiles','C:/Program Files'))/'7-Zip/7z.exe'
                if candidate.is_file():executable=str(candidate)
            if not executable:raise RuntimeError('Install 7-Zip to extract the Windows mpv runtime')
            subprocess.run([executable,'x','-y','-o'+str(target),str(archive)],check=True,stdout=subprocess.DEVNULL)
        nested=target/'mpv.tar.gz'
        if nested.exists():
            with tarfile.open(nested) as tar:tar.extractall(target,filter='data')
            nested.unlink()
        for file in target.glob('*'):
            if file.name.startswith('input') or file.name in ['onepiece_demo.mp4','vcomp140d.dll']:file.unlink()
        binary=target/('realesrgan-ncnn-vulkan.exe' if platform=='win32' else 'realesrgan-ncnn-vulkan')
        if binary.exists():binary.chmod(0o755)
        print(platform,kind,'verified',item['sha256'])
