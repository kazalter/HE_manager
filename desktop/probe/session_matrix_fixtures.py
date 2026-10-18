"""Optional disposable CP-03 matrix; imported only by the diagnostic server."""
import os
import secrets
import zipfile
import wave
from datetime import datetime
from PIL import Image
from app import auth, models


def seed(database, folder, fixtures):
    label = os.environ.get("HE_PROBE_MATRIX_LABEL", "A")
    if label not in {"A", "B"}:
        raise RuntimeError("Unknown synthetic fixture label")
    password = secrets.token_urlsafe(24)
    user = database.query(models.User).filter_by(username="desktop-probe-two").first()
    if user is None:
        user = models.User(username="desktop-probe-two", is_admin=False, is_active=True)
        database.add(user)
    user.password_hash = auth.hash_password(password)
    tags = []
    for name in ["CP03-A", "CP03-B"]:
        tag = database.query(models.Tag).filter_by(name=name).first()
        if tag is None:
            tag = models.Tag(name=name)
            database.add(tag)
        tags.append(tag)
    database.flush()

    def media(file, title, kind):
        item = database.query(models.Media).filter_by(absolute_path=str(file)).first()
        if item is None:
            item = models.Media(folder_id=folder.id, absolute_path=str(file), relative_path=file.name)
            database.add(item)
        item.title = title
        item.media_type = kind
        item.extension = file.suffix
        item.file_size = file.stat().st_size
        item.created_at = datetime(2000, 1, 1)
        item.progress = 0
        item.view_status = "unviewed"
        return item

    for index in range(62):
        file = fixtures / f"cp03-image-{index:03}.png"
        Image.new("RGB", (32, 48), (index * 3, 90, 160)).save(file)
        item = media(file, f"CP-03 {label} paged image {index:03}", "image")
        item.width = 32
        item.height = 48
        item.source_site = "pixiv" if index % 2 else None
        item.favorite = index % 3 == 0
        item.rating = index % 6
        item.view_status = ["unviewed", "viewing", "viewed"][index % 3]
        item.tags = [tags[index % 2]]
    file = fixtures / "cp03-one-page.zip"
    with zipfile.ZipFile(fixtures / "cp02-manga.zip") as original:
        with zipfile.ZipFile(file, "w") as output:
            output.writestr("001.png", original.read("001.png"))
    single = media(file, f"CP-03 {label} single-page manga", "manga")
    single.page_count = 1
    file = fixtures / "cp03-audio.wav"
    with wave.open(str(file), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000)
    sound = media(file, f"CP-03 {label} audio", "audio")
    sound.duration = 1
    database.commit()
    return {"secondaryUser": {"username": user.username, "password": password},
            "singleMangaId": single.id, "audioId": sound.id, "fixtureLabel": label, "expectedTotal": 69}
