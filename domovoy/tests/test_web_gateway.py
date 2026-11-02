"""Проверка сайта через тот же закрытый ASGI-прокси, что используется на сервере."""
import importlib.util
from pathlib import Path

import httpx

from core import config
from services import households
from web.app import create_app
from test_web import TOKEN, headers


async def test_category_removal_works_through_private_get_post_gateway(database, monkeypatch):
    monkeypatch.setattr(config, 'BOT_TOKEN', TOKEN)
    module_path = Path(__file__).resolve().parents[2] / 'predvestnik_v2/FastAPI/private_house_gateway.py'
    spec = importlib.util.spec_from_file_location('test_house_boundary', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def public_app(scope, receive, send):
        raise AssertionError('Private request reached public application')

    app = module.PrivateHouseGateway(public_app, prefix='/_h/test-private',
                                    transport=httpx.ASGITransport(app=create_app()))
    house = await households.create_house(100, 'Владелец', 'Дом')
    base = f'/_h/test-private/api/houses/{house}/categories'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        created = await client.post(base, headers=headers(), json={'name': 'Для теста'})
        assert created.status_code == 200
        category = created.json()['category_id']
        assert (await client.delete(f'{base}/{category}', headers=headers())).status_code == 404
        assert (await client.post(f'{base}/{category}/delete', headers=headers())).status_code == 200
        assert (await client.post(f'{base}/{category}/delete')).status_code == 404
