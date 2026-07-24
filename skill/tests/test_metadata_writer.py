"""Unit tests for metadata_writer.

Covers pure helpers (no LLM, no server) and the .tds injection round-trip
via a fake TSC server that speaks the two methods `_apply_column_
descriptions_via_tds` calls: download() + publish(). We build a real
.tdsx zip on disk, hand it back through the fake, and read the .tds
XML that comes out to confirm <column><desc> injection + orphan pruning.
"""
from __future__ import annotations

import io
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from skill.scripts import metadata_writer as mw


# --- pure helpers --------------------------------------------------------

def test_safe_name_replaces_unsafe():
    assert mw._safe_name("a b/c*d.csv") == "a_b_c_d.csv"
    assert mw._safe_name("") == "out"
    assert mw._safe_name("kept_1-2.hyper") == "kept_1-2.hyper"


def test_strip_fence_removes_backticks():
    assert mw._strip_fence("```json\n{\"a\":1}\n```") == "{\"a\":1}"
    assert mw._strip_fence("no fences here") == "no fences here"


def test_parse_json_extracts_object_from_prose():
    raw = "sure, here it is:\n{\"ds_description\": \"x\", \"columns\": []}\nthanks!"
    assert mw._parse_json(raw) == {"ds_description": "x", "columns": []}


def test_coerce_sample_caps_rows_and_long_strings():
    rows = [{"a": "x" * 90, "b": 1}] * 10
    out = mw._coerce_sample(rows, max_rows=3)
    assert len(out) == 3
    assert out[0]["a"] == "..."
    assert out[0]["b"] == 1


def test_coerce_sample_ignores_non_dicts():
    assert mw._coerce_sample([["not", "a", "dict"], 42, None]) == []


# --- .tds injection via a fake TSC server -------------------------------

class _FakeDSItem:
    def __init__(self, project_id="proj-luid", name="ds"):
        self.project_id = project_id
        self.name = name
        self.description = ""
        self.id = "ds-luid"


class _FakeDSAPI:
    """Just enough of TSC's DatasourcesAPI to drive
    `_apply_column_descriptions_via_tds` end-to-end.
    """

    def __init__(self, tdsx_source: Path):
        self._tdsx_source = tdsx_source
        self.published_tdsx: Path | None = None

    def get_by_id(self, luid):
        return _FakeDSItem()

    def download(self, luid, filepath, include_extract=True):
        dst = Path(filepath) / self._tdsx_source.name
        shutil.copy(self._tdsx_source, dst)
        return str(dst)

    def publish(self, ds_item, path, mode):
        # Capture what got pushed so the test can inspect it.
        self.published_tdsx = Path(path)
        pub = _FakeDSItem()
        return pub


class _FakeServer:
    def __init__(self, tdsx_source: Path):
        self.datasources = _FakeDSAPI(tdsx_source)


def _make_seed_tdsx(work_dir: Path) -> Path:
    """Build a minimal .tdsx with one existing column (to test update)
    and one stale/orphan column (to test pruning)."""
    tds_xml = (
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<datasource>\n"
        "  <column name='[kept_col]' caption='kept_col' "
        "datatype='string' role='dimension' type='nominal'/>\n"
        "  <column name='[orphan_col]' caption='orphan_col' "
        "datatype='string' role='dimension' type='nominal'>\n"
        "    <desc><formatted-text><run>stale</run></formatted-text></desc>\n"
        "  </column>\n"
        "</datasource>\n"
    )
    tds_path = work_dir / "seed.tds"
    tds_path.write_text(tds_xml)

    tdsx_path = work_dir / "seed.tdsx"
    with zipfile.ZipFile(tdsx_path, "w") as zf:
        zf.writestr("seed.tds", tds_xml)
        # No hyper sidecar — the method tolerates that.
    return tdsx_path


def test_tds_injection_updates_and_prunes(tmp_path):
    seed = _make_seed_tdsx(tmp_path)
    server = _FakeServer(seed)
    work = tmp_path / "work"

    result = mw._apply_column_descriptions_via_tds(
        server,
        luid="ds-luid",
        descriptions={
            "kept_col": "The canonical value column.",
            "new_col": "A brand-new column added by the writer.",
        },
        column_types={"kept_col": "string", "new_col": "decimal"},
        work_dir=work,
    )

    assert result["status"] == "ok", result
    assert result["updated_column_elements"] == 1  # kept_col
    assert result["added_column_elements"] == 1    # new_col
    assert result["removed_orphan_elements"] == 1  # orphan_col

    assert server.datasources.published_tdsx is not None
    with zipfile.ZipFile(server.datasources.published_tdsx) as zf:
        with zf.open("seed.tds") as f:
            tree = ET.parse(f)
    cols_by_name = {c.get("name"): c for c in tree.getroot().findall("./column")}

    assert "[orphan_col]" not in cols_by_name, "orphan should be pruned"
    assert "[kept_col]" in cols_by_name
    assert "[new_col]" in cols_by_name

    # Update path: existing desc replaced with new text
    kept = cols_by_name["[kept_col]"]
    assert kept.findtext(".//run") == "The canonical value column."

    # Add path: new_col got a datatype/role/type from column_types
    new = cols_by_name["[new_col]"]
    assert new.get("datatype") == "real"
    assert new.get("role") == "measure"
    assert new.findtext(".//run") == "A brand-new column added by the writer."


def test_tds_injection_skips_when_no_descriptions(tmp_path):
    seed = _make_seed_tdsx(tmp_path)
    server = _FakeServer(seed)
    result = mw._apply_column_descriptions_via_tds(
        server, luid="ds-luid", descriptions={}, work_dir=tmp_path / "w"
    )
    assert result["status"] == "skipped"
    assert server.datasources.published_tdsx is None


def test_apply_ds_description_ok_and_error():
    class _OKDSAPI:
        def get_by_id(self, luid):
            return _FakeDSItem()

        def update(self, item):
            assert item.description == "the desc"

    class _OKServer:
        def __init__(self):
            self.datasources = _OKDSAPI()

    assert mw._apply_ds_description(_OKServer(), "luid", "the desc") == {"status": "ok"}

    class _BadDSAPI(_OKDSAPI):
        def update(self, item):
            raise RuntimeError("boom")

    class _BadServer:
        def __init__(self):
            self.datasources = _BadDSAPI()

    r = mw._apply_ds_description(_BadServer(), "luid", "x")
    assert r["status"] == "error"
    assert r["type"] == "RuntimeError"
    assert "boom" in r["message"]
