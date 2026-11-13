import io
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.routers import l2d


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return output.getvalue()


def test_import_is_atomic_and_refuses_existing_or_unsafe_files(tmp_path, monkeypatch):
    monkeypatch.setenv('HE_L2D_MODELS_DIR', str(tmp_path))
    app = FastAPI()
    app.include_router(l2d.router)
    app.dependency_overrides[auth.require_admin] = lambda: object()
    client = TestClient(app)
    good = {'test_2.model3.json': '{}', 'test_2.moc3': 'MOC3', 'textures/a.png': 'png'}
    def post(files):
        return client.post('/l2d/models/import/test_2', files={'archive': ('skin.zip', archive(files), 'application/zip')})
    assert post({**good, '../escape': 'bad'}).status_code == 400
    assert not (tmp_path / 'test').exists()
    assert post(good).status_code == 201
    assert (tmp_path / 'test' / 'test_2' / 'test_2.moc3').read_text() == 'MOC3'
    assert post(good).status_code == 409
    assert len(client.get('/l2d/models/manifest.json').json()) == 1


def test_import_requires_admin(tmp_path, monkeypatch):
    monkeypatch.setenv('HE_L2D_MODELS_DIR', str(tmp_path))
    app = FastAPI()
    app.include_router(l2d.router)
    response = TestClient(app).post('/l2d/models/import/test_2', files={'archive': ('skin.zip', archive({}))})
    assert response.status_code in (401, 403)
