#!/usr/bin/env bash
set -euo pipefail

# RunPod model setup script for ComfyUI.
# - Installs required tools
# - Downloads CivitAI models (API + HTTP; redirect resolved before CDN fetch)
# - Downloads Hugging Face files
# - Skips downloads when destination file already exists

ROOT_DIR="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_SOURCES_JSON="${SCRIPT_DIR}/model_sources.json"
MODEL_SOURCES_URL="${MODEL_SOURCES_URL:-https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/scripts/model_sources.json}"
MODELS_DIR="${ROOT_DIR}/models"
CUSTOM_NODES_DIR="${ROOT_DIR}/custom_nodes"
DIFFUSION_DIR="${MODELS_DIR}/diffusion_models"
CHECKPOINTS_DIR="${MODELS_DIR}/checkpoints"
LORAS_DIR="${MODELS_DIR}/loras"
UPSCALE_MODELS_DIR="${MODELS_DIR}/upscale_models"
TEXT_ENCODERS_DIR="${MODELS_DIR}/text_encoders"
CLIP_DIR="${MODELS_DIR}/clip"
VAE_DIR="${MODELS_DIR}/vae"
WORKFLOWS_DIR="${ROOT_DIR}/user/default/workflows"

# Hardcoded only for test usage, as requested.
CIVITAI_TOKEN="14e82ee51d856f342cc2223a5afab58c"
export CIVITAI_TOKEN

# ComfySprites app location.
# - When this script lives in `ComfySprite/scripts/`, the app is typically `ComfySprite/` (SCRIPT_DIR/..).
# - When you curl this script into your ComfyUI root, the app is expected to be cloned as `./ComfySprite` (or `./ComfySprites`).
COMFYSPRITES_REPO_URL="${COMFYSPRITES_REPO_URL:-https://github.com/Hakim3i/ComfySprites.git}"
COMFYSPRITES_GIT_BRANCH="${COMFYSPRITES_GIT_BRANCH:-main}"
if [[ -z "${COMFYSPRITES_DIR:-}" ]]; then
  if [[ -f "${SCRIPT_DIR}/package.json" ]]; then
    COMFYSPRITES_DIR="${SCRIPT_DIR}"
  elif [[ -f "${SCRIPT_DIR}/../package.json" ]]; then
    COMFYSPRITES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  elif [[ -f "${SCRIPT_DIR}/ComfySprite/package.json" ]]; then
    COMFYSPRITES_DIR="${SCRIPT_DIR}/ComfySprite"
  elif [[ -f "${SCRIPT_DIR}/ComfySprites/package.json" ]]; then
    COMFYSPRITES_DIR="${SCRIPT_DIR}/ComfySprites"
  else
    # Default for "curl into ComfyUI root": clone into ./ComfySprite
    COMFYSPRITES_DIR="${ROOT_DIR}/ComfySprite"
  fi
fi
# Node app port (ComfySprites default is 3000, but allow overriding).
APP_PORT="${APP_PORT:-3000}"
RUN_MODE="all"
APP_ONLY="0"

start_comfysprites() {
  # Try to resolve the app directory even if COMFYSPRITES_DIR was not set correctly.
  if [[ ! -f "${COMFYSPRITES_DIR}/package.json" ]]; then
    local candidates=(
      "${COMFYSPRITES_DIR:-}"
      "${SCRIPT_DIR}/ComfySprite"
      "${SCRIPT_DIR}/ComfySprites"
      "${ROOT_DIR}/ComfySprite"
      "${ROOT_DIR}/ComfySprites"
    )
    for c in "${candidates[@]}"; do
      if [[ -n "$c" && -f "$c/package.json" ]]; then
        COMFYSPRITES_DIR="$c"
        break
      fi
    done
  fi

  if [[ ! -f "${COMFYSPRITES_DIR}/package.json" ]]; then
    # Auto-clone ComfySprites if it wasn't present yet (common on fresh RunPod images).
    log "ComfySprites not found; cloning ${COMFYSPRITES_REPO_URL} -> ${COMFYSPRITES_DIR}"
    rm -rf "${COMFYSPRITES_DIR}" || true
    git clone --depth 1 --branch "${COMFYSPRITES_GIT_BRANCH}" "${COMFYSPRITES_REPO_URL}" "${COMFYSPRITES_DIR}"
  elif [[ -d "${COMFYSPRITES_DIR}/.git" ]]; then
    log "Updating ComfySprites repo (${COMFYSPRITES_GIT_BRANCH})..."
    git -C "${COMFYSPRITES_DIR}" fetch origin "${COMFYSPRITES_GIT_BRANCH}" --depth 1
    git -C "${COMFYSPRITES_DIR}" checkout "${COMFYSPRITES_GIT_BRANCH}"
    # Force-sync to remote branch to handle rewritten history (force-pushes).
    git -C "${COMFYSPRITES_DIR}" reset --hard "origin/${COMFYSPRITES_GIT_BRANCH}"
  fi

  if [[ ! -f "${COMFYSPRITES_DIR}/package.json" ]]; then
    log "Error: could not find ComfySprites package.json even after clone."
    log "COMFYSPRITES_DIR='${COMFYSPRITES_DIR}'"
    exit 1
  fi

  log "Starting ComfySprites on port ${APP_PORT}..."
  cd "$COMFYSPRITES_DIR"

  # Ensure npm is available right before we try to install/start.
  if ! command -v npm >/dev/null 2>&1; then
    ensure_npm
  fi

  if [[ ! -d "node_modules" ]]; then
    log "node_modules not found; running 'npm install'..."
    npm install
  fi

  # Keep this in foreground so the container/job stays alive after downloads.
  HOST="${HOST:-0.0.0.0}" PORT="${APP_PORT}" npm start
}

log() {
  echo "[runpod-setup] $*"
}

require_model_sources() {
  if [[ ! -f "$MODEL_SOURCES_JSON" ]]; then
    ensure_model_sources
  fi
  if [[ ! -f "$MODEL_SOURCES_JSON" ]]; then
    log "Error: missing model sources file: ${MODEL_SOURCES_JSON}"
    exit 1
  fi
}

ensure_model_sources() {
  if [[ -f "$MODEL_SOURCES_JSON" ]]; then
    return 0
  fi

  log "model_sources.json not found locally; downloading from ${MODEL_SOURCES_URL}"
  curl -L --fail --retry 5 --retry-delay 3 -o "$MODEL_SOURCES_JSON" "$MODEL_SOURCES_URL"
}

resolve_output_dir_key() {
  local key="$1"
  case "$key" in
    loras) echo "$LORAS_DIR" ;;
    checkpoints) echo "$CHECKPOINTS_DIR" ;;
    diffusion|diffusion_models) echo "$DIFFUSION_DIR" ;;
    upscaler) echo "$UPSCALE_MODELS_DIR" ;;
    text_encoders) echo "$TEXT_ENCODERS_DIR" ;;
    clip) echo "$CLIP_DIR" ;;
    vae) echo "$VAE_DIR" ;;
    workflows) echo "$WORKFLOWS_DIR" ;;
    *)
      log "Error: unsupported output_dir_key in JSON: ${key}"
      exit 1
      ;;
  esac
}

resolve_output_path() {
  local output_dir_key="$1"
  local subfolder="${2:-}"
  local base_dir
  base_dir="$(resolve_output_dir_key "$output_dir_key")"
  if [[ -n "$subfolder" && "$subfolder" != "null" ]]; then
    echo "${base_dir}/${subfolder}"
  else
    echo "$base_dir"
  fi
}

download_civitai_group() {
  local group="$1"
  local mode="${2:-all}"
  while IFS= read -r item; do
    local skip required model_id source_filename target_filename output_dir_key subfolder output_dir
    skip="$(jq -r '.skip_download // false' <<<"$item")"
    [[ "$skip" == "true" ]] && continue
    required="$(jq -r '.required // false' <<<"$item")"
    if [[ "$mode" == "minimal" && "$required" != "true" ]]; then
      continue
    fi
    model_id="$(jq -r '.model_id' <<<"$item")"
    source_filename="$(jq -r '.source_filename // .expected_filename // ""' <<<"$item")"
    target_filename="$(jq -r '.filename // ""' <<<"$item")"
    output_dir_key="$(jq -r '.output_dir_key' <<<"$item")"
    subfolder="$(jq -r '.subfolder // ""' <<<"$item")"
    output_dir="$(resolve_output_path "$output_dir_key" "$subfolder")"
    ensure_dir "$output_dir"
    download_civitai "$model_id" "$output_dir" "$source_filename" "$target_filename"
  done < <(jq -c ".models[\"${group}\"][]?" "$MODEL_SOURCES_JSON")
}

download_hf_group() {
  local group="$1"
  local mode="${2:-all}"
  while IFS= read -r item; do
    local skip required url filename output_dir_key subfolder output_dir
    skip="$(jq -r '.skip_download // false' <<<"$item")"
    [[ "$skip" == "true" ]] && continue
    required="$(jq -r '.required // false' <<<"$item")"
    if [[ "$mode" == "minimal" && "$required" != "true" ]]; then
      continue
    fi
    url="$(jq -r '.url' <<<"$item")"
    filename="$(jq -r '.filename' <<<"$item")"
    output_dir_key="$(jq -r '.output_dir_key' <<<"$item")"
    subfolder="$(jq -r '.subfolder // ""' <<<"$item")"
    output_dir="$(resolve_output_path "$output_dir_key" "$subfolder")"
    ensure_dir "$output_dir"
    download_if_missing "$url" "${output_dir}/${filename}"
  done < <(jq -c ".models[\"${group}\"][]?" "$MODEL_SOURCES_JSON")
}

download_loras_group() {
  local group="$1"
  local mode="${2:-all}"
  while IFS= read -r item; do
    local skip required source output_dir_key subfolder output_dir model_id source_filename target_filename url filename
    skip="$(jq -r '.skip_download // false' <<<"$item")"
    [[ "$skip" == "true" ]] && continue
    required="$(jq -r '.required // false' <<<"$item")"
    if [[ "$mode" == "minimal" && "$required" != "true" ]]; then
      continue
    fi

    source="$(jq -r '.source // ""' <<<"$item")"
    output_dir_key="$(jq -r '.output_dir_key' <<<"$item")"
    subfolder="$(jq -r '.subfolder // ""' <<<"$item")"
    output_dir="$(resolve_output_path "$output_dir_key" "$subfolder")"
    ensure_dir "$output_dir"

    case "$source" in
      civitai)
        model_id="$(jq -r '.model_id' <<<"$item")"
        source_filename="$(jq -r '.source_filename // .expected_filename // ""' <<<"$item")"
        target_filename="$(jq -r '.filename // ""' <<<"$item")"
        download_civitai "$model_id" "$output_dir" "$source_filename" "$target_filename"
        ;;
      hf)
        url="$(jq -r '.url' <<<"$item")"
        filename="$(jq -r '.filename' <<<"$item")"
        download_if_missing "$url" "${output_dir}/${filename}"
        ;;
      *)
        log "Error: unsupported lora source in JSON: ${source}"
        exit 1
        ;;
    esac
  done < <(jq -c ".models[\"${group}\"][]?" "$MODEL_SOURCES_JSON")
}

download_workflow_group() {
  local group="$1"
  local mode="${2:-all}"
  while IFS= read -r item; do
    local skip required kind model_id workflow_name
    skip="$(jq -r '.skip_download // false' <<<"$item")"
    [[ "$skip" == "true" ]] && continue
    required="$(jq -r '.required // false' <<<"$item")"
    if [[ "$mode" == "minimal" && "$required" != "true" ]]; then
      continue
    fi
    kind="$(jq -r '.kind' <<<"$item")"
    case "$kind" in
      civitai_workflow)
        model_id="$(jq -r '.model_id' <<<"$item")"
        download_civitai_workflow "$model_id" "$WORKFLOWS_DIR"
        ;;
      local_workflow)
        workflow_name="$(jq -r '.workflow_name' <<<"$item")"
        install_local_workflow "$workflow_name"
        ;;
      *)
        log "Error: unsupported workflow kind in JSON: ${kind}"
        exit 1
        ;;
    esac
  done < <(jq -c ".models[\"${group}\"][]?" "$MODEL_SOURCES_JSON")
}

ensure_dir() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    log "Creating directory: $dir"
    mkdir -p "$dir"
  fi
}

download_if_missing() {
  local url="$1"
  local out_path="$2"
  local out_dir
  out_dir="$(dirname "$out_path")"
  ensure_dir "$out_dir"

  if [[ -f "$out_path" ]]; then
    log "Skipping existing file: $out_path"
    return 0
  fi

  log "Downloading: $url"
  curl -L --fail --retry 5 --retry-delay 3 -o "$out_path" "$url"
}

download_civitai() {
  local model_id="$1"
  local output_dir="$2"
  local source_filename="${3:-}"
  local target_filename="${4:-}"

  python3 - "$model_id" "$output_dir" "$source_filename" "$target_filename" "$CIVITAI_TOKEN" <<'PY'
import os
import subprocess
import sys
from urllib.parse import urlparse, urljoin

import requests

model_version_id = sys.argv[1]
output_dir = sys.argv[2]
match_name = sys.argv[3] or None
target_name = sys.argv[4] or None
token = sys.argv[5]

print(
    f"[runpod-setup] CivitAI model ID {model_version_id}: fetching metadata from API...",
    flush=True,
)

api_headers = {}
if token:
    api_headers["Authorization"] = f"Bearer {token}"

api_url = f"https://civitai.com/api/v1/model-versions/{model_version_id}"
resp = requests.get(api_url, headers=api_headers, timeout=60)
resp.raise_for_status()
payload = resp.json()
files = payload.get("files") or []
if not files:
    raise RuntimeError(f"No files found for model version {model_version_id}")

chosen = None
if match_name:
    for f in files:
        if (f.get("name") or "") == match_name:
            chosen = f
            break

if chosen is None:
    for f in files:
        if f.get("primary"):
            chosen = f
            break

if chosen is None:
    chosen = files[0]

name = target_name or chosen.get("name") or match_name or f"civitai_{model_version_id}.bin"
base_url = chosen.get("downloadUrl")
if not base_url:
    raise RuntimeError(f"No downloadUrl for model version {model_version_id}")

# CivitAI download entry: add token only when not already in URL (query signing).
if token and "token=" not in base_url and "civitai.com" in base_url:
    sep = "&" if "?" in base_url else "?"
    start_url = f"{base_url}{sep}token={token}"
else:
    start_url = base_url

out_path = os.path.join(output_dir, name)
if os.path.isfile(out_path):
    print(
        f"[runpod-setup] CivitAI model ID {model_version_id}: skip (already have {name})",
        flush=True,
    )
    sys.exit(0)

tmp_path = out_path + ".part"


def needs_civitai_bearer(url: str) -> bool:
    """Bearer is for civitai.com API only; b2.civitai.com signed URLs break with extra auth."""
    if not token:
        return False
    host = (urlparse(url).hostname or "").lower()
    return host in ("civitai.com", "www.civitai.com")


# Resolve CivitAI -> CDN/B2: follow redirects manually; never send Bearer to b2.* hosts.
def resolve_download_url(url: str) -> str:
    current = url
    for _ in range(20):
        headers = {}
        if needs_civitai_bearer(current):
            headers["Authorization"] = f"Bearer {token}"
        r = requests.get(
            current,
            headers=headers,
            allow_redirects=False,
            timeout=60,
            stream=True,
        )
        try:
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("Location")
                if not loc:
                    r.raise_for_status()
                current = urljoin(current, loc)
                continue
            if r.status_code == 200:
                return current
            r.raise_for_status()
            return current
        finally:
            r.close()
    return current


print(
    f"[runpod-setup] CivitAI model ID {model_version_id}: resolving download redirect...",
    flush=True,
)
final_url = resolve_download_url(start_url)
host = (urlparse(final_url).hostname or "?")
print(
    f"[runpod-setup] CivitAI model ID {model_version_id}: download -> {name} via {host} (aria2c, 8 connections)",
    flush=True,
)
dl_headers = {
    "User-Agent": "ComfyUI-RunPod-Setup/1.0 (python-requests)",
    "Accept": "*/*",
}
if needs_civitai_bearer(final_url):
    dl_headers["Authorization"] = f"Bearer {token}"

os.makedirs(output_dir, exist_ok=True)

# Match Hearmeman24 CivitAI_Downloader: resolve redirect in Python, then aria2c on the
# final URL for multi-connection download + --summary-interval progress (aria2 cannot
# follow CivitAI->B2 redirects reliably on its own).
def download_via_requests_fallback() -> None:
    with requests.get(
        final_url,
        headers=dl_headers,
        stream=True,
        timeout=600,
        allow_redirects=True,
    ) as dl:
        dl.raise_for_status()
        total = int(dl.headers.get("Content-Length") or 0)
        done = 0
        last_log = -1
        with open(tmp_path, "wb") as f:
            for chunk in dl.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = min(100, int(done * 100 / total))
                    if pct >= last_log + 5 or done == total:
                        print(
                            f"[runpod-setup] CivitAI download {pct}% "
                            f"({done // (1024 * 1024)}MiB / {max(1, total // (1024 * 1024))}MiB)",
                            flush=True,
                        )
                        last_log = pct
                elif done // (50 * 1024 * 1024) > last_log // (50 * 1024 * 1024):
                    print(
                        f"[runpod-setup] CivitAI download {done // (1024 * 1024)}MiB (unknown total)",
                        flush=True,
                    )
                    last_log = done
    os.replace(tmp_path, out_path)


aria2_cmd = [
    "aria2c",
    "--max-connection-per-server=8",
    "--split=8",
    "--continue=true",
    "--auto-file-renaming=false",
    "--allow-overwrite=true",
    "--summary-interval=5",
    # "warn" hides aria2's periodic "*** Download Progress Summary ***" lines
    "--console-log-level=notice",
    "--download-result=full",
    f"--dir={output_dir}",
    f"--out={name}",
    final_url,
]

try:
    subprocess.run(aria2_cmd, check=True)
except FileNotFoundError:
    print("[runpod-setup] aria2c not found; using requests fallback", flush=True)
    download_via_requests_fallback()
except subprocess.CalledProcessError as e:
    print(
        f"[runpod-setup] aria2c failed ({e}); using requests fallback",
        flush=True,
    )
    if os.path.isfile(tmp_path):
        os.unlink(tmp_path)
    download_via_requests_fallback()

print(f"[runpod-setup] CivitAI model ready: {out_path}")
PY
}

download_civitai_workflow() {
  local model_id="$1"
  local workflows_dir="$2"
  local temp_dir="/tmp/civitai_workflow_${model_id}"

  ensure_dir "$workflows_dir"
  rm -rf "$temp_dir"
  mkdir -p "$temp_dir"

  log "Resolving CivitAI workflow files for model version ID ${model_id}"
  python3 - "$model_id" "$temp_dir" "$CIVITAI_TOKEN" <<'PY'
import json
import os
import sys
import requests

model_version_id = sys.argv[1]
output_dir = sys.argv[2]
token = sys.argv[3]

api_url = f"https://civitai.com/api/v1/model-versions/{model_version_id}"
resp = requests.get(api_url, timeout=30)
resp.raise_for_status()
payload = resp.json()
files = payload.get("files", [])
if not files:
    raise RuntimeError(f"No files listed for model version {model_version_id}")

# Prefer workflow-friendly assets first.
def score(file_obj):
    name = (file_obj.get("name") or "").lower()
    typ = (file_obj.get("type") or "").lower()
    ext = os.path.splitext(name)[1]
    if ext == ".zip":
        return 0
    if ext == ".json":
        return 1
    if typ == "archive":
        return 2
    return 10

sorted_files = sorted(files, key=score)
for file_obj in sorted_files:
    name = file_obj.get("name") or "download.bin"
    url = file_obj.get("downloadUrl")
    if not url:
        continue
    separator = "&" if "?" in url else "?"
    url_with_token = f"{url}{separator}token={token}"
    out_path = os.path.join(output_dir, name)
    print(f"[runpod-setup] Downloading workflow asset: {name}")
    with requests.get(url_with_token, stream=True, timeout=120) as dl:
        dl.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in dl.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
PY

  # Handle direct JSON workflow downloads.
  for json_file in "$temp_dir"/*.json; do
    [[ -e "$json_file" ]] || continue
    local base_name
    base_name="$(basename "$json_file")"
    if [[ -f "${workflows_dir}/${base_name}" ]]; then
      log "Skipping existing workflow JSON: ${workflows_dir}/${base_name}"
    else
      mv "$json_file" "${workflows_dir}/${base_name}"
      log "Installed workflow JSON: ${workflows_dir}/${base_name}"
    fi
  done

  # Extract workflow JSON files from ZIP packages if present.
  for zip_file in "$temp_dir"/*.zip; do
    [[ -e "$zip_file" ]] || continue
    log "Extracting workflow JSON from ZIP: ${zip_file}"
    python3 - "$zip_file" "$workflows_dir" <<'PY'
import os
import sys
import zipfile

zip_path = sys.argv[1]
workflows_dir = sys.argv[2]

with zipfile.ZipFile(zip_path, "r") as zf:
    for member in zf.namelist():
        if not member.lower().endswith(".json"):
            continue
        target_name = os.path.basename(member)
        if not target_name:
            continue
        target_path = os.path.join(workflows_dir, target_name)
        if os.path.exists(target_path):
            print(f"[runpod-setup] Skipping existing workflow JSON: {target_path}")
            continue
        with zf.open(member) as src, open(target_path, "wb") as dst:
            dst.write(src.read())
        print(f"[runpod-setup] Installed workflow JSON: {target_path}")
PY
  done
}

install_requirements() {
  log "Installing system and Python dependencies"
  apt-get update
  apt-get install -y aria2 curl git jq python3 python3-pip python3-requests ca-certificates

  # ComfySprites is a Node.js app. Ensure Node/npm exists before continuing.
  ensure_npm
}

ensure_npm() {
  # Install npm/Node only if it's missing.
  if command -v npm >/dev/null 2>&1; then
    return 0
  fi

  log "npm not found; installing Node.js/npm for ComfySprites..."
  apt-get update

  # 1) Try Ubuntu/Debian packages first.
  apt-get install -y nodejs || true
  apt-get install -y npm || true

  # 2) Fallback to NodeSource if still missing.
  if ! command -v npm >/dev/null 2>&1; then
    apt-get install -y gnupg || true
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - || true
    apt-get install -y nodejs || true
  fi

  # Final check.
  if ! command -v npm >/dev/null 2>&1; then
    log "Error: npm is still missing after Node.js installation."
    log "Please check network access to NodeSource and apt repositories."
    exit 1
  fi
}

sync_git_repo() {
  local repo_url="$1"
  local repo_dir="$2"

  ensure_dir "$CUSTOM_NODES_DIR"

  if [[ -d "${repo_dir}/.git" ]]; then
    log "Updating custom node: ${repo_dir}"
    git -C "$repo_dir" pull --ff-only
    return 0
  fi

  if [[ -d "$repo_dir" ]]; then
    log "Removing non-git directory before clone: ${repo_dir}"
    rm -rf "$repo_dir"
  fi

  log "Cloning custom node: ${repo_url} -> ${repo_dir}"
  git clone "$repo_url" "$repo_dir"
}

reclone_git_repo() {
  local repo_url="$1"
  local repo_dir="$2"

  ensure_dir "$CUSTOM_NODES_DIR"

  if [[ -d "$repo_dir" ]]; then
    log "Removing custom node for clean reinstall: ${repo_dir}"
    rm -rf "$repo_dir"
  fi

  log "Cloning custom node fresh: ${repo_url} -> ${repo_dir}"
  git clone "$repo_url" "$repo_dir"
}

install_local_workflow() {
  local workflow_name="$1"
  local target_path="${WORKFLOWS_DIR}/${workflow_name}"
  local source_path=""

  local candidates=(
    "${SCRIPT_DIR}/${workflow_name}"
    "${ROOT_DIR}/${workflow_name}"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" ]]; then
      source_path="$candidate"
      break
    fi
  done

  if [[ -z "$source_path" ]]; then
    log "Workflow source not found locally, skipping: ${workflow_name}"
    return 0
  fi

  if [[ -f "$target_path" ]]; then
    log "Skipping existing local workflow: ${target_path}"
    return 0
  fi

  cp "$source_path" "$target_path"
  log "Installed local workflow: ${target_path}"
}

section_sync_custom_nodes() {
  local mode="${1:-all}"
  while IFS= read -r item; do
    local skip required name repo_url dir_name reclone_env repo_dir should_reclone
    skip="$(jq -r '.skip_sync // false' <<<"$item")"
    [[ "$skip" == "true" ]] && continue
    required="$(jq -r '.required // false' <<<"$item")"
    if [[ "$mode" == "minimal" && "$required" != "true" ]]; then
      continue
    fi

    name="$(jq -r '.name' <<<"$item")"
    repo_url="$(jq -r '.repo_url' <<<"$item")"
    dir_name="$(jq -r '.dir_name' <<<"$item")"
    reclone_env="$(jq -r '.reclone_env // ""' <<<"$item")"
    repo_dir="${CUSTOM_NODES_DIR}/${dir_name}"

    should_reclone=0
    if [[ -n "$reclone_env" && "${!reclone_env:-0}" == "1" ]]; then
      should_reclone=1
    fi

    if [[ "$should_reclone" -eq 1 ]]; then
      reclone_git_repo "$repo_url" "$repo_dir"
    else
      sync_git_repo "$repo_url" "$repo_dir"
    fi
  done < <(jq -c '.nodes[]?' "$MODEL_SOURCES_JSON")
}

run_all_model_downloads() {
  local mode="${1:-all}"
  download_loras_group "loras" "$mode"
  download_civitai_group "checkpoints" "$mode"
  download_civitai_group "diffusion_models" "$mode"
  download_hf_group "upscaler" "$mode"
  download_hf_group "text_encoders" "$mode"
  download_hf_group "clip" "$mode"
  download_hf_group "vae" "$mode"
}

print_usage() {
  cat <<'USAGE'
Usage: ./runpod_setup.sh [--minimal] [--app-only]

--minimal : only process entries marked `required: true`.
--app-only: skip all model/custom-node syncing and only update/start ComfySprites.

Configuration lives in model_sources.json.
Use `required: true` in JSON entries to control what `--minimal` includes.

Examples:
  ./runpod_setup.sh
  ./runpod_setup.sh --minimal
  ./runpod_setup.sh --app-only
USAGE
}

parse_args() {
  RUN_MODE="all"
  APP_ONLY="0"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        print_usage
        exit 0
        ;;
      --minimal)
        RUN_MODE="minimal"
        ;;
      --app-only)
        APP_ONLY="1"
        ;;
      *)
        log "Unknown argument: $1"
        print_usage
        exit 1
        ;;
    esac
    shift
  done
}

main() {
  parse_args "$@"

  install_requirements

  if [[ "${APP_ONLY}" != "1" ]]; then
    if [[ ! -d "${ROOT_DIR}/models" ]]; then
      log "Error: could not find '${ROOT_DIR}/models'."
      log "Run this script from your ComfyUI root folder (the folder that contains 'models')."
      exit 1
    fi

    log "Detected ComfyUI root: ${ROOT_DIR}"

    ensure_dir "$MODELS_DIR"
    ensure_dir "$CUSTOM_NODES_DIR"
    ensure_dir "$DIFFUSION_DIR"
    ensure_dir "$CHECKPOINTS_DIR"
    ensure_dir "$LORAS_DIR"
    ensure_dir "$UPSCALE_MODELS_DIR"
    ensure_dir "$TEXT_ENCODERS_DIR"
    ensure_dir "$CLIP_DIR"
    ensure_dir "$VAE_DIR"
    ensure_dir "$WORKFLOWS_DIR"

    ensure_model_sources
    require_model_sources
    section_sync_custom_nodes "${RUN_MODE:-all}"
    run_all_model_downloads "${RUN_MODE:-all}"
  else
    log "App-only mode enabled: skipping model/custom-node downloads and sync."
  fi

  log "All requested operations completed."

  # Start ComfySprites after downloads so the web UI is immediately available.
  start_comfysprites
}

main "$@"
