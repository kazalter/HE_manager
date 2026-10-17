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
import io
import zipfile
import asyncio
from datetime import datetime

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
ui_fixtures = os.environ.get('HE_PROBE_UI_FIXTURES') == '1'
ui_stream_delay = min(3, max(0, float(os.environ.get('HE_PROBE_UI_STREAM_DELAY', '0')))) if ui_fixtures else 0
ui_password = secrets.token_urlsafe(24) if ui_fixtures else None
if ui_fixtures:
    from PIL import Image, ImageDraw
    from app.services.thumbnails import THUMBNAIL_DIR
    thumbnails = pathlib.Path(THUMBNAIL_DIR)
    with zipfile.ZipFile(fixtures / 'cp02-manga.zip', 'w') as archive:
        for index, dimensions in enumerate([(480, 720), (480, 720), (960, 540), (480, 720)]):
            image = Image.new('RGB', dimensions, ['#c7d2fe', '#fbcfe8', '#a7f3d0', '#fde68a'][index])
            draw = ImageDraw.Draw(image)
            draw.rectangle((24, 24, dimensions[0] - 24, dimensions[1] - 24), outline='#334155', width=5)
            draw.text((44, 60), f'HE Manager / CP-02 / page {index + 1}', fill='#0f172a')
            buffer = io.BytesIO(); image.save(buffer, 'PNG'); archive.writestr(f'{index + 1:03}.png', buffer.getvalue())
            if index == 0: image.save(thumbnails / 'cp02-portrait.png')
            if index == 2: image.save(thumbnails / 'cp02-landscape.png')
    image.save(fixtures / 'cp02-image.png')
    (fixtures / 'cp02-unreadable.mp4').write_bytes(b'HE synthetic unsupported video fixture\n')
with SessionLocal() as database:
    user = database.query(models.User).filter_by(username="desktop-probe").first()
    if user is None:
        user = models.User(username="desktop-probe", password_hash=auth.hash_password(secrets.token_urlsafe(32)), is_admin=True, is_active=True)
        database.add(user)
        database.commit()
    if ui_password:
        user.password_hash = auth.hash_password(ui_password)
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
    if ui_fixtures:
        items[0].title = '星海漫游：带有很长标题的跨平台内嵌播放器验收视频 · 第二章节与字幕音轨切换'
        items[0].cover_path = 'cp02-landscape.png'
        items[0].progress = 3; items[0].view_status = 'viewing'; items[0].last_opened_at = datetime.utcnow()
        items[1].title = '没有封面的短片 · 原画'; items[1].favorite = True
        for name, title, kind, cover in [
            ('cp02-manga.zip', '四季手记：单页、双页与卷轴阅读的长标题漫画代表作品', 'manga', 'cp02-portrait.png'),
            ('cp02-image.png', '午后的一张静态图片', 'image', None),
            ('cp02-unreadable.mp4', '无法解码的测试视频 · 重试与返回', 'video', None),
        ]:
            file = fixtures / name
            media = database.query(models.Media).filter_by(absolute_path=str(file)).first()
            if media is None:
                media = models.Media(folder_id=folder.id, absolute_path=str(file), relative_path=name)
                database.add(media)
            media.title = title; media.media_type = kind; media.extension = file.suffix
            media.file_size = file.stat().st_size; media.cover_path = cover
            media.width = 480; media.height = 720; media.page_count = 4 if kind == 'manga' else None
        database.commit()
    token = auth.create_access_token(database, user)
    config = {"source": f"http://127.0.0.1:{port}/stream/{items[0].id}", "secondSource": f"http://127.0.0.1:{port}/stream/{items[1].id}", "headers": ["Authorization: Bearer " + token], "richFixture": rich}
    if ui_fixtures:
        manga = database.query(models.Media).filter_by(absolute_path=str(fixtures / 'cp02-manga.zip')).one()
        unreadable = database.query(models.Media).filter_by(absolute_path=str(fixtures / 'cp02-unreadable.mp4')).one()
        config.update(server=f'http://127.0.0.1:{port}', username=user.username, password=ui_password,
                      videoId=items[0].id, mangaId=manga.id, errorVideoId=unreadable.id, expectVideoLoading=ui_stream_delay > 0)
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
    if ui_stream_delay and request.url.path == f'/stream/{items[0].id}':
        await asyncio.sleep(ui_stream_delay)
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
