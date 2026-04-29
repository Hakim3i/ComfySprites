# ComfySprites

ComfySprites is a local web app for creating and processing sprite assets using ComfyUI workflows. It provides a browser interface and a Node.js backend to manage sprite generation jobs, editing jobs, animation jobs, and export-ready outputs.

The app is designed for fast iteration: select or upload inputs, run a workflow, preview results, and save generated assets to organized local folders.

## What This Project Does

- Connects to a ComfyUI server over WebSocket/API.
- Runs preconfigured workflows from the `workflows/` folder.
- Supports sprite creation, editing, animation, and video-related processing flows.
- Stores generated files and metadata locally for easy reuse.
- Serves a simple frontend (`index.html`, `styles.css`, `js/`) backed by an Express server (`server.js`, `src/`).

## Project Structure

- `server.js` - app entry point.
- `src/` - routes, controllers, services, and utility modules.
- `workflows/` - ComfyUI workflow JSON files used by the app.
- `data/` - local app data and configuration files.
- `outputs/` - generated assets (ignored in git).
- `temp_export/` - temporary export artifacts (ignored in git).

## Run Locally

```bash
npm install
npm start
```

Then open: `http://localhost:3000`

### Ports and ComfyUI

- **ComfySprites** listens on **`PORT`** (default **3000**). Expose **3000** in Docker or RunPod when you need browser access to this app.
- **ComfyUI** should run on **`127.0.0.1:8188`** (the usual default). ComfySprites reads **`COMFY_URL`** (default `http://127.0.0.1:8188`). If your ComfyUI uses another host or port, set `COMFY_URL` accordingly (for example `COMFY_URL=http://127.0.0.1:8188 npm start`).

## RunPod: download models and sync workflows

Run these **from your ComfyUI root** (the folder that contains `models/` and `custom_nodes/`):

```bash
curl -fsSL -o runpod_setup.sh https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/scripts/runpod_setup.sh
curl -fsSL -o model_sources.json https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/scripts/model_sources.json
chmod +x runpod_setup.sh
./runpod_setup.sh
```

If you hit stale-cache issues, use this one-shot “clean download + run” command:

```bash
curl -fsSL -o runpod_setup.sh https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/scripts/runpod_setup.sh && \
curl -fsSL -o model_sources.json https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/scripts/model_sources.json && \
chmod +x runpod_setup.sh && \
./runpod_setup.sh
```

The script installs tooling, applies `model_sources.json` (unless you override `MODEL_SOURCES_URL`), syncs workflow JSONs into ComfyUI, downloads listed weights, and can restart the ComfySprites app under **`COMFYSPRITES_DIR`** (see `scripts/runpod_setup.sh` for env vars such as `COMFYSPRITES_RESTART`, `APP_PORT`, `COMFY_URL`).

If you already cloned this repo, you can run `bash path/to/ComfySprites/scripts/runpod_setup.sh` from the ComfyUI root instead; `model_sources.json` is loaded from the same directory as that script.

## Requirements

- Node.js 18+ (recommended)
- A running ComfyUI instance reachable at **`COMFY_URL`** (default `http://127.0.0.1:8188`)

## Notes

- This repository ignores generated and temporary folders to keep commits clean.
- If ComfyUI is not running, the app will start but Comfy job calls will fail until the backend is available.
