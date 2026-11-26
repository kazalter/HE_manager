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
    skin_dir = tmp_path / 'test' / 'test_2'
    assert (skin_dir / 'test_2.moc3').read_text() == 'MOC3'
    import os, stat
    if os.name != 'nt':
        assert stat.S_IMODE(skin_dir.stat().st_mode) == 0o755
        assert stat.S_IMODE((skin_dir / 'test_2.moc3').stat().st_mode) == 0o644
    assert post(good).status_code == 409
    assert len(client.get('/l2d/models/manifest.json').json()) == 1


def test_import_requires_admin(tmp_path, monkeypatch):
    monkeypatch.setenv('HE_L2D_MODELS_DIR', str(tmp_path))
    app = FastAPI()
    app.include_router(l2d.router)
    response = TestClient(app).post('/l2d/models/import/test_2', files={'archive': ('skin.zip', archive({}))})
    assert response.status_code in (401, 403)


def test_manifest_orders_by_shop_id_desc_and_zero_last(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv('HE_L2D_MODELS_DIR', str(tmp_path))

    def add_skin(char, skin_id, l2d_meta=None):
        skin_dir = tmp_path / char / skin_id
        skin_dir.mkdir(parents=True)
        (skin_dir / f'{skin_id}.model3.json').write_text('{}', encoding='utf-8')
        if l2d_meta is not None:
            (skin_dir / f'{skin_id}.l2d.json').write_text(json.dumps(l2d_meta), encoding='utf-8')

    add_skin('biaoqiang', 'biaoqiang', {'name': '标枪'})
    add_skin('aidang', 'aidang_2')  # uses l2d_shop_ids.json (70009)
    add_skin('antu', 'antu_2_hx')  # strips _hx -> antu_2 (71398)
    add_skin('future', 'future_9', {'name': '未来新皮肤', 'shop_id': 99999})
    add_skin('unknown', 'unknown_skin')

    app = FastAPI()
    app.include_router(l2d.router)
    items = TestClient(app).get('/l2d/models/manifest.json').json()
    assert [item['id'] for item in items] == [
        'future_9',
        'antu_2_hx',
        'aidang_2',
        'unknown_skin',
        'biaoqiang',
    ]
    assert items[0]['shop_id'] == 99999
    assert items[1]['shop_id'] > items[2]['shop_id'] > 0
    assert items[3]['shop_id'] == 0
    assert items[4]['shop_id'] == 0
