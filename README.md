# ComfySprites

Sprite design and generation webapp built on the ComfySprites stack (FastAPI, Alpine.js, SQLite, ComfyUI).

## v1 tabs

- **Design** — characters, monsters, objects, backgrounds (skins nested under character/monster)
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

## Tests

```bash
python -m pytest test/ -q
```
