import json
import struct
from pathlib import Path

import ezdxf
import pytest

from app.local_converter import ConversionError, dxf_to_obj, repair_libredwg_dxf
from app.obj_to_glb import convert_obj_to_glb


def glb_document(path: Path) -> dict:
    data = path.read_bytes()
    assert data[:4] == b"glTF"
    json_length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + json_length])


def test_converts_transformed_3d_block_to_centered_glb(tmp_path: Path) -> None:
    document = ezdxf.new("R2007")
    document.header["$INSUNITS"] = 4  # milimetros
    block = document.blocks.new("PECA")
    block.add_3dface([(0, 0, 0), (1000, 0, 0), (1000, 1000, 1000), (0, 1000, 0)])
    document.modelspace().add_blockref("PECA", (5000, 2000, 3000))
    document.modelspace().add_line((5000, 2000, 3000), (5000, 2000, 4000))

    dxf_path = tmp_path / "model.dxf"
    obj_path = tmp_path / "model.obj"
    glb_path = tmp_path / "model.glb"
    document.saveas(dxf_path)

    result = dxf_to_obj(dxf_path, obj_path)
    convert_obj_to_glb(obj_path, glb_path, recenter=True)

    assert result == {"faces": 1, "lines": 1, "unsupportedAcis": 0}
    accessor = glb_document(glb_path)["accessors"][0]
    assert accessor["min"] == pytest.approx([-0.5, -0.5, -0.5])
    assert accessor["max"] == pytest.approx([0.5, 0.5, 0.5])


def test_rejects_acis_solid_instead_of_returning_partial_model(tmp_path: Path) -> None:
    document = ezdxf.new("R2007")
    solid = document.modelspace().add_3dsolid()
    solid.sat = ("700 0 0 0", "1 9.9999999999999995e-007 1e-010")
    document.modelspace().add_line((0, 0, 0), (1, 1, 1))
    dxf_path = tmp_path / "solid.dxf"
    obj_path = tmp_path / "solid.obj"
    document.saveas(dxf_path)

    with pytest.raises(ConversionError, match="ACIS/3DSOLID"):
        dxf_to_obj(dxf_path, obj_path)


def test_repairs_libredwg_mesh_without_crease_count(tmp_path: Path) -> None:
    dxf_path = tmp_path / "broken.dxf"
    dxf_path.write_text(
        "  0\nSECTION\n  0\nMESH\n 92\n         0\n 93\n         0\n"
        " 94\n         0\n  0\nENDSEC\n  0\nEOF\n",
        encoding="utf-8",
    )

    assert repair_libredwg_dxf(dxf_path) == 1
    text = dxf_path.read_text(encoding="utf-8")
    assert " 95\n         0\n" in text
