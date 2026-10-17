"""Verify the complete CP-01 packaged acceptance matrix against current sources."""
import hashlib
import json
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parents[1]
evidence = pathlib.Path(sys.argv[1]).resolve()

def read(name):
    return json.loads((evidence / name).read_text(encoding='utf-8-sig'))

def require(condition, description):
    if not condition:
        raise RuntimeError(description)

def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()

checks = []
for platform, label, hardware in [('darwin', 'mac', 'videotoolbox-copy'), ('win32', 'windows', 'd3d11va')]:
    binaries = None
    for mode in ['local', 'network']:
        name = f'CP-01-{label}-packaged-{mode}.json'
        report = read(name)
        require(report['status'] == 'partial-pass' and not report.get('error'), name + ': integration failed')
        require(report['platform'] == platform, name + ': platform mismatch')
        artifact = report['artifact']
        require(artifact['packaged'] and artifact['runtimeWithinApp'] and artifact['electron'] == '44.8.0', name + ': packaged runtime')
        require(artifact['sourceKind'] == ('protected-http' if mode == 'network' else 'local-fixture'), name + ': source kind')
        require(artifact['hasAuthorizationHeader'] == (mode == 'network'), name + ': authorization')
        for path in ['probe/main.cjs', 'probe/preload.cjs']:
            require(artifact['files'][path] == digest(root / path), name + ': stale JS ' + path)
        for path, expected in artifact['nativeBuild']['sourceSha256'].items():
            require(expected == digest(root / 'native' / path), name + ': stale native source ' + path)
        if binaries is None:
            binaries = artifact['files']
        require(binaries == artifact['files'], name + ': different binaries across local/network')
        required = ['orientation', 'overlayInput', 'sameSessionFullscreen', 'seek', 'completedFrameRetained',
                    'slowConsumer', 'minimizeRestore', 'resize', 'pausedResize', 'boundedFrames']
        require(all(report['checks'].get(key) is True for key in required), name + ': acceptance check missing/failed')
        require(report['checks']['video']['spread'] > 40 and report['checks']['video']['displayed'] >= 5, name + ': actual image')
        require(report['stateBeforeStop']['hwdec'] == hardware, name + ': actual hardware decode')
        before, after = report['fullscreenState']['before'], report['fullscreenState']['after']
        require(before['aid'] == '2' and before['sid'] == '2' and before['speed'] == 1.25, name + ': non-default tracks/speed')
        require(before['paused'] and after['paused'] and before['sourceLoads'] == after['sourceLoads'] == 1, name + ': fullscreen load/pause')
        require(all(before[key] == after[key] for key in ['aid', 'sid', 'speed']), name + ': fullscreen track preservation')
        shaders = report['checks']['shaders']
        require(all(shaders[key]['matched'] for key in ['off', 'efficiency', 'quality']), name + ': shader matches')
        require('Anime4K' not in shaders['off']['passes'] and 'Restore-CNN-(M)' in shaders['efficiency']['passes']
                and 'Restore-CNN-(VL)' in shaders['quality']['passes'], name + ': actual shader passes')
        renderer = report['slowConsumer']['renderer']
        require(renderer['delayContinued'] >= 3 and report['slowConsumer']['maxInFlight'] <= 2, name + ': slow consumer completion')
        states = [report['stateAfterStop'], *[item['stopped'] for item in report['checks']['reopen']]]
        require(len(states) == 4, name + ': repeated sessions')
        require(all(s['stopped'] and s['surfaces'] == s['leases'] == s['inFlight'] == 0 for s in states), name + ': native resources remain')
        require(all(item['spread'] > 40 for item in report['checks']['reopen']), name + ': reopened image')
        require((evidence / name.replace('.json', '.png')).is_file(), name + ': screenshot missing')
        checks.append({'report': name, 'sha256': digest(evidence / name), 'passed': True})
    close_name = f'CP-01-{label}-packaged-close.json'
    close = read(close_name)
    require(close['status'] == 'passed' and close['packaged'] and close['platform'] == platform, close_name + ': normal close')
    require(close['state']['stopped'] and close['state']['leases'] == close['state']['surfaces'] == close['state']['inFlight'] == 0, close_name + ': resources remain')
    dependencies = read(f'CP-01-{label}-dependencies.json')
    require(dependencies['status'] == 'passed', label + ': dependency inspection')
    inspected = {item['file'].replace('\\', '/'): item for item in dependencies['files']}
    for path, expected in binaries.items():
        if path.startswith('native/'):
            require(path in inspected and inspected[path]['sha256'] == expected, label + ': inspected binary differs from executed binary ' + path)
    if platform == 'darwin':
        require(len(dependencies['files']) == 45, 'mac: native module plus 44 dependencies')
        for item in dependencies['files']:
            require(all(link.startswith(('@loader_path/', '/System/Library/', '/usr/lib/')) for link in item['dependencies']), 'mac: external dynamic library')
    else:
        require(len(dependencies['files']) == 2 and dependencies['graphicsDriverLoader']['file'].lower() == 'c:\\windows\\system32\\vulkan-1.dll', 'windows: native dependencies/driver loader')
        require(all('vcruntime' not in item['dumpbin'].lower() for item in dependencies['files']), 'windows: unexpected dev CRT')
    checks.append({'report': close_name, 'sha256': digest(evidence / close_name), 'passed': True})
preflight = read('CP-01-http-preflight.json')
require(preflight['passed'] and preflight['anonymousStatus'] == 401 and preflight['authorizedStatus'] == 206, 'HTTP authorization/range preflight')
requests = read('CP-01-http-evidence.json')
require(any(item['status'] == 401 and not item['hasBearer'] for item in requests), 'HTTP anonymous rejection')
require(any(item['status'] == 206 and item['hasBearer'] and re.match(r'bytes=[1-9]\d*-', item.get('range') or '') for item in requests), 'HTTP nonzero Range evidence')
summary = {'phase': 'CP-01', 'status': 'passed', 'matrix': checks,
           'scope': 'Section 7.4 prototype gate; full format/performance/long-play/installer gates remain CP-04/06/07',
           'sourceSha256': {p: digest(root / p) for p in ['probe/main.cjs', 'probe/preload.cjs', 'native/embedded.cpp', 'native/surface.h']}}
(evidence / 'CP-01-verification.json').write_text(json.dumps(summary, indent=2) + '\n')
print('CP-01 packaged local/network/close matrix: passed')
