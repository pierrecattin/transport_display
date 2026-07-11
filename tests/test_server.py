"""Endpoint tests for the config web backend (FastAPI TestClient, no systemd).

The app resolves its config path and dev-mode flag from the environment at
import time, so the fixture points them at a scratch copy and reloads the
module before handing out a client.
"""

import importlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import DISPLAY_BOUNDS

FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "config.json"


@pytest.fixture()
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Path]]:
    cfg_path = tmp_path / "config.json"
    shutil.copy(FIXTURE_CONFIG, cfg_path)
    monkeypatch.setenv("TRANSPORT_DISPLAY_CONFIG", str(cfg_path))
    monkeypatch.setenv("TRANSPORT_DISPLAY_NO_RESTART", "1")
    import server.app

    app_module = importlib.reload(server.app)
    with TestClient(app_module.app) as tc:
        yield tc, cfg_path


def test_get_config_returns_raw_json(client: tuple[TestClient, Path]) -> None:
    tc, cfg_path = client
    r = tc.get("/api/config")
    assert r.status_code == 200
    assert r.json() == json.loads(cfg_path.read_text(encoding="utf-8"))


def test_put_invalid_config_400_and_file_untouched(client: tuple[TestClient, Path]) -> None:
    tc, cfg_path = client
    before = cfg_path.read_text(encoding="utf-8")
    r = tc.put("/api/config", json={"stations": [], "destination_labels": {}})
    assert r.status_code == 400
    assert "stations" in r.json()["detail"]
    assert cfg_path.read_text(encoding="utf-8") == before
    # Validation failed before anything was written: no backup, no temp litter.
    assert list(cfg_path.parent.glob("config.json.*")) == []


def test_put_valid_config_writes_file_and_bak(client: tuple[TestClient, Path]) -> None:
    tc, cfg_path = client
    payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    payload["display"]["brightness"] = 42
    r = tc.put("/api/config", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["restart"]["ok"] is False  # dev mode: restart skipped
    on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert on_disk["display"]["brightness"] == 42
    assert cfg_path.with_name(cfg_path.name + ".bak").exists()
    assert list(cfg_path.parent.glob("*.tmp")) == []


def test_preview_returns_png_without_touching_disk(client: tuple[TestClient, Path]) -> None:
    tc, cfg_path = client
    payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    r = tc.post("/api/preview", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert list(cfg_path.parent.glob("config.json.*")) == []


def test_preview_invalid_config_400(client: tuple[TestClient, Path]) -> None:
    tc, _ = client
    r = tc.post("/api/preview", json={"stations": "nope", "destination_labels": {}})
    assert r.status_code == 400


def test_fonts_lists_bundled_bdf_stems(client: tuple[TestClient, Path]) -> None:
    tc, _ = client
    r = tc.get("/api/fonts")
    assert r.status_code == 200
    assert set(r.json()) >= {"4x6", "5x7", "6x10"}


def test_meta_bounds_match_validation(client: tuple[TestClient, Path]) -> None:
    tc, _ = client
    r = tc.get("/api/meta")
    assert r.status_code == 200
    fields = {f["key"]: f for f in r.json()["display_fields"]}
    for key, (lo, hi) in DISPLAY_BOUNDS.items():
        assert (fields[key]["min"], fields[key]["max"]) == (lo, hi)
