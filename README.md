# ComfySprites

Sprite design and generation webapp built on the ComfySprites stack (FastAPI, Alpine.js, SQLite, ComfyUI).

## v1 tabs

- **Design** — characters (inline outfit tags), monsters, objects, backgrounds
- **Style** — SDXL checkpoint styles
- **Act** — sprite actions and poses
- **Views** — camera framings
- **Make** — still-image generation (Make Lab workflow + detailers)
- **Settings** — ComfyUI URL, Civitai/HF tokens, tag suggestions

Deferred: Gallery, Edit, Animate, Export.

## Run

```bat
run.bat
```

Or:

```bash
python -m uvicorn webapp.main:app --host 0.0.0.0 --port 8765
```

## ComfyUI nodes

Install `ComfyUI-ComfySprites` into ComfyUI `custom_nodes/`. Provides LoRA download (Civitai/HuggingFace) and export compression nodes.

## Database

`dataset/dataset.db` is rebuilt when `SCHEMA_VERSION` in `webapp/db/models.py` changes (no migrations). Back up custom data before upgrading.

## Tests

```bash
python -m pytest test/ -q
```
