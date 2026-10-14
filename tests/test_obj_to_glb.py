import json
import struct
from pathlib import Path

from app.obj_to_glb import convert_obj_to_glb


def test_converts_obj_faces_and_lines_to_glb(tmp_path: Path) -> None:
    source = tmp_path / "model.obj"
    output = tmp_path / "model.glb"
    source.write_text(
        "\n".join(
            (
                "v 0 0 0",
                "v 1 0 0",
                "v 1 1 0",
                "v 0 1 0",
                "f 1 2 3 4",
                "l 1 3 4",
            )
        ),
        encoding="utf-8",
    )

    convert_obj_to_glb(source, output)

    data = output.read_bytes()
    magic, version, length = struct.unpack("<4sII", data[:12])
    json_length = struct.unpack("<I", data[12:16])[0]
    document = json.loads(data[20 : 20 + json_length])
    assert magic == b"glTF"
    assert version == 2
    assert length == len(data)
    assert [primitive["mode"] for primitive in document["meshes"][0]["primitives"]] == [4, 1]
