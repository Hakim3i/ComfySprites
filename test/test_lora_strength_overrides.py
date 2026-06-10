"""Photo Lab session LoRA strength overrides."""

from __future__ import annotations

from webapp.db.test_seed import TEST_CHARACTER_SLUG, TEST_STYLE_SLUG


def test_build_character_lora_strength_override(client):
    filename = "char-override-test.safetensors"
    put = client.put(
        f"/api/characters/{TEST_CHARACTER_SLUG}",
        json={
            "slug": TEST_CHARACTER_SLUG,
            "lora": {
                "filename": filename,
                "name": "Override Test",
                "trigger": "override_test",
                "strength": 1.0,
            },
        },
    )
    assert put.status_code == 200, put.text
    try:
        body = client.post(
            "/api/build",
            json={
                "character": TEST_CHARACTER_SLUG,
                "style": TEST_STYLE_SLUG,
                "animation": "none",
                "seed": 42,
                "lora_strength_overrides": {"character": 0.42},
            },
        ).json()
        for block in ("sdxl", "refine_sdxl"):
            by_kind = {
                x["kind"]: x["strength"]
                for x in body[block]["loras"]
                if isinstance(x, dict)
            }
            assert by_kind.get("character") == 0.42, block
    finally:
        client.put(
            f"/api/characters/{TEST_CHARACTER_SLUG}",
            json={"slug": TEST_CHARACTER_SLUG, "lora": None},
        )


def test_workflow_character_lora_strength_from_override(client):
    from webapp.comfyui.workflow import build_result_to_make_lab

    filename = "wf-char-override.safetensors"
    put = client.put(
        f"/api/characters/{TEST_CHARACTER_SLUG}",
        json={
            "slug": TEST_CHARACTER_SLUG,
            "lora": {
                "filename": filename,
                "trigger": "wf_override",
                "strength": 1.0,
            },
        },
    )
    assert put.status_code == 200, put.text
    try:
        build = client.post(
            "/api/build",
            json={
                "character": TEST_CHARACTER_SLUG,
                "style": TEST_STYLE_SLUG,
                "animation": "none",
                "seed": 42,
                "lora_strength_overrides": {"character": 0.55},
            },
        ).json()
        wf = build_result_to_make_lab(build)
        infer_nodes = [
            node
            for node in wf.values()
            if isinstance(node, dict)
            and node.get("class_type") == "LoraLoader"
            and str((node.get("_meta") or {}).get("title") or "").startswith(
                "Inference LoRA"
            )
            and (node.get("inputs") or {}).get("lora_name") == filename
        ]
        assert len(infer_nodes) == 1
        assert infer_nodes[0]["inputs"]["strength_model"] == 0.55
    finally:
        client.put(
            f"/api/characters/{TEST_CHARACTER_SLUG}",
            json={"slug": TEST_CHARACTER_SLUG, "lora": None},
        )


def test_build_omits_character_lora_when_strength_zero(client):
    filename = "char-zero-strength.safetensors"
    put = client.put(
        f"/api/characters/{TEST_CHARACTER_SLUG}",
        json={
            "slug": TEST_CHARACTER_SLUG,
            "lora": {
                "filename": filename,
                "trigger": "zero_test",
                "strength": 0.0,
            },
        },
    )
    assert put.status_code == 200, put.text
    assert put.json()["lora"]["strength"] == 0.0
    try:
        body = client.post(
            "/api/build",
            json={
                "character": TEST_CHARACTER_SLUG,
                "style": TEST_STYLE_SLUG,
                "animation": "none",
                "seed": 42,
            },
        ).json()
        for block in ("sdxl", "refine_sdxl"):
            kinds = [x.get("kind") for x in body[block].get("loras", [])]
            assert "character" not in kinds, block
    finally:
        client.put(
            f"/api/characters/{TEST_CHARACTER_SLUG}",
            json={"slug": TEST_CHARACTER_SLUG, "lora": None},
        )


def test_build_spin_box_override_enables_zero_saved_character_lora(client):
    """Saved STR 0 + session spin above 0 must load the LoRA file."""
    filename = "char-zero-saved-spin-on.safetensors"
    put = client.put(
        f"/api/characters/{TEST_CHARACTER_SLUG}",
        json={
            "slug": TEST_CHARACTER_SLUG,
            "lora": {
                "filename": filename,
                "trigger": "spin_on",
                "strength": 0.0,
            },
        },
    )
    assert put.status_code == 200, put.text
    try:
        body = client.post(
            "/api/build",
            json={
                "character": TEST_CHARACTER_SLUG,
                "style": TEST_STYLE_SLUG,
                "animation": "none",
                "seed": 42,
                "lora_strength_overrides": {"character": 0.77},
            },
        ).json()
        by_kind = {
            x["kind"]: x["strength"]
            for x in body["sdxl"]["loras"]
            if isinstance(x, dict)
        }
        assert by_kind.get("character") == 0.77
    finally:
        client.put(
            f"/api/characters/{TEST_CHARACTER_SLUG}",
            json={"slug": TEST_CHARACTER_SLUG, "lora": None},
        )


def test_build_session_override_zero_omits_character_lora(client):
    from webapp.comfyui.workflow import build_result_to_make_lab

    filename = "char-override-zero.safetensors"
    put = client.put(
        f"/api/characters/{TEST_CHARACTER_SLUG}",
        json={
            "slug": TEST_CHARACTER_SLUG,
            "lora": {
                "filename": filename,
                "trigger": "override_zero",
                "strength": 0.8,
            },
        },
    )
    assert put.status_code == 200, put.text
    try:
        build = client.post(
            "/api/build",
            json={
                "character": TEST_CHARACTER_SLUG,
                "style": TEST_STYLE_SLUG,
                "animation": "none",
                "seed": 42,
                "lora_strength_overrides": {"character": 0},
            },
        ).json()
        kinds = [x.get("kind") for x in build["sdxl"].get("loras", [])]
        assert "character" not in kinds
        wf = build_result_to_make_lab(build)
        filenames = [
            (node.get("inputs") or {}).get("lora_name")
            for node in wf.values()
            if isinstance(node, dict)
            and node.get("class_type") == "LoraLoader"
        ]
        assert filename not in filenames
    finally:
        client.put(
            f"/api/characters/{TEST_CHARACTER_SLUG}",
            json={"slug": TEST_CHARACTER_SLUG, "lora": None},
        )
