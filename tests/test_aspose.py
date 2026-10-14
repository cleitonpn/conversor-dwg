from pathlib import Path
from tempfile import SpooledTemporaryFile

import httpx
import pytest

from app.aspose import AsposeCadClient, ConversionError
from app.config import Settings


def glb_bytes() -> bytes:
    # Cabecalho GLB 2.0 minimo para validar o transporte do arquivo.
    return b"glTF" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little")


@pytest.mark.asyncio
async def test_authenticates_and_downloads_glb() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/connect/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer token"
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, content=glb_bytes())

    source = SpooledTemporaryFile()
    source.write(b"AC1032fake-drawing")
    client = AsposeCadClient(
        Settings("client", "secret"),
        transport=httpx.MockTransport(handler),
    )

    output = await client.convert(source, "modelo.dwg")
    try:
        assert output.read_bytes() == glb_bytes()
        assert calls == ["POST /connect/token", "PUT /v3.0/cad/glb"]
    finally:
        Path(output).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_rejects_non_glb_success_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/token":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, content=b"not really a glb")

    source = SpooledTemporaryFile()
    source.write(b"AC1032fake-drawing")
    client = AsposeCadClient(
        Settings("client", "secret"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ConversionError, match="nao e um GLB valido"):
        await client.convert(source, "modelo.dwg")


@pytest.mark.asyncio
async def test_falls_back_to_generic_conversion_after_provider_error() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/connect/token":
            return httpx.Response(200, json={"access_token": "token"})
        if request.url.path == "/v3.0/cad/glb":
            return httpx.Response(500, text="System.InvalidOperationException: internal stack")
        assert request.url.params["outputFormat"] == "GLB"
        return httpx.Response(200, content=glb_bytes())

    source = SpooledTemporaryFile()
    source.write(b"AC1032fake-drawing")
    client = AsposeCadClient(
        Settings("client", "secret"),
        transport=httpx.MockTransport(handler),
    )

    output = await client.convert(source, "modelo.dwg")
    try:
        assert output.read_bytes() == glb_bytes()
        assert calls == [
            "POST /connect/token",
            "PUT /v3.0/cad/glb",
            "POST /v3.0/cad/Convert",
        ]
    finally:
        Path(output).unlink(missing_ok=True)


def test_hides_provider_stack_trace() -> None:
    message = AsposeCadClient._format_service_error(
        500,
        "System.InvalidOperationException: Synchronous operations are disallowed at Server.Write",
    )

    assert "InvalidOperationException" not in message
    assert "falha interna" in message
