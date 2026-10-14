import httpx
import pytest

from app.config import Settings
from app.main import app, get_settings


def settings() -> Settings:
    return Settings("client", "secret", max_upload_mb=1)


@pytest.mark.asyncio
async def test_health_reports_configuration() -> None:
    app.dependency_overrides[get_settings] = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "converterConfigured": True,
        "maxUploadMb": 1,
    }


@pytest.mark.asyncio
async def test_rejects_non_dwg_extension() -> None:
    app.dependency_overrides[get_settings] = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/convert",
            files={"file": ("modelo.txt", b"AC1032fake", "text/plain")},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 415


@pytest.mark.asyncio
async def test_rejects_invalid_dwg_signature() -> None:
    app.dependency_overrides[get_settings] = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/convert",
            files={"file": ("modelo.dwg", b"not-a-dwg", "application/acad")},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_static_home_is_available() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "DWG" in response.text

