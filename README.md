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

### Make

```sh
cd ComfyUI/custom_nodes
for u in \
  https://github.com/Hakim3i/ComfyUI-ComfySprites \
  https://github.com/ltdrdata/ComfyUI-Impact-Pack \
  https://github.com/ltdrdata/ComfyUI-Impact-Subpack \
  https://github.com/1038lab/ComfyUI-RMBG \
  https://github.com/crystian/ComfyUI-Crystools; do \
  d="${u##*/}"; \
  [ -d "$d" ] || git clone --depth 1 "$u"; \
  [ -f "$d/requirements.txt" ] && pip install -r "$d/requirements.txt"; \
  [ -f "$d/install.py" ] && (cd "$d" && python install.py); \
done
```

### Animate / video

```sh
cd ComfyUI/custom_nodes
for u in \
  https://github.com/kijai/ComfyUI-KJNodes \
  https://github.com/rgthree/rgthree-comfy \
  https://github.com/pythongosssss/ComfyUI-Custom-Scripts \
  https://github.com/yolain/ComfyUI-Easy-Use \
  https://github.com/ClownsharkBatwing/RES4LYF; do \
  d="${u##*/}"; \
  [ -d "$d" ] || git clone --depth 1 "$u"; \
  [ -f "$d/requirements.txt" ] && pip install -r "$d/requirements.txt"; \
  [ -f "$d/install.py" ] && (cd "$d" && python install.py); \
done
```

## Database

`dataset/dataset.db` is rebuilt when `SCHEMA_VERSION` in `webapp/db/models.py` changes (no migrations). Back up custom data before upgrading.

## Tests

```bash
python -m pytest test/ -q
```
