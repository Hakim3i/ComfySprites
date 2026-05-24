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

This app is designed to run with this RunPod template: [ComfySprites RunPod template](https://console.runpod.io/deploy?template=t9w2im8mt8&ref=nekg08as).  
It can also work on other templates if your ComfyUI environment, model paths, and custom nodes are configured correctly.

Run these **from your ComfyUI root folder** (usually `/ComfyUI`, the folder that contains `models/` and `custom_nodes/`):

```bash
cd /ComfyUI
curl -fsSL -o runpod_setup.sh https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/scripts/runpod_setup.sh && \
curl -fsSL -o model_sources.json https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/scripts/model_sources.json && \
chmod +x runpod_setup.sh && \
./runpod_setup.sh
```

Always `cd /ComfyUI` first, then run `./runpod_setup.sh`.

If you already cloned this repo, you can run `bash path/to/ComfySprites/scripts/runpod_setup.sh` from the ComfyUI root instead; `model_sources.json` is loaded from the same directory as that script.

### `runpod_setup.sh` arguments

Pass flags after the script name. Run `./runpod_setup.sh --help` for the same list.

| Flag | What it does |
|------|----------------|
| *(none)* | Full setup: sync custom nodes, download all models from `model_sources.json`, sync workflows, then start ComfySprites. |
| `--minimal` | Only download entries marked `"required": true` in `model_sources.json`. Combine with a profile flag to limit scope further. |
| `--app-only` | Skip custom-node sync and all model downloads; only update/clone ComfySprites and start the app. |
| `--make` | Download only **Make** dependencies: SDXL LoRAs (`loras/sdxl`), checkpoints, and upscaler. |
| `--animate` | Download only **Animate** dependencies: WAN diffusion models, LoRAs (`loras/wan`), and text encoders. |
| `--edit` | Download only **Edit** dependencies: QWEN diffusion models, LoRAs (`loras/qwen`), clip, and vae. |
| `-h`, `--help` | Print usage and exit. |

Profile flags (`--make`, `--animate`, `--edit`) filter by subfolder in `model_sources.json`. If you pass more than one profile flag, the **last** one wins.

Examples:

```bash
./runpod_setup.sh                          # everything
./runpod_setup.sh --minimal                # required models only
./runpod_setup.sh --app-only               # app update/start only
./runpod_setup.sh --make                   # SDXL / Make stack
./runpod_setup.sh --animate --minimal      # required WAN / Animate models only
./runpod_setup.sh --edit                   # QWEN / Edit stack
```

### Environment variables (setup script)

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODEL_SOURCES_URL` | GitHub `model_sources.json` | Fetch model list from a different URL instead of the local file. |
| `COMFYSPRITES_DIR` | Auto-detected | Path to the ComfySprites app (clone target if missing). |
| `COMFYSPRITES_REPO_URL` | `https://github.com/Hakim3i/ComfySprites.git` | Repo to clone when the app is not present. |
| `COMFYSPRITES_GIT_BRANCH` | `main` | Branch to clone or reset to. |
| `APP_PORT` | `3000` | Port for `npm start` after setup. |

The script installs tooling, applies `model_sources.json`, syncs workflow JSONs into ComfyUI, downloads listed weights, then starts ComfySprites. For the running app, set **`COMFY_URL`** (default `http://127.0.0.1:8188`) so the UI can reach ComfyUI.

## Requirements

- Node.js 18+ (recommended)
- A running ComfyUI instance reachable at **`COMFY_URL`** (default `http://127.0.0.1:8188`)

## Notes

- This repository ignores generated and temporary folders to keep commits clean.
- If ComfyUI is not running, the app will start but Comfy job calls will fail until the backend is available.
