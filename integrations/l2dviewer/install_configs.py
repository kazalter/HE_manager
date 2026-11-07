"""Install recovered controller JSON files alongside existing HDD models."""
import argparse
import json
import shutil
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('configs', type=Path)
parser.add_argument('models', type=Path)
args = parser.parse_args()
root = args.models.resolve(strict=True)
pending = []
for source in sorted(args.configs.rglob('*.l2d.json')):
    relative = source.relative_to(args.configs)
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f'Path outside models: {relative}')
    model = target.with_name(target.name.replace('.l2d.json', '.model3.json'))
    if not model.is_file():
        raise ValueError(f'Missing model: {model}')
    config = json.loads(source.read_text(encoding='utf-8'))
    if not config.get('entries') or not config.get('idle_index'):
        raise ValueError(f'Incomplete controller: {source}')
    if target.exists():
        if json.loads(target.read_text(encoding='utf-8')) != config:
            raise ValueError(f'Existing controller differs; preserved: {target}')
    else:
        pending.append((source, target))
for source, target in pending:
    shutil.copyfile(source, target)
print(f'Installed {len(pending)} controller configs; existing configs preserved.')
