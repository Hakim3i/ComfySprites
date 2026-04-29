#!/usr/bin/env bash
set -euo pipefail

# RunPod / Linux helper: download weights onto ComfyUI and sync ComfySprites workflows from GitHub.
# Optional custom-node git sync: populate nodes[] in model_sources.json when needed.
# Run from your ComfyUI root (the directory that contains models/, custom_nodes/).
#
# CivitAI model downloads use the same embedded Python flow as ComfyUI-Coomfy runpod_setup_models.sh.
# Public CivitAI API token is set below (same key as that bundle). Override with export CIVITAI_TOKEN=...
# or a one-line ${SCRIPT_DIR}/.civitai_token file if you use a different key.
#
# ComfySprites web app (Node): after model/workflow steps, can stop node server.js, optionally git pull
# the app repo, reinstall deps, and restart (see COMFYSPRITES_* env vars below).

ROOT_DIR="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# CivitAI — public API token (embedded default; override with $CIVITAI_TOKEN env first, else .civitai_token).
if [[ -n "${CIVITAI_TOKEN:-}" ]]; then
  :
elif [[ -f "${SCRIPT_DIR}/.civitai_token" ]]; then
  CIVITAI_TOKEN="$(head -n1 "${SCRIPT_DIR}/.civitai_token" | tr -d '\r\n')"
else
  CIVITAI_TOKEN="14e82ee51d856f342cc2223a5afab58c"
fi
export CIVITAI_TOKEN

MODEL_SOURCES_JSON="${SCRIPT_DIR}/model_sources.json"
MODEL_SOURCES_URL="${MODEL_SOURCES_URL:-https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/scripts/model_sources.json}"
MODELS_DIR="${ROOT_DIR}/models"
CUSTOM_NODES_DIR="${ROOT_DIR}/custom_nodes"
DIFFUSION_DIR="${MODELS_DIR}/diffusion_models"
CHECKPOINTS_DIR="${MODELS_DIR}/checkpoints"
LORAS_DIR="${MODELS_DIR}/loras"
MMAUDIO_DIR="${MODELS_DIR}/mmaudio"
UPSCALE_MODELS_DIR="${MODELS_DIR}/upscale_models"
TEXT_ENCODERS_DIR="${MODELS_DIR}/text_encoders"
VAE_DIR="${MODELS_DIR}/vae"
WORKFLOWS_DIR="${ROOT_DIR}/user/default/workflows"
COMFYSPRITES_WORKFLOWS_RAW_URL="${COMFYSPRITES_WORKFLOWS_RAW_URL:-https://raw.githubusercontent.com/Hakim3i/ComfySprites/main/workflows}"

# ComfySprites Node app (optional tail of this script)
COMFYSPRITES_DIR="${COMFYSPRITES_DIR:-/workspace/ComfySprites}"
COMFYSPRITES_RESTART="${COMFYSPRITES_RESTART:-1}"
COMFYSPRITES_GIT_SYNC="${COMFYSPRITES_GIT_SYNC:-1}"
COMFYSPRITES_GIT_BRANCH="${COMFYSPRITES_GIT_BRANCH:-main}"

ANCHOR_NODE_NAME=""
ANCHOR_NODE_DIR=""

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

init_node_paths_from_config() {
  ANCHOR_NODE_NAME=""
  ANCHOR_NODE_DIR=""
  local node_count
  node_count="$(jq '.nodes | length' "$MODEL_SOURCES_JSON")"
  if [[ "${node_count:-0}" -eq 0 ]]; then
    log "No custom nodes configured (nodes[] empty); skipping anchor paths."
    return 0
  fi

  ANCHOR_NODE_NAME="$(jq -r '.anchor_node_name // empty' "$MODEL_SOURCES_JSON")"
  if [[ -z "$ANCHOR_NODE_NAME" || "$ANCHOR_NODE_NAME" == "null" ]]; then
    ANCHOR_NODE_NAME="$(jq -r '.nodes[0].name // empty' "$MODEL_SOURCES_JSON")"
  fi
  local anchor_dir_name
  anchor_dir_name="$(jq -r --arg n "$ANCHOR_NODE_NAME" '.nodes[]? | select(.name==$n) | .dir_name' "$MODEL_SOURCES_JSON" | head -n 1)"
  if [[ -z "$anchor_dir_name" || "$anchor_dir_name" == "null" ]]; then
    log "Warning: anchor not resolved from nodes[]; skipping anchor paths."
    return 0
  fi
  ANCHOR_NODE_DIR="${CUSTOM_NODES_DIR}/${anchor_dir_name}"
}

resolve_output_dir_key() {
  local key="$1"
  case "$key" in
    loras) echo "$LORAS_DIR" ;;
    checkpoints) echo "$CHECKPOINTS_DIR" ;;
    diffusion) echo "$DIFFUSION_DIR" ;;
    mmaudio) echo "$MMAUDIO_DIR" ;;
    upscaler) echo "$UPSCALE_MODELS_DIR" ;;
    text_encoders) echo "$TEXT_ENCODERS_DIR" ;;
    vae) echo "$VAE_DIR" ;;
    workflows) echo "$WORKFLOWS_DIR" ;;
    *)
      log "Error: unsupported output_dir_key in JSON: ${key}"
      exit 1
      ;;
  esac
}

download_civitai_group() {
  local group="$1"
  local mode="${2:-all}"
  while IFS= read -r item; do
    local skip required model_id expected_filename output_dir_key output_dir
    skip="$(jq -r '.skip_download // false' <<<"$item")"
    [[ "$skip" == "true" ]] && continue
    required="$(jq -r '.required // false' <<<"$item")"
    if [[ "$mode" == "minimal" && "$required" != "true" ]]; then
      continue
    fi
    model_id="$(jq -r '.model_id' <<<"$item")"
    expected_filename="$(jq -r '.expected_filename // ""' <<<"$item")"
    output_dir_key="$(jq -r '.output_dir_key' <<<"$item")"
    output_dir="$(resolve_output_dir_key "$output_dir_key")"
    download_civitai "$model_id" "$output_dir" "$expected_filename"
  done < <(jq -c ".groups[\"${group}\"][]?" "$MODEL_SOURCES_JSON")
}

download_hf_group() {
  local group="$1"
  local mode="${2:-all}"
  while IFS= read -r item; do
    local skip required url filename output_dir_key output_dir
    skip="$(jq -r '.skip_download // false' <<<"$item")"
    [[ "$skip" == "true" ]] && continue
    required="$(jq -r '.required // false' <<<"$item")"
    if [[ "$mode" == "minimal" && "$required" != "true" ]]; then
      continue
    fi
    url="$(jq -r '.url' <<<"$item")"
    filename="$(jq -r '.filename' <<<"$item")"
    output_dir_key="$(jq -r '.output_dir_key' <<<"$item")"
    output_dir="$(resolve_output_dir_key "$output_dir_key")"
    download_if_missing "$url" "${output_dir}/${filename}"
  done < <(jq -c ".groups[\"${group}\"][]?" "$MODEL_SOURCES_JSON")
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
  done < <(jq -c ".groups[\"${group}\"][]?" "$MODEL_SOURCES_JSON")
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
  local expected_filename="${3:-}"

  python3 - "$model_id" "$output_dir" "$expected_filename" "$CIVITAI_TOKEN" <<'PY'
import os
import subprocess
import sys
from urllib.parse import urlparse, urljoin

import requests

model_version_id = sys.argv[1]
output_dir = sys.argv[2]
expected_name = sys.argv[3] or None
token = sys.argv[4]

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
if expected_name:
    for f in files:
        if (f.get("name") or "") == expected_name:
            chosen = f
            break

if chosen is None:
    for f in files:
        if f.get("primary"):
            chosen = f
            break

if chosen is None:
    chosen = files[0]

name = chosen.get("name") or expected_name or f"civitai_{model_version_id}.bin"
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
  apt-get install -y aria2 curl git jq python3 python3-pip python3-requests
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
  local candidate

  for candidate in \
    "${SCRIPT_DIR}/${workflow_name}" \
    "${ANCHOR_NODE_DIR}/${workflow_name}" \
    "${ROOT_DIR}/${workflow_name}"; do
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
  local node_count
  node_count="$(jq '.nodes | length' "$MODEL_SOURCES_JSON")"
  if [[ "${node_count:-0}" -eq 0 ]]; then
    log "Skipping custom node git sync and overlays (nodes[] empty)."
    return 0
  fi

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

    if [[ "$name" == "$ANCHOR_NODE_NAME" ]]; then
      ANCHOR_NODE_DIR="$repo_dir"
    fi

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

  while IFS= read -r overlay; do
    local skip required source_node_name target_node_name filename source_dir_name target_dir_name src dest
    skip="$(jq -r '.skip_sync // false' <<<"$overlay")"
    [[ "$skip" == "true" ]] && continue
    required="$(jq -r '.required // false' <<<"$overlay")"
    if [[ "$mode" == "minimal" && "$required" != "true" ]]; then
      continue
    fi

    source_node_name="$(jq -r '.source_node_name' <<<"$overlay")"
    target_node_name="$(jq -r '.target_node_name' <<<"$overlay")"
    filename="$(jq -r '.filename' <<<"$overlay")"

    source_dir_name="$(jq -r ".nodes[]? | select(.name==\"${source_node_name}\") | .dir_name" "$MODEL_SOURCES_JSON" | head -n 1)"
    target_dir_name="$(jq -r ".nodes[]? | select(.name==\"${target_node_name}\") | .dir_name" "$MODEL_SOURCES_JSON" | head -n 1)"

    if [[ -z "$source_dir_name" || "$source_dir_name" == "null" || -z "$target_dir_name" || "$target_dir_name" == "null" ]]; then
      log "Skipping overlay for ${filename}: invalid source/target node mapping in JSON."
      continue
    fi

    src="${CUSTOM_NODES_DIR}/${source_dir_name}/${filename}"
    if [[ ! -f "$src" ]]; then
      src="${SCRIPT_DIR}/${filename}"
    fi

    if [[ ! -f "$src" ]]; then
      log "Skipping overlay for ${filename}: source file not found."
      continue
    fi

    dest="${CUSTOM_NODES_DIR}/${target_dir_name}/${filename}"
    if [[ ! -d "${CUSTOM_NODES_DIR}/${target_dir_name}" ]]; then
      log "Skipping overlay for ${filename}: target node directory missing."
      continue
    fi

    cp -f "$src" "$dest"
    log "Installed ${filename} overlay (${src} -> ${dest})"
  done < <(jq -c '.node_overlays[]?' "$MODEL_SOURCES_JSON")
}

restart_comfysprites_app() {
  if [[ "${COMFYSPRITES_RESTART:-1}" != "1" ]]; then
    log "COMFYSPRITES_RESTART is not 1; skipping ComfySprites stop/start."
    return 0
  fi

  local app_dir="${COMFYSPRITES_DIR}"
  if [[ ! -f "${app_dir}/server.js" ]]; then
    log "No ComfySprites app at ${app_dir}/server.js (set COMFYSPRITES_DIR); skipping restart."
    return 0
  fi

  if ! command -v node >/dev/null 2>&1; then
    log "Warning: node not in PATH; cannot restart ComfySprites. Install Node.js or set COMFYSPRITES_RESTART=0."
    return 0
  fi

  if [[ "${COMFYSPRITES_GIT_SYNC:-1}" == "1" ]] && [[ -d "${app_dir}/.git" ]]; then
    log "Git-sync ComfySprites -> origin/${COMFYSPRITES_GIT_BRANCH}"
    git -C "$app_dir" fetch origin "${COMFYSPRITES_GIT_BRANCH}" --prune
    git -C "$app_dir" checkout "${COMFYSPRITES_GIT_BRANCH}"
    git -C "$app_dir" reset --hard "origin/${COMFYSPRITES_GIT_BRANCH}"
  fi

  log "Installing npm dependencies in ${app_dir}"
  if [[ -f "${app_dir}/package-lock.json" ]]; then
    (cd "$app_dir" && npm ci)
  else
    (cd "$app_dir" && npm install)
  fi

  if pgrep -f "node server.js" >/dev/null 2>&1; then
    log "Stopping existing ComfySprites process (node server.js)"
    pkill -f "node server.js" || true
    sleep 2
  fi

  local port="${APP_PORT:-3000}"
  local host_bind="${HOST:-0.0.0.0}"
  local comfy="${COMFY_URL:-http://127.0.0.1:8188}"

  mkdir -p "${app_dir}/logs"
  log "Starting ComfySprites (HOST=${host_bind} PORT=${port} COMFY_URL=${comfy})"
  (
    cd "$app_dir"
    HOST="${host_bind}" PORT="${port}" COMFY_URL="${comfy}" \
      nohup npm start >>logs/comfysprites.log 2>&1 &
  )
  sleep 2
  log "ComfySprites log: ${app_dir}/logs/comfysprites.log"
}

sync_comfysprites_workflows_from_github() {
  local wf url out_path
  log "Syncing ComfySprites workflow JSONs -> ${WORKFLOWS_DIR}"
  for wf in Make.json Edit.json Animate.json AnimateFFLF.json AnimatePP.json RMBG.json RMBG_IMAGES.json RMBG_VIDEO.json; do
    url="${COMFYSPRITES_WORKFLOWS_RAW_URL%/}/${wf}"
    out_path="${WORKFLOWS_DIR}/${wf}"
    log "Fetching ${wf}"
    curl -fsSL --retry 5 --retry-delay 3 -o "${out_path}.part" "$url"
    mv -f "${out_path}.part" "${out_path}"
    log "Installed workflow: ${out_path}"
  done
}

run_all_model_downloads() {
  local mode="${1:-all}"
  download_civitai_group "civitai_loras" "$mode"
  download_civitai_group "civitai_checkpoints" "$mode"
  download_civitai_group "diffusion_i2v" "$mode"
  download_civitai_group "diffusion_t2v" "$mode"
  download_hf_group "hf_loras_all" "$mode"
  download_hf_group "wan_vae" "$mode"
  download_workflow_group "workflows" "$mode"
  download_hf_group "mmaudio" "$mode"
  download_hf_group "upscaler" "$mode"
  download_hf_group "text_encoders" "$mode"
}

print_usage() {
  cat <<'USAGE'
Usage: ./runpod_setup.sh [--minimal]

Run from ComfyUI root (directory containing models/ and custom_nodes/).

--minimal: only fetch CivitAI/HF rows marked required: true (useful when nodes[] is empty).

Configuration: scripts/model_sources.json (weights/groups); MODEL_SOURCES_URL to fetch JSON remotely.
Populate nodes[] only when you want git clones into custom_nodes/.

Workflow JSONs are pulled from the ComfySprites repo into user/default/workflows/ unless you
set COMFYSPRITES_WORKFLOWS_RAW_URL to another branch/base URL.

Optional: CivitAI — export CIVITAI_TOKEN or scripts/.civitai_token to override the embedded public API key.

ComfySprites app restart (after downloads): COMFYSPRITES_DIR defaults to /workspace/ComfySprites.
Set COMFYSPRITES_RESTART=0 to skip stop/start. COMFYSPRITES_GIT_SYNC=0 skips git pull in that repo.

Examples:
  ./runpod_setup.sh
  ./runpod_setup.sh --minimal
USAGE
}

parse_args() {
  if [[ $# -eq 0 ]]; then
    RUN_MODE="all"
    return
  fi

  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    print_usage
    exit 0
  fi

  if [[ "$1" == "--minimal" ]]; then
    RUN_MODE="minimal"
    shift
    if [[ $# -eq 0 ]]; then
      return
    fi
  fi

  log "This script no longer accepts runtime flags."
  print_usage
  exit 1
}

main() {
  parse_args "$@"

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
  ensure_dir "$MMAUDIO_DIR"
  ensure_dir "$UPSCALE_MODELS_DIR"
  ensure_dir "$TEXT_ENCODERS_DIR"
  ensure_dir "$VAE_DIR"
  ensure_dir "$WORKFLOWS_DIR"

  install_requirements
  ensure_model_sources
  require_model_sources
  init_node_paths_from_config

  section_sync_custom_nodes "${RUN_MODE:-all}"
  sync_comfysprites_workflows_from_github
  run_all_model_downloads "${RUN_MODE:-all}"

  restart_comfysprites_app

  log "All requested operations completed."
  log "Restart ComfyUI if needed so it picks up new models/custom nodes."
}

main "$@"
