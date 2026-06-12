"""Smoke tests — every v1 page and core API returns 200 on a fresh DB."""



from __future__ import annotations



import pytest



ROUTES = [

    "/",

    "/design",

    "/design?type=characters",

    "/design?type=backgrounds",

    "/design/monsters/new",

    "/design/objects/new",

    "/characters/new",

    "/animations",

    "/animations/new",

    "/animations/standing_idle",

    "/styles",

    "/styles/new",

    "/views",

    "/views/new",

    "/views/close-up",

    "/backgrounds/new",

    "/make",

    "/settings",

    "/api/health",

    "/api/character-attributes",

    "/api/characters",

    "/api/animations",

    "/api/views",

    "/api/styles",

    "/api/backgrounds",

    "/api/dropdowns",

]





@pytest.mark.parametrize("path", ROUTES)

def test_route_returns_200(client, path):

    r = client.get(path)

    assert r.status_code == 200, f"{path} -> {r.status_code}\n{r.text[:400]}"





def test_dropdowns_payload_shape(client):

    r = client.get("/api/dropdowns")

    assert r.status_code == 200

    body = r.json()

    for key in (

        "characters",

        "animations",

        "styles",

        "backgrounds",

        "views",

        "orientations",

        "sampler_hints",

        "scheduler_hints",

        "dimension_hints",

        "style_defaults",

        "revision",

    ):

        assert key in body, f"missing key {key}"

    assert "dialogue_languages" not in body

    assert "close-up" in body["views"]


def test_views_list_shows_coomfy_taxonomy(client):
    """All Coomfy camera views (labels + framing clauses) are seeded."""
    from webapp.db.views_defaults import CANONICAL_VIEW_KEYS_BY_KIND, load_view_defaults

    shipped = {v.key: v for v in load_view_defaults()}
    assert len(shipped) == 57

    r = client.get("/api/views")
    assert r.status_code == 200
    rows = {row["key"]: row for row in r.json()}
    assert len(rows) >= len(shipped)

    for key, spec in shipped.items():
        row = rows[key]
        assert row["label"] == spec.label, key
        assert row["framing_clause"] == spec.framing_clause, key

    for kind, expected in CANONICAL_VIEW_KEYS_BY_KIND.items():
        for key in expected:
            assert key in rows, f"expected {kind} view {key!r} in /api/views"

    page = client.get("/views")
    assert page.status_code == 200
    assert "Cowboy shot (mid-thigh up)" in page.text
    assert "From outside (through window / doorway)" in page.text
    assert "Pussy focus" in page.text


def test_api_create_character_round_trip(client):

    payload = {

        "slug": "agent_test",

        "display_name": "Agent Test",

        "name_tag": "agent_test",

        "identity_core": ["agent_test", "1girl", "solo"],

        "hair_color": "brown hair",

    }

    r = client.post("/api/characters", json=payload)

    assert r.status_code == 201, r.text

    assert r.json()["slug"] == "agent_test"

    client.delete("/api/characters/agent_test")

