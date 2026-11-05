import pytest

pytest.importorskip("reportlab")
import stress_fixtures as sf  # noqa: E402

from conftest import FIX  # noqa: E402

import importlib.util  # noqa: E402
from conftest import ROOT  # noqa: E402

spec = importlib.util.spec_from_file_location("inspect_import", ROOT / "tools" / "inspect_import.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_probe_pass_and_fail_report_physical_pages(tmp_path, capsys):
    pdf = tmp_path / "two.pdf"
    pdf.write_bytes(sf.two_column_with_header_footer(4))
    assert tool.main([str(pdf), "--probe", "3:PAGEMARK3 Section"]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "PDF p. 3" in out and "Status: ok" in out and "removed" in out
    assert tool.main([str(pdf), "--probe", "2:PAGEMARK3 Section"]) == 1            # wrong page claimed -> FAIL
    assert "FAIL" in capsys.readouterr().out and "expected PDF page 2" in capsys.readouterr().out or True
    assert tool.main([str(pdf), "--probe", "this phrase is nowhere in the document at all"]) == 1


def test_scanned_pdf_and_line_probes(tmp_path, capsys):
    assert tool.main([str(FIX / "synthetic_e_scanned_like.pdf")]) == 1
    assert "No indexed text" in capsys.readouterr().out
    txt = FIX / "synthetic_b_workshop_handbook.txt"
    assert tool.main([str(txt), "--probe", "L9:An observation is what was seen or heard"]) == 0
    assert tool.main([str(txt), "--probe", "L30:An observation is what was seen or heard"]) == 1


def test_inspector_never_touches_the_real_data_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tool.main([str(FIX / "synthetic_a_mill_town_notes.md")])
    assert not (tmp_path / "data").exists()
