from __future__ import annotations

from research.data import krx_api


def test_cfg_falls_back_to_project_root_env_not_data_env(tmp_path, monkeypatch):
    monkeypatch.delenv("KRX_API_KEY", raising=False)
    monkeypatch.delenv("KRX_BASE_URL", raising=False)

    root = tmp_path
    (root / "data" / "krx").mkdir(parents=True)
    (root / ".env").write_text('KRX_API_KEY="root-key"\nKRX_BASE_URL="https://root.example"\n')
    (root / "data" / ".env").write_text('KRX_API_KEY="data-key"\nKRX_BASE_URL="https://data.example"\n')

    monkeypatch.setattr(krx_api, "STORE", str(root / "data" / "krx"))

    key, base = krx_api._cfg()

    assert key == "root-key"
    assert base == "https://root.example"


def test_cfg_prefers_env_vars_over_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv("KRX_API_KEY", "env-key")
    monkeypatch.setenv("KRX_BASE_URL", "https://env.example")
    monkeypatch.setattr(krx_api, "STORE", str(tmp_path / "data" / "krx"))

    key, base = krx_api._cfg()

    assert key == "env-key"
    assert base == "https://env.example"
