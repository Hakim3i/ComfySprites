"""Load and patch the LTX Video Studio ComfyUI workflow."""

from __future__ import annotations

import copy
from typing import Any

from ..pipeline_builder import _instantiate_node, build_pipeline
from ..power_lora import patch_power_lora_loader
from ...services.ltx.text import format_ltx_negative, parse_ltx_negative_blocks

SULPHUR_EXPERIMENTAL_LORA_FILENAME = (
    "LTX_SulphurEXP_LoRA_fro99-avgrank105.safetensors"
)
SULPHUR_EXPERIMENTAL_LORA_URL = (
    "https://huggingface.co/maximsobolev275/LTX-SulphurExperimental-LoRA-Optimized/"
    "resolve/main/LTX_SulphurEXP_LoRA_fro99-avgrank105.safetensors"
)
_SULPHUR_STRENGTH = 0.35

_VIDEO_STUDIO_MODELS = {
    "ltx23_eros": "ltx2310eros_v1_FP8.safetensors",
    "eros": "ltx2310eros_v1_FP8.safetensors",
    "ltx23_golden_lace": "DasiwaLTX23_goldenLaceV3.safetensors",
    "golden_lace": "DasiwaLTX23_goldenLaceV3.safetensors",
}
_LTX_CLIP_1 = "gemma_3_12B_it_fp8_e4m3fn.safetensors"
_LTX_CLIP_2 = "ltx-2.3_text_projection_bf16.safetensors"
_LTX_VIDEO_VAE = "LTX23_video_vae_bf16.safetensors"
_LTX_AUDIO_VAE = "LTX23_audio_vae_bf16.safetensors"


def _blueprint() -> dict[str, Any]:
    from ..pipeline_builder import _load_pipeline_blueprint

    return _load_pipeline_blueprint("ltx_studio")


def ltx_studio_patch_roles() -> dict[str, str]:
    return {
        str(k): str(v) for k, v in (_blueprint().get("patch_roles") or {}).items()
    }


VIDEO_STUDIO_COMBINE_NODE_ID = str(
    (_blueprint().get("outputs") or {}).get("video") or "export_video"
)
VIDEO_EXPORT_AUDIO_NODE_ID = str(
    (_blueprint().get("outputs") or {}).get("audio") or "export_audio"
)

_LTX_STUDIO_NODES = ltx_studio_patch_roles()


def load_ltx_studio_workflow() -> dict[str, Any]:
    return copy.deepcopy(build_pipeline("ltx_studio").workflow)


def sulphur_experimental_lora_entry() -> dict[str, Any]:
    return {
        "kind": "ltx",
        "filename": SULPHUR_EXPERIMENTAL_LORA_FILENAME,
        "name": "Sulphur Experimental",
        "strength": _SULPHUR_STRENGTH,
        "download_url": SULPHUR_EXPERIMENTAL_LORA_URL,
    }


def merge_ltx_loras(
    loras: list[dict[str, Any]] | None,
    *,
    use_sulphur_experimental: bool,
    build: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    motion = _motion_loras(loras, build)
    merged: list[dict[str, Any]] = []
    sulphur_name = SULPHUR_EXPERIMENTAL_LORA_FILENAME.lower()
    if use_sulphur_experimental:
        merged.append(sulphur_experimental_lora_entry())
    for lora in motion:
        filename = (lora.get("filename") or "").strip().lower()
        if use_sulphur_experimental and filename == sulphur_name:
            continue
        merged.append(lora)
    return merged


def _motion_loras(
    loras: list[dict[str, Any]] | None,
    build: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    from_request = _loras_from_request(loras)
    if from_request:
        return from_request
    if not build:
        return []
    ltx = build.get("ltx") if isinstance(build.get("ltx"), dict) else {}
    out: list[dict[str, Any]] = []
    from ...services.ltx.render import is_animate_video_lora_kind

    for item in ltx.get("loras") or []:
        if not isinstance(item, dict) or not (item.get("filename") or "").strip():
            continue
        kind = str(item.get("kind") or "ltx").strip().lower()
        if is_animate_video_lora_kind(kind):
            out.append(item)
    return out


def _loras_from_request(loras: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    from ...services.ltx.render import is_animate_video_lora_kind

    out: list[dict[str, Any]] = []
    for lora in loras or []:
        if not isinstance(lora, dict):
            continue
        kind = str(lora.get("kind") or "").strip().lower()
        if not is_animate_video_lora_kind(kind):
            continue
        if (lora.get("filename") or "").strip():
            out.append(lora)
    return out


def _caption_from_build(build: dict[str, Any]) -> str:
    ltx = build.get("ltx")
    if isinstance(ltx, dict):
        return str(ltx.get("caption") or ltx.get("positive") or "")
    return ""


def _negative_tags_from_build(build: dict[str, Any], kind: str) -> str:
    ltx = build.get("ltx")
    if not isinstance(ltx, dict):
        return ""
    full = str(ltx.get("negative") or "").strip()
    if full.startswith("#Video"):
        video, audio = parse_ltx_negative_blocks(full)
        return video if kind == "video" else audio
    segs = ltx.get("negative_segments")
    if isinstance(segs, list):
        source = "style_ltx_video" if kind == "video" else "style_ltx_audio"
        parts = [
            str(seg.get("text") or "").strip()
            for seg in segs
            if isinstance(seg, dict) and str(seg.get("source") or "") == source
        ]
        parts = [p for p in parts if p]
        if parts:
            return ", ".join(parts)
    return full if kind == "video" else ""


def _compose_ltx_negative(
    build: dict[str, Any],
    *,
    ltx_video_negative: str | None = None,
    ltx_audio_negative: str | None = None,
) -> str:
    vid_override = (ltx_video_negative or "").strip()
    aud_override = (ltx_audio_negative or "").strip()
    if not vid_override and not aud_override:
        ltx = build.get("ltx")
        if isinstance(ltx, dict):
            inherited = str(ltx.get("negative") or "").strip()
            if inherited.startswith("#Video"):
                return inherited
            segs = ltx.get("negative_segments")
            if isinstance(segs, list) and segs:
                return format_ltx_negative(segs)
    video = vid_override or _negative_tags_from_build(build, "video")
    audio = aud_override or _negative_tags_from_build(build, "audio")
    if not video and not audio:
        return ""
    lines = ["#Video"]
    if video:
        lines.append(video)
    lines.append("")
    lines.append("#Audio")
    if audio:
        lines.append(audio)
    return "\n".join(lines)


def _resolved_path(model_paths: dict[str, str] | None, catalog_filename: str) -> str:
    if model_paths:
        hit = model_paths.get(catalog_filename)
        if hit:
            return hit
    return catalog_filename


_FFLF_END_LOAD_ROLE = "load_end_image"
_FFLF_END_RESIZE_ROLE = "resize_end_image"
_FFLF_INPLACE_ROLE = "img_to_video_inplace"


def _apply_fflf_end_frame(
    workflow: dict[str, Any],
    *,
    end_comfy_image_name: str,
    end_frame_strength: float,
) -> None:
    """Anchor the last latent frame via LTXVImgToVideoInplaceKJ multi-image inputs."""
    end_name = (end_comfy_image_name or "").strip()
    if not end_name:
        return
    if _FFLF_INPLACE_ROLE not in workflow:
        raise ValueError(f"LTX workflow missing {_FFLF_INPLACE_ROLE!r}")

    role_to_id = {role: role for role in workflow}
    workflow[_FFLF_END_LOAD_ROLE] = _instantiate_node(
        "ltx_studio", _FFLF_END_LOAD_ROLE, role_to_id
    )
    workflow[_FFLF_END_LOAD_ROLE]["inputs"]["image"] = end_name
    role_to_id[_FFLF_END_LOAD_ROLE] = _FFLF_END_LOAD_ROLE

    workflow[_FFLF_END_RESIZE_ROLE] = _instantiate_node(
        "ltx_studio", _FFLF_END_RESIZE_ROLE, role_to_id
    )

    inplace = workflow[_FFLF_INPLACE_ROLE].setdefault("inputs", {})
    inplace["num_images"] = "2"
    inplace["num_images.image_2"] = [_FFLF_END_RESIZE_ROLE, 0]
    inplace["num_images.index_2"] = -1
    inplace["num_images.strength_2"] = float(end_frame_strength)


def patch_ltx_studio_workflow(
    *,
    comfy_image_name: str,
    model: str,
    width: int,
    height: int,
    length_seconds: int,
    fps: int,
    seed: int,
    image_strength: float,
    audio_volume: int,
    cfg: float,
    steps: int | None = None,
    shift: float | None = None,
    loras: list[dict[str, Any]] | None,
    build: dict[str, Any],
    ltx_caption: str | None = None,
    ltx_video_negative: str | None = None,
    ltx_audio_negative: str | None = None,
    use_sulphur_experimental_lora: bool = False,
    end_comfy_image_name: str | None = None,
    end_frame_strength: float = 1.0,
    request: dict[str, Any] | None = None,
    model_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    workflow = load_ltx_studio_workflow()
    nodes = _LTX_STUDIO_NODES

    workflow[nodes["load_image"]]["inputs"]["image"] = comfy_image_name
    workflow[nodes["video_width"]]["inputs"]["value"] = max(1, int(width))
    workflow[nodes["video_height"]]["inputs"]["value"] = max(1, int(height))
    workflow[nodes["video_length"]]["inputs"]["value"] = max(1, int(length_seconds))
    workflow[nodes["fps"]]["inputs"]["value"] = max(1, int(fps))
    workflow[nodes["seed"]]["inputs"]["seed"] = int(seed)
    workflow[nodes["audio_volume"]]["inputs"]["value"] = int(audio_volume)
    workflow[nodes["image_strength"]]["inputs"]["Number"] = f"{float(image_strength):.2f}"
    workflow[nodes["cfg_first_pass"]]["inputs"]["cfg"] = float(cfg)
    if steps is not None and "ltxv_scheduler" in nodes:
        workflow[nodes["ltxv_scheduler"]]["inputs"]["steps"] = max(1, int(steps))
    if shift is not None and "ltxv_scheduler" in nodes:
        workflow[nodes["ltxv_scheduler"]]["inputs"]["max_shift"] = float(shift)

    model_key = (model or "ltx23_eros").strip().lower()
    ckpt = _VIDEO_STUDIO_MODELS.get(model_key)
    if not ckpt:
        raise ValueError(f"Unknown LTX model {model!r}")
    workflow[nodes["diffusion_model"]]["inputs"]["model_name"] = _resolved_path(
        model_paths, ckpt
    )
    if "dual_clip" in nodes:
        clip = workflow[nodes["dual_clip"]]["inputs"]
        clip["clip_name1"] = _resolved_path(model_paths, _LTX_CLIP_1)
        clip["clip_name2"] = _resolved_path(model_paths, _LTX_CLIP_2)
    if "video_vae" in nodes:
        workflow[nodes["video_vae"]]["inputs"]["vae_name"] = _resolved_path(
            model_paths, _LTX_VIDEO_VAE
        )
    if "audio_vae" in nodes:
        workflow[nodes["audio_vae"]]["inputs"]["vae_name"] = _resolved_path(
            model_paths, _LTX_AUDIO_VAE
        )

    caption = (ltx_caption or "").strip() or _caption_from_build(build)
    negative = _compose_ltx_negative(
        build,
        ltx_video_negative=ltx_video_negative,
        ltx_audio_negative=ltx_audio_negative,
    )
    workflow[nodes["positive"]]["inputs"]["text"] = caption
    workflow[nodes["negative"]]["inputs"]["text"] = negative

    effective_loras = merge_ltx_loras(
        loras,
        use_sulphur_experimental=use_sulphur_experimental_lora,
        build=build,
    )
    patch_power_lora_loader(workflow[nodes["lora"]]["inputs"], effective_loras)

    if (end_comfy_image_name or "").strip():
        _apply_fflf_end_frame(
            workflow,
            end_comfy_image_name=str(end_comfy_image_name).strip(),
            end_frame_strength=float(end_frame_strength),
        )

    from ..inject_assets import patch_video_studio_export

    patch_video_studio_export(workflow, request=request or {})
    return workflow
