from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Iterable, TextIO

import ezdxf
from ezdxf import disassemble
from ezdxf.math import Vec3

from app.config import Settings
from app.obj_to_glb import ObjConversionError, convert_obj_to_glb


class ConversionError(RuntimeError):
    """Erro seguro para ser exibido ao usuario da API."""


_ACIS_TYPES = {"3DSOLID", "BODY", "REGION", "SURFACE"}
_FACE_TYPES = {"3DFACE", "SOLID", "TRACE"}

# AutoCAD $INSUNITS -> metros.
_UNIT_TO_METERS = {
    0: 1.0,
    1: 0.0254,
    2: 0.3048,
    3: 1609.344,
    4: 0.001,
    5: 0.01,
    6: 1.0,
    7: 1000.0,
    8: 2.54e-8,
    9: 2.54e-5,
    10: 0.9144,
    11: 1e-10,
    12: 1e-9,
    13: 1e-6,
    14: 0.1,
    15: 10.0,
    16: 100.0,
    17: 1e9,
    18: 149_597_870_700.0,
    19: 9.460_730_472_580_8e15,
    20: 3.085_677_581_491_367e16,
    21: 1200.0 / 3937.0,
}


def _flush_dxf_entity(destination: TextIO, pairs: list[tuple[str, str]]) -> int:
    """Corrige MESH sem o grupo 95 que algumas versoes do LibreDWG emitem."""
    if len(pairs) < 2 or pairs[0][0].strip() != "0" or pairs[0][1].strip() != "MESH":
        for code, value in pairs:
            destination.write(code)
            destination.write(value)
        return 0

    if any(code.strip() == "95" for code, _ in pairs):
        for code, value in pairs:
            destination.write(code)
            destination.write(value)
        return 0

    first_crease = next(
        (index for index, (code, _) in enumerate(pairs) if code.strip() == "140"), len(pairs)
    )
    crease_count = sum(1 for code, _ in pairs if code.strip() == "140")
    pairs.insert(first_crease, (" 95\n", f"{crease_count:10d}\n"))
    for code, value in pairs:
        destination.write(code)
        destination.write(value)
    return 1


def repair_libredwg_dxf(source_path: Path) -> int:
    """Sanitiza um defeito conhecido do exportador sem alterar a geometria."""
    repaired_path = source_path.with_suffix(".repaired.dxf")
    repaired_meshes = 0
    current_entity: list[tuple[str, str]] = []
    try:
        with source_path.open("r", encoding="utf-8", errors="replace", newline="") as source:
            with repaired_path.open("w", encoding="utf-8", newline="") as destination:
                while True:
                    code = source.readline()
                    if not code:
                        break
                    value = source.readline()
                    if not value:
                        destination.write(code)
                        break
                    if code.strip() == "0" and current_entity:
                        repaired_meshes += _flush_dxf_entity(destination, current_entity)
                        current_entity = []
                    current_entity.append((code, value))
                if current_entity:
                    repaired_meshes += _flush_dxf_entity(destination, current_entity)
        repaired_path.replace(source_path)
    except OSError as exc:
        repaired_path.unlink(missing_ok=True)
        raise ConversionError("Nao foi possivel preparar o DXF intermediario.") from exc
    return repaired_meshes


def _clean_vertices(vertices: Iterable[Vec3]) -> list[Vec3]:
    result = [Vec3(vertex) for vertex in vertices]
    if len(result) > 1 and result[0].isclose(result[-1]):
        result.pop()
    return result


def _write_obj_vertex(destination, vertex: Vec3, scale: float) -> int:
    # DWG/DXF usa Z para cima; glTF usa Y para cima. Tambem normalizamos para metros.
    x = vertex.x * scale
    y = vertex.z * scale
    z = -vertex.y * scale
    destination.write(f"v {x:.12g} {y:.12g} {z:.12g}\n")
    return 1


def dxf_to_obj(dxf_path: Path, obj_path: Path, flattening_distance: float = 0.01) -> dict[str, int]:
    """Converte entidades DXF reais em faces/linhas OBJ, expandindo blocos."""
    try:
        document = ezdxf.readfile(dxf_path)
    except (OSError, ezdxf.DXFError) as exc:
        raise ConversionError("O DWG foi lido, mas o DXF intermediario e invalido.") from exc

    modelspace = document.modelspace()
    unsupported_acis = sum(1 for entity in modelspace if entity.dxftype() in _ACIS_TYPES)
    scale = _UNIT_TO_METERS.get(int(document.header.get("$INSUNITS", 0) or 0), 1.0)

    vertex_index = 1
    face_count = 0
    line_count = 0

    try:
        entities = disassemble.recursive_decompose(modelspace)
        with obj_path.open("w", encoding="utf-8", newline="\n") as destination:
            destination.write("# Gerado localmente pelo conversor DWG para GLB\n")
            for entity in entities:
                entity_type = entity.dxftype()
                if entity_type in _ACIS_TYPES:
                    unsupported_acis += 1
                    continue

                primitive = disassemble.make_primitive(
                    entity, max_flattening_distance=flattening_distance
                )

                if primitive.mesh is not None:
                    for face in primitive.mesh.faces_as_vertices():
                        vertices = _clean_vertices(face)
                        if len(vertices) < 3:
                            continue
                        first = vertex_index
                        for vertex in vertices:
                            vertex_index += _write_obj_vertex(destination, vertex, scale)
                        destination.write(
                            "f " + " ".join(str(first + offset) for offset in range(len(vertices))) + "\n"
                        )
                        face_count += 1
                    continue

                vertices = _clean_vertices(primitive.vertices())
                if not vertices:
                    continue

                if entity_type in _FACE_TYPES and len(vertices) >= 3:
                    first = vertex_index
                    for vertex in vertices:
                        vertex_index += _write_obj_vertex(destination, vertex, scale)
                    destination.write(
                        "f " + " ".join(str(first + offset) for offset in range(len(vertices))) + "\n"
                    )
                    face_count += 1
                elif len(vertices) >= 2:
                    first = vertex_index
                    for vertex in vertices:
                        vertex_index += _write_obj_vertex(destination, vertex, scale)
                    destination.write(
                        "l " + " ".join(str(first + offset) for offset in range(len(vertices))) + "\n"
                    )
                    line_count += 1
    except (OSError, ezdxf.DXFError, ValueError, TypeError) as exc:
        raise ConversionError("Nao foi possivel interpretar a geometria 3D do DWG.") from exc

    if unsupported_acis and face_count == 0:
        raise ConversionError(
            "Este DWG contem solidos ACIS/3DSOLID sem malha renderizavel. "
            "Exporte os solidos como malha (MESH/3DFACE) no CAD e tente novamente."
        )

    if face_count == 0 and line_count == 0:
        raise ConversionError("O DWG nao possui geometria 3D exportavel.")

    return {
        "faces": face_count,
        "lines": line_count,
        "unsupportedAcis": unsupported_acis,
    }


class LocalDwgConverter:
    def __init__(self, settings: Settings, executable: str | None = None) -> None:
        self.settings = settings
        self.executable = executable or os.getenv("LIBREDWG_DWG2DXF") or shutil.which("dwg2dxf")

    async def _run_dwg2dxf(self, dwg_path: Path, dxf_path: Path) -> None:
        if not self.executable:
            raise ConversionError("O motor local LibreDWG nao esta instalado no servidor.")

        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-y",
                "-o",
                str(dxf_path),
                str(dwg_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.settings.request_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise ConversionError("A conversao local excedeu o tempo limite.") from exc
        except OSError as exc:
            raise ConversionError("Nao foi possivel iniciar o motor local LibreDWG.") from exc

        if process.returncode != 0 or not dxf_path.exists() or dxf_path.stat().st_size == 0:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip().splitlines()
            suffix = f" Detalhe: {detail[-1][:240]}" if detail else ""
            raise ConversionError(f"O LibreDWG nao conseguiu ler este arquivo DWG.{suffix}")

    async def convert(self, source: BinaryIO, original_name: str) -> Path:
        del original_name  # nome nao participa dos comandos e nunca e confiado ao shell
        output_handle = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
        output_path = Path(output_handle.name)
        output_handle.close()

        try:
            with tempfile.TemporaryDirectory(prefix="dwg-to-glb-") as work_dir:
                work_path = Path(work_dir)
                dwg_path = work_path / "input.dwg"
                dxf_path = work_path / "model.dxf"
                obj_path = work_path / "model.obj"

                source.seek(0)
                with dwg_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

                await self._run_dwg2dxf(dwg_path, dxf_path)
                repair_libredwg_dxf(dxf_path)
                dxf_to_obj(dxf_path, obj_path)
                convert_obj_to_glb(obj_path, output_path, recenter=True)

            with output_path.open("rb") as result:
                if result.read(4) != b"glTF":
                    raise ConversionError("O arquivo GLB gerado e invalido.")
            return output_path
        except ConversionError:
            output_path.unlink(missing_ok=True)
            raise
        except ObjConversionError as exc:
            output_path.unlink(missing_ok=True)
            raise ConversionError(str(exc)) from exc
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            raise ConversionError("Falha inesperada durante a conversao local.") from exc
