"""Partner routes removed — regression guards."""

from __future__ import annotations


def test_partner_api_routes_gone(client):
    assert client.get("/api/partners").status_code == 404
    assert client.post("/api/partners", json={"slug": "x"}).status_code == 404


def test_design_partners_tab_redirects(client):
    r = client.get("/design?type=partners", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"].endswith("/design?type=characters")


def test_character_create_rejects_partner_role(client):
    r = client.post(
        "/api/characters",
        json={"slug": "bad_role", "role": "partner"},
    )
    assert r.status_code == 422
