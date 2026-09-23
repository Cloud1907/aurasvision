"""Çıkış ucu kimliksiz de çalışır — anahtar/oturum olmadan 401 dönerse arayüz
"Oturum kapatılamadı" der ve kullanıcı çıkamaz (saha bildirimi 2026-09-23)."""
from fastapi.testclient import TestClient

from src import server


def test_cikis_anahtarsiz_ve_cerezsiz_200_doner(monkeypatch):
    monkeypatch.setattr(server, "API_TOKEN", "gizli-anahtar")
    monkeypatch.setattr(server, "_kullanici_var", lambda: True)
    with TestClient(server.app) as c:
        r = c.post("/api/cikis")
    assert r.status_code == 200 and r.json() == {"ok": True}
    # Oturum çerezi silinir (Set-Cookie ile boş/expired)
    assert "oturum" in r.headers.get("set-cookie", "").lower() or "set-cookie" in r.headers


def test_diger_yazma_uclari_anahtarsiz_401(monkeypatch):
    monkeypatch.setattr(server, "API_TOKEN", "gizli-anahtar")
    monkeypatch.setattr(server, "_kullanici_var", lambda: False)
    with TestClient(server.app) as c:
        assert c.post("/api/cameras", json={"name": "x", "source": "y"}).status_code == 401
