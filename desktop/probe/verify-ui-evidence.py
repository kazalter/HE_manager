"""Verify the CP-02 real UI matrix and the exact payload of its portable packages.

Use --platform for an explicitly partial audit while the other host is pending.
Source hashes can be checked against an explicit historical Git revision.
"""
import argparse
import hashlib
import json
import pathlib
import struct
import subprocess
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence', type=pathlib.Path)
parser.add_argument('--archives', type=pathlib.Path)
parser.add_argument('--revision')
parser.add_argument('--platform', choices=['darwin', 'win32'])
parser.add_argument('--output', type=pathlib.Path)
args = parser.parse_args()
root = pathlib.Path(__file__).resolve().parents[1]
archives = args.archives or root / 'release'
revision = subprocess.check_output(['git', 'rev-parse', '--verify', args.revision + '^{commit}'], cwd=root, text=True).strip() if args.revision else None


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def source_hash(relative):
    content = subprocess.check_output(['git', 'show', f'{revision}:desktop/{relative}'], cwd=root) if revision else (root / relative).read_bytes()
    return digest(content)


checks = ['directConnectivity', 'loginAndLibrary', 'continueWatching', 'minimumContent', 'libraryAppearance',
          'systemAppearance', 'emptySearch', 'videoLoading', 'embeddedVideo',
          'videoEnhancement', 'keyboardSettings', 'seek', 'sameSessionFullscreen', 'viewerClose',
          'readerModesAndZoom', 'readerControlsFit', 'enhancementFeedback', 'readerOpened', 'videoErrorAndRetry']
matrix = []
ui_payload = None
for platform, label, hardware in [('darwin', 'mac', 'videotoolbox-copy'), ('win32', 'windows', 'd3d11va')]:
    if args.platform and args.platform != platform:
        continue
    name = f'CP-02-{label}.json'
    report = json.loads((args.evidence / name).read_text(encoding='utf-8-sig'))
    require(report['phase'] == 'CP-02' and report['status'] == 'partial-pass' and not report.get('error'), name + ': run did not pass')
    require(report['platform'] == platform and report['packaged'] and report['electron'] == '44.8.0', name + ': packaged target mismatch')
    require(all(report['checks'].get(key) is True for key in checks), name + ': missing or failed UI gate')
    require(report['minimumContent'] == {'width': 1024, 'height': 640}, name + ': minimum content size')
    seek = report['seek']
    require(abs(seek['before'] - seek['target']) >= 3 and abs(seek['after'] - seek['target']) < 0.2, name + ': actual slider seek')
    require(report['video']['hwdec'] == hardware and report['video']['sourceLoads'] == 1 and report['video']['speed'] == 1.25, name + ': playback session')
    require(all(sum(track['type'] == kind for track in report['video']['tracks']) == 2 for kind in ['audio', 'sub']), name + ': actual track list')
    shaders = {item['mode']: item for item in report['shaderModes']}
    require(set(shaders) == {'off', 'efficiency', 'quality'}, name + ': shader modes')
    require('Anime4K' not in shaders['off']['passes'] and 'Restore-CNN-(M)' in shaders['efficiency']['passes']
            and 'Restore-CNN-(VL)' in shaders['quality']['passes'], name + ': actual shader passes')
    require(all(item['sourceLoads'] == 1 and item['hwdec'] == hardware for item in shaders.values()), name + ': shader change restarted or lost hardware decoding')
    require(report['closedPlayer'] == {'stopped': True, 'surfaces': 0, 'leases': 0, 'references': 0}, name + ': player resources retained')
    layouts = {(item['scene'], item['mode'], item['width'], item['height']) for item in report['layouts'] if not item['overflow']}
    expected = {(scene, mode, width, height) for scene in ['library', 'video', 'reader'] for mode in ['light', 'dark'] for width, height in [(1280, 800), (1024, 640)]}
    require(layouts == expected, name + ': scene/theme/size matrix incomplete')
    for scene, mode, width, height in expected:
        matches = [file for file in report['screenshots'] if file.endswith(f'-{scene}-{mode}-{width}.png')]
        require(len(matches) == 1, name + ': screenshot missing')
        file = matches[0]
        require(pathlib.Path(file).name == file, name + ': invalid screenshot path')
        data = (args.evidence / file).read_bytes()
        require(data[:8] == b'\x89PNG\r\n\x1a\n', file + ': invalid PNG')
        pixel_width, pixel_height = struct.unpack('>II', data[16:24])
        require(pixel_width >= width and pixel_height >= height and abs(pixel_width / width - pixel_height / height) < 0.02, file + ': capture dimensions differ from viewport')
    for suffix in ['reader-double-dark-1024.png', 'reader-scroll-dark-1024.png', 'reader-enhancement-feedback.png', 'video-loading.png', 'video-error.png']:
        require(any(file.endswith('-' + suffix) and (args.evidence / file).is_file() for file in report['screenshots']), name + ': state capture missing: ' + suffix)
    for file, sha256 in report['sourceSha256'].items():
        require(source_hash('src/' + file) == sha256, name + ': different host source: ' + file)
    for file, sha256 in report['nativeBuild']['sourceSha256'].items():
        require(source_hash('native/' + file) == sha256, name + ': different native source: ' + file)
    if ui_payload is None:
        ui_payload = report['uiSha256']
    require(ui_payload == report['uiSha256'] and 'index.html' in ui_payload, name + ': UI differs across platforms')
    arch = 'arm64' if platform == 'darwin' else 'x64'
    archive = archives / f"HE-Manager-{report['version']}-{platform}-{arch}.zip"
    prefix = 'HE Manager.app/Contents/Resources/app/' if platform == 'darwin' else 'resources/app/'
    with zipfile.ZipFile(archive) as package:
        for file, sha256 in report['sourceSha256'].items():
            require(digest(package.read(prefix + 'src/' + file)) == sha256, name + ': archive host source differs from executed source')
        packaged_ui = {file[len(prefix + 'ui/'):]: digest(package.read(file)) for file in package.namelist() if file.startswith(prefix + 'ui/') and not file.endswith('/')}
        require(packaged_ui == report['uiSha256'], name + ': archive UI differs from executed UI')
        native_prefix = prefix + f'native/build/{platform}-{arch}/'
        require(digest(package.read(native_prefix + 'he_embedded.node')) == report['nativeSha256'], name + ': archive native addon differs')
        metadata = json.loads(package.read(native_prefix + 'build-info.json').decode('utf-8-sig'))
        require(metadata == report['nativeBuild'], name + ': archive build metadata differs')
        library = 'darwin/libmpv.2.dylib' if platform == 'darwin' else 'win32/libmpv-2.dll'
        require(digest(package.read(prefix + 'native/runtime/' + library)) == report['librarySha256'], name + ': archive libmpv differs')
    matrix.append({'platform': platform, 'report': name, 'reportSha256': digest((args.evidence / name).read_bytes()),
                   'archive': archive.name, 'archiveSha256': digest(archive.read_bytes()), 'passed': True})

summary = {'phase': 'CP-02', 'status': 'partial-pass' if args.platform else 'passed',
           'sourceRevision': revision or 'working-tree', 'matrix': matrix,
           'scope': 'Shared UI, theme, representative input and application foundation. CP-03–07 acceptance remains separate.'}
output = args.output or args.evidence / 'CP-02-verification.json'
output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print('CP-02 UI/package matrix:', summary['status'])
