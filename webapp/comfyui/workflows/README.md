# ComfyUI workflow assets

Make Lab graphs are composed at runtime from decomposed node files — not monolithic JSON exports.

| Path | Role |
|------|------|
| [`nodes/`](./nodes/) | One JSON file per ComfyUI node (symbolic `@registry` links). |
| [`registry.json`](./registry.json) | Symbol → stable node id map (`sampler` → `103`, …). |
| [`recipes/make_lab.json`](./recipes/make_lab.json) | Base include sets + optional stage groups (refine, upscale, encode). |
| [`recipes/detailers.json`](./recipes/detailers.json) | Detailer region catalog (order, labels, adetailer keys) — not ComfyUI nodes. |
| [`nodes/rmbg.json`](./nodes/rmbg.json) | Optional post-export background removal node template. |
| [`workflow_builder.py`](../workflow_builder.py) | Loads nodes, resolves links, applies wiring profiles. |

## Detailers

Detailer **node templates** live under [`nodes/`](./nodes/):

| Template | Role |
|----------|------|
| `detail_detector_first.json` / `detail_detector_chain.json` | Ultralytics detector per region |
| `detail_sam.json` | Shared SAM loader |
| `detailer_fd_first.json` / `detailer_fd_chain.json` | FaceDetailer (one per enabled region) |
| `detailer_pos_*.json` | Regional positive CLIP |
| `detailer_to_pipe_*.json` / `detailer_from_pipe.json` | Before-refine refine handoff |

[`recipes/detailers.json`](./recipes/detailers.json) is a region catalog only (order, labels, `adetailer_key`) — not a ComfyUI node. Per-region FaceDetailer scalars and detector model overrides come from `dataset/make_lab_detailers.json`.

### Composed node ids

| Role | Id pattern |
|------|------------|
| FaceDetailer | `detail:{region}:fd` |
| Positive prompt | `detail:{region}:pos` |
| Detector | `detail:{region}:det` |
| SAM | `detail:{region}:sam` |
| ToBasicPipe / FromBasicPipe | `detail:{region}:to_pipe` / `detail:{region}:from_pipe` |

Wiring (before vs after refine, upscale timing) is applied by [`workflow_builder.py`](../workflow_builder.py).

## Editing the graph

1. Edit the relevant file under [`nodes/`](./nodes/) (or add a new node file + register it in [`registry.json`](./registry.json)).
2. Update [`recipes/make_lab.json`](./recipes/make_lab.json) if the node belongs to a new optional stage group.
3. Update wiring in [`workflow_builder.py`](../workflow_builder.py) (`_apply_inference_links` / `_apply_detailer_links`) when link topology changes.
4. Run `pytest test/test_workflow_builder.py test/test_make_lab_detailers.py test/test_make_lab_inference_stages.py test/test_comfyui_workflow.py`.

## ControlNet (Make Lab)

Inference-time ControlNet chains are injected by [`make_lab_controlnet.py`](../make_lab_controlnet.py) before the main KSampler. Animation uploads are already preprocessed maps — `LoadImage` feeds `ControlNetApplyAdvanced` directly (no aux preprocess step). Both positive and negative conditioning pass through each apply into the sampler. Node templates: `controlnet_ensure.json`, `controlnet_load_image.json`, `controlnet_loader.json`, `controlnet_apply.json`.

**ComfyUI custom nodes required on the server:**

| Package | Purpose |
|---------|---------|
| **ComfyUI-ComfySprites** (this repo) | `ComfySpritesEnsureControlNets` |

Built into ComfyUI: `ControlNetApplyAdvanced`, `LoadImage`. Weights load via `ComfySpritesControlNetLoader` (STRING filename, same pattern as SDXL/LoRA loaders).

**Preprocessor nodes (Make Lab “preprocess preview” button):** requires [ComfyUI-ControlNet-Aux](https://github.com/Fannovel16/comfyui_controlnet_aux) on the ComfyUI host (`OpenposePreprocessor`, `MiDaS-DepthMapPreprocessor`, `CannyEdgePreprocessor`). Preprocessor class names and defaults live in [`dataset/controlnet_types.json`](../../../dataset/controlnet_types.json) under each type's `preprocessor` block.

ControlNet weight filenames and download URLs live in [`dataset/controlnet_types.json`](../../../dataset/controlnet_types.json).

## Re-export from ComfyUI (optional)

Export API JSON from ComfyUI for reference, then split nodes into [`nodes/{id}.json`](./nodes/) with `@symbol` links instead of numeric cross-refs. Do not commit full-graph exports unless needed for review.
