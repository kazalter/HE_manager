import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { resedit } from "../node_modules/@electron/packager/dist/resedit.js";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const target = process.argv[2];
const python = process.platform === "win32" ? "python" : "python3";
if (!["darwin", "win32"].includes(target))
  throw new Error("Usage: npm run package -- darwin|win32");
const arch = target === "darwin" ? "arm64" : "x64";
execFileSync(
  python,
  [path.join(root, "scripts/electron-template.py"), target],
  { stdio: "inherit" },
);
const output = path.join(root, "release", `HE Manager-${target}-${arch}`);
const destination =
  target === "darwin"
    ? path.join(output, "HE Manager.app/Contents/Resources/app")
    : path.join(output, "resources/app");
execFileSync(
  python,
  [
    "-c",
    `
import pathlib,shutil,json
import hashlib
shutil._USE_CP_SENDFILE=False
root=pathlib.Path(${JSON.stringify(root)})
dest=pathlib.Path(${JSON.stringify(destination)})
dest.mkdir(parents=True,exist_ok=True)
for name in ['src','ui']:
    shutil.copytree(root/name,dest/name,symlinks=True,dirs_exist_ok=True)
    print('Copied',name,flush=True)
for name in ['shaders','licenses','test']:
    shutil.copytree(root/'resources'/name,dest/'resources'/name,symlinks=True,dirs_exist_ok=True)
shutil.copytree(root/'resources/runtime'/${JSON.stringify(target)},dest/'resources/runtime',symlinks=True,dirs_exist_ok=True)
native=root/'native'
build=native/'build'/${JSON.stringify(`${target}-${arch}`)}
metadata=json.loads((build/'build-info.json').read_text(encoding='utf-8-sig'))
for name,expected in metadata['sourceSha256'].items():
    if hashlib.sha256((native/name).read_bytes()).hexdigest()!=expected:
        raise RuntimeError('Rebuild the native module after changing '+name)
if hashlib.sha256((build/'he_embedded.node').read_bytes()).hexdigest()!=metadata['addonSha256']:
    raise RuntimeError('Native addon checksum mismatch')
shutil.copytree(build,dest/'native/build'/${JSON.stringify(`${target}-${arch}`)},ignore=shutil.ignore_patterns('*.obj','*.lib','*.exp'),dirs_exist_ok=True)
shutil.copytree(native/'runtime'/${JSON.stringify(target)},dest/'native/runtime'/${JSON.stringify(target)},ignore=shutil.ignore_patterns('include','*.lib','*.a'),dirs_exist_ok=True)
for name in ['runtime-lock.json','header-lock.json','README.md']:
    shutil.copy2(native/name,dest/'native'/name)
pkg=json.loads((root/'package.json').read_text())
pkg.pop('devDependencies',None);pkg.pop('scripts',None)
(dest/'package.json').write_text(json.dumps(pkg,indent=2))
shutil.copy2(root/'runtime-lock.json',dest/'runtime-lock.json')
print('Copied native runtimes',flush=True)
`,
  ],
  { stdio: "inherit" },
);
const pkg = JSON.parse(
  await fs.readFile(path.join(root, "package.json"), "utf8"),
);
if (target === "win32")
  await resedit(path.join(output, "HE Manager.exe"), {
    productVersion: pkg.version,
    fileVersion: pkg.version,
    iconPath: path.join(root, "resources/icons/he.ico"),
    win32Metadata: {
      FileDescription: "HE Manager",
      ProductName: "HE Manager",
      CompanyName: "HE Manager",
    },
  });
const archive = path.join(
  root,
  "release",
  `HE-Manager-${pkg.version}-${target}-${arch}.zip`,
);
execFileSync(
  python,
  [path.join(root, "scripts/archive.py"), output, archive, target],
  { stdio: "inherit" },
);
console.log("Package ready:", archive);
