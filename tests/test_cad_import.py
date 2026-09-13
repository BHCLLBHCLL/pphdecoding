"""Parasolid .x_t import via Cradle pskernel (cabdecoding path)."""
from __future__ import annotations

from pathlib import Path

import pytest

import cad_import
import ps_facet2_nodes as ps

BOX_XT = Path(__file__).resolve().parents[1] / "tests" / "box" / "box.x_t"


@pytest.mark.skipif(not ps.available(),
                    reason="Cradle pskernel.dll not installed")
def test_tessellate_box_xt():
    assert BOX_XT.is_file()
    parts = ps.tessellate_xt(BOX_XT.read_bytes())
    assert len(parts) == 1
    box = parts[0]
    assert len(box.points) == 8
    assert len(box.triangles) == 12
    mn, mx = box.points.min(0), box.points.max(0)
    assert abs(float(mn.min()) - 0.0) < 1e-12
    assert abs(float(mx.max()) - 0.01) < 1e-12


@pytest.mark.skipif(not cad_import.available(),
                    reason="Cradle pskernel.dll not installed")
def test_import_xt_file_box():
    bodies = cad_import.import_xt_file(BOX_XT, adaptive=True)
    assert len(bodies) == 1
    assert bodies[0].name  # stem fallback if PK name weak
    assert len(bodies[0].tess.points) == 8
    assert len(bodies[0].tess.triangles) == 12


@pytest.mark.skipif(not cad_import.available(),
                    reason="Cradle pskernel.dll not installed")
def test_tris_to_polydata():
    import pph_vtk

    bodies = cad_import.import_xt_file(BOX_XT)
    pd = pph_vtk.tris_to_polydata(
        bodies[0].tess.points, bodies[0].tess.triangles)
    assert pd is not None
    assert pd.GetNumberOfPoints() >= 8
    assert pd.GetNumberOfCells() == 12
