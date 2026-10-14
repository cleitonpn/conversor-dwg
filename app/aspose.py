from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

import httpx

from app.config import Settings


TOKEN_URL = "https://api.aspose.cloud/connect/token"
CONVERT_URL = "https://api.aspose.cloud/v3.0/cad/glb"
GENERIC_CONVERT_URL = "https://api.aspose.cloud/v3.0/cad/Convert"


class ConversionError(RuntimeError):
    """Erro seguro para ser apresentado ao usuario."""


class AsposeCadClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._transport = transport
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        async with self._token_lock:
            if self._access_token and time.monotonic() < self._token_expires_at:
                return self._access_token

            self.settings.validate_credentials()
            try:
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=httpx.Timeout(30.0),
                ) as client:
                    response = await client.post(
                        TOKEN_URL,
                        data={
                            "grant_type": "client_credentials",
                            "client_id": self.settings.aspose_client_id,
                            "client_secret": self.settings.aspose_client_secret,
                        },
                        headers={"Accept": "application/json"},
                    )
                    response.raise_for_status()
                    payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ConversionError(
                    "Nao foi possivel autenticar no servico de conversao. Verifique as credenciais."
                ) from exc

            token = payload.get("access_token")
            if not token:
                raise ConversionError("O servico de conversao nao retornou um token valido.")

            expires_in = max(int(payload.get("expires_in", 3600)), 60)
            self._access_token = str(token)
            self._token_expires_at = time.monotonic() + expires_in - 30
            return self._access_token

    async def convert(self, source: BinaryIO, original_name: str) -> Path:
        token = await self._get_access_token()
        fd, output_name = tempfile.mkstemp(prefix="dwg-to-glb-", suffix=".glb")
        os.close(fd)
        output_path = Path(output_name)

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(self.settings.request_timeout_seconds),
            ) as client:
                attempts = (
                    ("PUT", CONVERT_URL, None),
                    ("POST", GENERIC_CONVERT_URL, {"outputFormat": "GLB"}),
                )
                for attempt, (method, url, params) in enumerate(attempts):
                    source.seek(0)
                    async with client.stream(
                        method,
                        url,
                        params=params,
                        headers={
                            "Authorization": f"Bearer {token}",
                            # A API oficial declara application/json mesmo quando
                            # a resposta bem-sucedida contem o arquivo binario.
                            "Accept": "application/json",
                        },
                        files={
                            "drawingData": (
                                original_name,
                                source,
                                "application/acad",
                            )
                        },
                    ) as response:
                        if response.status_code >= 400:
                            body = (await response.aread()).decode("utf-8", errors="replace")
                            if attempt == 0 and response.status_code >= 500:
                                continue
                            raise ConversionError(
                                self._format_service_error(response.status_code, body)
                            )

                        with output_path.open("wb") as destination:
                            async for chunk in response.aiter_bytes():
                                destination.write(chunk)
                        break

            if output_path.stat().st_size < 12:
                raise ConversionError("O servico retornou um arquivo GLB vazio ou incompleto.")
            with output_path.open("rb") as result:
                if result.read(4) != b"glTF":
                    raise ConversionError("O servico retornou um arquivo que nao e um GLB valido.")
            return output_path
        except ConversionError:
            output_path.unlink(missing_ok=True)
            raise
        except httpx.TimeoutException as exc:
            output_path.unlink(missing_ok=True)
            raise ConversionError("A conversao excedeu o tempo limite.") from exc
        except httpx.HTTPError as exc:
            output_path.unlink(missing_ok=True)
            raise ConversionError("Falha de comunicacao com o servico de conversao.") from exc

    @staticmethod
    def _format_service_error(status_code: int, body: str) -> str:
        message = f"A conversao foi recusada pelo servico ({status_code})."
        if status_code >= 500:
            return message + " O provedor encontrou uma falha interna; tente novamente."

        detail = ""
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                detail = str(payload.get("message") or payload.get("error") or "")
        except (ValueError, TypeError):
            detail = body

        detail = " ".join(detail.split())[:240]
        if detail and "exception" not in detail.lower() and " at " not in detail.lower():
            return f"{message} Detalhe: {detail}"
        return message

