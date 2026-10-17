"""Serve synthetic fixtures with the real HE FastAPI/auth/Range implementation.

Run with HE_PROBE_SERVER_ROOT set to a disposable, separate directory. The
production database, credentials and media are never read or mounted.
"""
import json
import os
import pathlib
import secrets
import shutil
import socket
import sys
import threading

repository = pathlib.Path(__file__).resolve().parents[2]
root = pathlib.Path(os.environ["HE_PROBE_SERVER_ROOT"]).resolve()
if root == repository or repository in root.parents and ".diagnostics" not in root.parts:
    raise RuntimeError("Use an isolated disposable data directory")
port = int(os.environ.get("HE_PROBE_SERVER_PORT", "18010"))
if "--seed-only" not in sys.argv:
    with socket.socket() as check:
        check.bind(("127.0.0.1", port))
root.mkdir(parents=True, exist_ok=True)
work = root / "work"
work.mkdir(exist_ok=True)
os.environ["HE_DATABASE_URL"] = "sqlite:///" + (root / "library.db").as_posix()
os.environ["HE_AI_CONFIG_PATH"] = str(root / "ai.json")
os.chdir(work)
sys.path.insert(0, str(repository / "backend"))
from app.main import app
from app import auth, models
from app.database import SessionLocal, engine
from app.migrations import run_schema_migrations
import uvicorn

models.Base.metadata.create_all(engine)
run_schema_migrations()
fixtures = root / "fixtures"
fixtures.mkdir(exist_ok=True)
fixture = pathlib.Path(os.environ.get("HE_PROBE_FIXTURE_PATH", str(repository / "desktop/resources/test/sample.mp4")))
names = ["first" + fixture.suffix, "second" + fixture.suffix]
rich = fixture.name == "acceptance.mkv"
for name in names:
    shutil.copy2(fixture, fixtures / name)
with SessionLocal() as database:
    user = database.query(models.User).filter_by(username="desktop-probe").first()
    if user is None:
        user = models.User(username="desktop-probe", password_hash=auth.hash_password(secrets.token_urlsafe(32)), is_admin=True, is_active=True)
        database.add(user)
        database.commit()
    folder = database.query(models.Folder).filter_by(path=str(fixtures)).first()
    if folder is None:
        folder = models.Folder(path=str(fixtures), scan_mode="video", status="idle")
        database.add(folder)
        database.commit()
    for name in names:
        file = fixtures / name
        if database.query(models.Media).filter_by(absolute_path=str(file)).first() is None:
            database.add(models.Media(folder_id=folder.id, title="CP-01 synthetic " + name, relative_path=name, absolute_path=str(file), media_type="video", extension=fixture.suffix, file_size=file.stat().st_size, width=640, height=360, duration=30 if rich else 8))
    database.commit()
    items = [database.query(models.Media).filter_by(absolute_path=str(fixtures / name)).one() for name in names]
    token = auth.create_access_token(database, user)
    config = {"source": f"http://127.0.0.1:{port}/stream/{items[0].id}", "secondSource": f"http://127.0.0.1:{port}/stream/{items[1].id}", "headers": ["Authorization: Bearer " + token], "richFixture": rich}
    descriptor = os.open(root / "client-access.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(config, file)
if "--seed-only" in sys.argv:
    print("Synthetic acceptance media seeded")
    raise SystemExit(0)

requests = []
lock = threading.Lock()


@app.middleware("http")
async def evidence(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/stream/"):
        with lock:
            requests.append({"path": request.url.path, "method": request.method, "range": request.headers.get("range"), "hasBearer": request.headers.get("authorization", "").startswith("Bearer "), "status": response.status_code, "contentRange": response.headers.get("content-range")})
            temporary = root / "http-evidence.next"
            temporary.write_text(json.dumps(requests, indent=2) + "\n", encoding="utf-8")
            temporary.replace(root / "http-evidence.json")
    return response

(root / "process.json").write_text(json.dumps({"pid": os.getpid(), "port": port}), encoding="utf-8")
uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)
