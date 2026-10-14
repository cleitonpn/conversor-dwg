from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from app.aspose import AsposeCadClient, ConversionError
from app.config import Settings


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="DWG para GLB", version="0.1.0")

_startup_settings = Settings.from_env()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_startup_settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition"],
)


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


def get_converter(settings: Settings = Depends(get_settings)) -> AsposeCadClient:
    return AsposeCadClient(settings)


def safe_output_name(original_name: str) -> str:
    stem = Path(original_name).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    return f"{stem or 'modelo'}.glb"


async def validate_upload(upload: UploadFile, max_upload_mb: int) -> None:
    if Path(upload.filename or "").suffix.lower() != ".dwg":
        raise HTTPException(status_code=415, detail="Envie um arquivo com extensao .dwg.")

    max_bytes = max_upload_mb * 1024 * 1024
    total = 0
    signature = b""
    while chunk := await upload.read(1024 * 1024):
        if not signature:
            signature = chunk[:6]
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"O arquivo excede o limite de {max_upload_mb} MB.",
            )

    await upload.seek(0)
    if not signature.startswith(b"AC10"):
        raise HTTPException(status_code=422, detail="O arquivo nao parece ser um DWG valido.")


@app.get("/api/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "status": "ok",
        "converterConfigured": bool(
            settings.aspose_client_id and settings.aspose_client_secret
        ),
        "maxUploadMb": settings.max_upload_mb,
    }


@app.post("/api/convert")
async def convert_dwg(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    converter: AsposeCadClient = Depends(get_converter),
) -> FileResponse:
    await validate_upload(file, settings.max_upload_mb)
    try:
        output_path = await converter.convert(file.file, file.filename or "modelo.dwg")
    except RuntimeError as exc:
        if isinstance(exc, ConversionError):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await file.close()

    return FileResponse(
        output_path,
        media_type="model/gltf-binary",
        filename=safe_output_name(file.filename or "modelo.dwg"),
        background=BackgroundTask(output_path.unlink, missing_ok=True),
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

