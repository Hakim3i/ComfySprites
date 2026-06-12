"""Style defaults must come from dataset JSON — no Python fallback literals."""

from __future__ import annotations

import json

import pytest

from webapp.services.catalog import style_defaults as sd


def test_load_style_defaults_requires_new_style_key(tmp_path, monkeypatch):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    bad = dataset / "style_defaults.json"
    bad.write_text(json.dumps({"base_model_options": ["sdxl"]}), encoding="utf-8")
    monkeypatch.setattr(sd, "DEFAULTS_PATH", bad)
    monkeypatch.setattr(sd, "_SHIPPED_DEFAULTS_PATH", dataset / "missing.json")
    with pytest.raises(ValueError, match="new_style"):
        sd.load_style_defaults()


def test_ensure_style_defaults_copies_shipped_when_missing(tmp_path, monkeypatch):
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    shipped_file = shipped / "style_defaults.json"
    shipped_file.write_text(
        json.dumps(
            {
                "new_style": {
                    "base_model": "sdxl",
                    "sampler": "Euler a",
                    "scheduler": "normal",
                    "steps": 25,
                    "cfg_scale": 5.0,
                    "clip_skip": 2,
                    "width": 832,
                    "height": 1216,
                },
                "base_model_options": ["sdxl"],
                "sampler_hints": ["Euler a"],
                "scheduler_hints": ["normal"],
                "dimension_hints": [[832, 1216]],
            }
        ),
        encoding="utf-8",
    )
    dataset = tmp_path / "writable"
    dataset.mkdir()
    target = dataset / "style_defaults.json"
    monkeypatch.setattr(sd, "DEFAULTS_PATH", target)
    monkeypatch.setattr(sd, "_SHIPPED_DEFAULTS_PATH", shipped_file)
    sd.ensure_style_defaults_file()
    assert target.is_file()
    ns = sd.new_style_defaults()
    assert ns.sampler == "Euler a"
