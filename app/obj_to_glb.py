from __future__ import annotations

import json
import math
import struct
import sys
import zipfile
from array import array
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO


class ObjConversionError(ValueError):
    pass


@contextmanager
def _open_obj_text(path: Path) -> Iterator[TextIO]:
    with path.open("rb") as source:
        signature = source.read(4)

    if signature.startswith(b"PK"):
        with zipfile.ZipFile(path) as archive:
            candidates = [item for item in archive.infolist() if item.filename.lower().endswith(".obj")]
            if not candidates:
                raise ObjConversionError("O pacote OBJ nao contem um modelo.")
            with archive.open(candidates[0]) as raw:
                import io

                with io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as text:
                    yield text
        return

    with path.open("r", encoding="utf-8", errors="replace") as text:
        yield text


def _vertex_index(token: str, vertex_count: int) -> int:
    raw = int(token.split("/", 1)[0])
    index = raw - 1 if raw > 0 else vertex_count + raw
    if index < 0 or index >= vertex_count:
        raise ObjConversionError("O OBJ retornado possui indices invalidos.")
    return index


def convert_obj_to_glb(source_path: Path, output_path: Path, *, recenter: bool = False) -> None:
    positions = array("f")
    triangles = array("I")
    lines = array("I")
    bounds_min = [math.inf, math.inf, math.inf]
    bounds_max = [-math.inf, -math.inf, -math.inf]

    try:
        with _open_obj_text(source_path) as source:
            for raw_line in source:
                parts = raw_line.strip().split()
                if not parts:
                    continue
                if parts[0] == "v" and len(parts) >= 4:
                    coordinates = [float(parts[1]), float(parts[2]), float(parts[3])]
                    if not all(math.isfinite(value) for value in coordinates):
                        raise ObjConversionError("O OBJ retornado possui coordenadas invalidas.")
                    positions.extend(coordinates)
                    for axis, value in enumerate(coordinates):
                        bounds_min[axis] = min(bounds_min[axis], value)
                        bounds_max[axis] = max(bounds_max[axis], value)
                elif parts[0] == "f" and len(parts) >= 4:
                    vertex_count = len(positions) // 3
                    face = [_vertex_index(token, vertex_count) for token in parts[1:]]
                    for offset in range(1, len(face) - 1):
                        triangles.extend((face[0], face[offset], face[offset + 1]))
                elif parts[0] == "l" and len(parts) >= 3:
                    vertex_count = len(positions) // 3
                    path = [_vertex_index(token, vertex_count) for token in parts[1:]]
                    for offset in range(len(path) - 1):
                        lines.extend((path[offset], path[offset + 1]))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        if isinstance(exc, ObjConversionError):
            raise
        raise ObjConversionError("Nao foi possivel interpretar o OBJ retornado.") from exc

    if not positions or (not triangles and not lines):
        raise ObjConversionError("O OBJ retornado nao possui geometria exportavel.")

    if recenter:
        center = [(minimum + maximum) / 2.0 for minimum, maximum in zip(bounds_min, bounds_max)]
        for offset in range(0, len(positions), 3):
            for axis in range(3):
                positions[offset + axis] -= center[axis]
        bounds_min = [minimum - center[axis] for axis, minimum in enumerate(bounds_min)]
        bounds_max = [maximum - center[axis] for axis, maximum in enumerate(bounds_max)]

    if sys.byteorder != "little":
        positions.byteswap()
        triangles.byteswap()
        lines.byteswap()

    binary = bytearray()
    buffer_views: list[dict[str, int]] = []
    accessors: list[dict[str, object]] = []

    def append_buffer(data: bytes, target: int) -> int:
        while len(binary) % 4:
            binary.append(0)
        offset = len(binary)
        binary.extend(data)
        buffer_views.append(
            {"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target}
        )
        return len(buffer_views) - 1

    position_view = append_buffer(positions.tobytes(), 34962)
    accessors.append(
        {
            "bufferView": position_view,
            "componentType": 5126,
            "count": len(positions) // 3,
            "type": "VEC3",
            "min": bounds_min,
            "max": bounds_max,
        }
    )

    primitives: list[dict[str, object]] = []
    for indices, mode in ((triangles, 4), (lines, 1)):
        if not indices:
            continue
        index_view = append_buffer(indices.tobytes(), 34963)
        accessors.append(
            {
                "bufferView": index_view,
                "componentType": 5125,
                "count": len(indices),
                "type": "SCALAR",
                "min": [min(indices)],
                "max": [max(indices)],
            }
        )
        primitives.append({"attributes": {"POSITION": 0}, "indices": len(accessors) - 1, "mode": mode})

    document = {
        "asset": {"version": "2.0", "generator": "conversor-dwg"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": primitives}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    binary.extend(b"\0" * (-len(binary) % 4))

    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary)
    with output_path.open("wb") as destination:
        destination.write(struct.pack("<4sII", b"glTF", 2, total_length))
        destination.write(struct.pack("<I4s", len(json_chunk), b"JSON"))
        destination.write(json_chunk)
        destination.write(struct.pack("<I4s", len(binary), b"BIN\0"))
        destination.write(binary)
