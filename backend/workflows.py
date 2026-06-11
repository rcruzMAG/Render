"""ComfyUI workflow-graph builders (API format) for every app function.

Each builder returns a dict keyed by node id, matching what ComfyUI's
POST /prompt endpoint expects. Model filenames come from config.json so
users can point at fp8/GGUF variants that fit their VRAM.
"""

import random

from .config import model


def _seed(params):
    s = int(params.get("seed", -1))
    return s if s >= 0 else random.randint(0, 2**32 - 1)


def _apply_loras(graph, nid, model_in, clip_in, loras):
    """Chain LoraLoader nodes; returns (next_id, model_link, clip_link)."""
    for lora in loras or []:
        graph[str(nid)] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": model_in,
                "clip": clip_in,
                "lora_name": lora["name"],
                "strength_model": float(lora.get("strength", 1.0)),
                "strength_clip": float(lora.get("strength", 1.0)),
            },
        }
        model_in, clip_in = [str(nid), 0], [str(nid), 1]
        nid += 1
    return nid, model_in, clip_in


# ---------------------------------------------------------------- FLUX images

def flux_txt2img(p: dict) -> dict:
    """FLUX.1-dev / schnell text-to-image with optional LoRA stack.

    Uses the Comfy-Org all-in-one fp8 checkpoints that the setup wizard
    downloads — model, CLIP and VAE in a single file.
    """
    variant = ("flux_schnell_checkpoint" if p.get("model") == "flux-schnell"
               else "flux_dev_checkpoint")
    g = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": model(variant)}},
    }
    nid, m, c = _apply_loras(g, 10, ["1", 0], ["1", 1], p.get("loras"))
    g.update({
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": c, "text": p["prompt"]}},
        "5": {"class_type": "FluxGuidance",
              "inputs": {"conditioning": ["4", 0],
                         "guidance": float(p.get("guidance", 3.5))}},
        "6": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": int(p.get("width", 1024)),
                         "height": int(p.get("height", 1024)),
                         "batch_size": int(p.get("batch_size", 1))}},
        "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": m, "positive": ["5", 0], "negative": ["7", 0],
                         "latent_image": ["6", 0], "seed": _seed(p),
                         "steps": int(p.get("steps", 28)), "cfg": 1.0,
                         "sampler_name": p.get("sampler", "euler"),
                         "scheduler": p.get("scheduler", "simple"),
                         "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "90": {"class_type": "SaveImage",
               "inputs": {"images": ["9", 0], "filename_prefix": "render_studio/img"}},
    })
    return g


def sdxl_txt2img(p: dict) -> dict:
    g = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": p.get("checkpoint") or model("sdxl_checkpoint")}},
    }
    nid, m, c = _apply_loras(g, 10, ["1", 0], ["1", 1], p.get("loras"))
    g.update({
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": c, "text": p["prompt"]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": c, "text": p.get("negative_prompt", "")}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": int(p.get("width", 1024)),
                         "height": int(p.get("height", 1024)),
                         "batch_size": int(p.get("batch_size", 1))}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": m, "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": _seed(p),
                         "steps": int(p.get("steps", 30)),
                         "cfg": float(p.get("cfg", 6.0)),
                         "sampler_name": p.get("sampler", "dpmpp_2m"),
                         "scheduler": p.get("scheduler", "karras"),
                         "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "90": {"class_type": "SaveImage",
               "inputs": {"images": ["6", 0], "filename_prefix": "render_studio/img"}},
    })
    return g


# ----------------------------------------------------------- image modifiers

def img2img(p: dict) -> dict:
    """SDXL img2img restyle; `denoise` controls how much changes (0.25–0.8)."""
    g = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": p.get("checkpoint") or model("sdxl_checkpoint")}},
        "2": {"class_type": "LoadImage", "inputs": {"image": p["input_image"]}},
        "3": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
    }
    nid, m, c = _apply_loras(g, 10, ["1", 0], ["1", 1], p.get("loras"))
    g.update({
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": c, "text": p["prompt"]}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": c, "text": p.get("negative_prompt", "")}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": m, "positive": ["4", 0], "negative": ["5", 0],
                         "latent_image": ["3", 0], "seed": _seed(p),
                         "steps": int(p.get("steps", 30)),
                         "cfg": float(p.get("cfg", 6.0)),
                         "sampler_name": p.get("sampler", "dpmpp_2m"),
                         "scheduler": p.get("scheduler", "karras"),
                         "denoise": float(p.get("denoise", 0.55))}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "90": {"class_type": "SaveImage",
               "inputs": {"images": ["7", 0], "filename_prefix": "render_studio/mod"}},
    })
    return g


def kontext_edit(p: dict) -> dict:
    """FLUX.1 Kontext instruction-based editing ('make the sofa green')."""
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": model("flux_kontext_unet"),
                         "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": model("flux_clip_l"),
                         "clip_name2": model("flux_t5"), "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": model("flux_vae")}},
        "4": {"class_type": "LoadImage", "inputs": {"image": p["input_image"]}},
        "5": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["4", 0]}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": p["prompt"]}},
        "8": {"class_type": "ReferenceLatent",
              "inputs": {"conditioning": ["7", 0], "latent": ["6", 0]}},
        "9": {"class_type": "FluxGuidance",
              "inputs": {"conditioning": ["8", 0],
                         "guidance": float(p.get("guidance", 2.5))}},
        "10": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
        "11": {"class_type": "KSampler",
               "inputs": {"model": ["1", 0], "positive": ["9", 0],
                          "negative": ["10", 0], "latent_image": ["6", 0],
                          "seed": _seed(p), "steps": int(p.get("steps", 20)),
                          "cfg": 1.0, "sampler_name": "euler",
                          "scheduler": "simple", "denoise": 1.0}},
        "12": {"class_type": "VAEDecode",
               "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "90": {"class_type": "SaveImage",
               "inputs": {"images": ["12", 0], "filename_prefix": "render_studio/edit"}},
    }


# ------------------------------------------------- architecture / controlnet

# One union ControlNet covers all control types (what the wizard installs).
CONTROLNETS = {"depth": "controlnet_union", "canny": "controlnet_union",
               "mlsd": "controlnet_union"}
PREPROCESSORS = {"depth": "DepthAnythingV2Preprocessor",
                 "canny": "CannyEdgePreprocessor", "mlsd": "M-LSDPreprocessor"}


def architecture(p: dict) -> dict:
    """ControlNet-guided render from a 3D model export, sketch or photo.

    Geometry is locked by the control map; prompt + denoise control the
    materials, lighting and style.
    """
    control = p.get("control_type", "depth")
    g = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": p.get("checkpoint") or model("sdxl_checkpoint")}},
        "2": {"class_type": "LoadImage", "inputs": {"image": p["input_image"]}},
        "3": {"class_type": PREPROCESSORS[control],
              "inputs": {"image": ["2", 0], "resolution": 1024}},
        "4": {"class_type": "ControlNetLoader",
              "inputs": {"control_net_name": model(CONTROLNETS[control])}},
    }
    nid, m, c = _apply_loras(g, 20, ["1", 0], ["1", 1], p.get("loras"))
    denoise = float(p.get("denoise", 1.0))
    if denoise >= 0.999:
        g["5"] = {"class_type": "EmptyLatentImage",
                  "inputs": {"width": int(p.get("width", 1024)),
                             "height": int(p.get("height", 1024)), "batch_size": 1}}
        latent = ["5", 0]
    else:
        g["5"] = {"class_type": "VAEEncode",
                  "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}}
        latent = ["5", 0]
    g.update({
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": c, "text": p["prompt"]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": c, "text": p.get(
                  "negative_prompt",
                  "warped geometry, curved walls, distorted perspective, lowres")}},
        "8": {"class_type": "ControlNetApplyAdvanced",
              "inputs": {"positive": ["6", 0], "negative": ["7", 0],
                         "control_net": ["4", 0], "image": ["3", 0],
                         "strength": float(p.get("control_strength", 0.8)),
                         "start_percent": 0.0,
                         "end_percent": float(p.get("control_end", 0.7))}},
        "9": {"class_type": "KSampler",
              "inputs": {"model": m, "positive": ["8", 0], "negative": ["8", 1],
                         "latent_image": latent, "seed": _seed(p),
                         "steps": int(p.get("steps", 30)),
                         "cfg": float(p.get("cfg", 6.0)),
                         "sampler_name": "dpmpp_2m", "scheduler": "karras",
                         "denoise": denoise}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "90": {"class_type": "SaveImage",
               "inputs": {"images": ["10", 0], "filename_prefix": "render_studio/arch"}},
    })
    return g


# -------------------------------------------------------------- Wan 2.2 video

def _wan_common(p, high_key, low_key):
    """Shared loader nodes for Wan 2.2 two-stage (high/low noise) sampling."""
    g = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": model(high_key), "weight_dtype": "default"}},
        "2": {"class_type": "UNETLoader",
              "inputs": {"unet_name": model(low_key), "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": model("wan_text_encoder"), "type": "wan",
                         "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": model("wan_vae")}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0], "text": p["prompt"]}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0], "text": p.get(
                  "negative_prompt",
                  "static, blurry, jittery motion, deformed hands, watermark")}},
    }
    return g


def _wan_sampler_chain(g, latent_link, p):
    steps = int(p.get("steps", 20))
    cfg = float(p.get("cfg", 4.0))
    seed = _seed(p)
    mid = steps // 2
    g.update({
        "10": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["1", 0], "positive": ["7", 0], "negative": ["7", 1],
                          "latent_image": latent_link, "add_noise": "enable",
                          "noise_seed": seed, "steps": steps, "cfg": cfg,
                          "sampler_name": p.get("sampler", "uni_pc"),
                          "scheduler": "simple", "start_at_step": 0,
                          "end_at_step": mid, "return_with_leftover_noise": "enable"}},
        "11": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["2", 0], "positive": ["7", 0], "negative": ["7", 1],
                          "latent_image": ["10", 0], "add_noise": "disable",
                          "noise_seed": seed, "steps": steps, "cfg": cfg,
                          "sampler_name": p.get("sampler", "uni_pc"),
                          "scheduler": "simple", "start_at_step": mid,
                          "end_at_step": steps,
                          "return_with_leftover_noise": "disable"}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}},
        "13": {"class_type": "CreateVideo",
               "inputs": {"images": ["12", 0], "fps": int(p.get("fps", 16))}},
        "90": {"class_type": "SaveVideo",
               "inputs": {"video": ["13", 0], "filename_prefix": "render_studio/vid",
                          "format": "mp4", "codec": "h264"}},
    })
    return g


def _wan_5b(p: dict, start_image: str | None) -> dict:
    """Wan 2.2 TI2V-5B: single-stage, does both T2V and I2V. This is what the
    setup wizard installs by default — 720p video on ~8 GB VRAM."""
    g = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": model("wan_5b"), "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": model("wan_text_encoder"), "type": "wan",
                         "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": model("wan22_vae")}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0], "text": p["prompt"]}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0], "text": p.get(
                  "negative_prompt",
                  "static, blurry, jittery motion, deformed hands, watermark")}},
        "7": {"class_type": "Wan22ImageToVideoLatent",
              "inputs": {"vae": ["4", 0],
                         "width": int(p.get("width", 1280)),
                         "height": int(p.get("height", 704)),
                         "length": int(p.get("frames", 121)),
                         "batch_size": 1}},
        "10": {"class_type": "KSampler",
               "inputs": {"model": ["1", 0], "positive": ["5", 0],
                          "negative": ["6", 0], "latent_image": ["7", 0],
                          "seed": _seed(p), "steps": int(p.get("steps", 20)),
                          "cfg": float(p.get("cfg", 5.0)),
                          "sampler_name": p.get("sampler", "uni_pc"),
                          "scheduler": "simple", "denoise": 1.0}},
        "12": {"class_type": "VAEDecode",
               "inputs": {"samples": ["10", 0], "vae": ["4", 0]}},
        "13": {"class_type": "CreateVideo",
               "inputs": {"images": ["12", 0], "fps": int(p.get("fps", 24))}},
        "90": {"class_type": "SaveVideo",
               "inputs": {"video": ["13", 0], "filename_prefix": "render_studio/vid",
                          "format": "mp4", "codec": "h264"}},
    }
    if start_image:
        g["8"] = {"class_type": "LoadImage", "inputs": {"image": start_image}}
        g["7"]["inputs"]["start_image"] = ["8", 0]
    return g


def wan_t2v(p: dict) -> dict:
    if p.get("model", "wan-5b") != "wan-14b":
        return _wan_5b(p, None)
    g = _wan_common(p, "wan_t2v_high", "wan_t2v_low")
    g["8"] = {"class_type": "EmptyHunyuanLatentVideo",
              "inputs": {"width": int(p.get("width", 832)),
                         "height": int(p.get("height", 480)),
                         "length": int(p.get("frames", 81)), "batch_size": 1}}
    g = _wan_sampler_chain(g, ["8", 0], p)
    for nid in ("10", "11"):
        g[nid]["inputs"]["positive"] = ["5", 0]
        g[nid]["inputs"]["negative"] = ["6", 0]
    return g


def wan_i2v(p: dict) -> dict:
    if p.get("model", "wan-5b") != "wan-14b":
        return _wan_5b(p, p["input_image"])
    g = _wan_common(p, "wan_i2v_high", "wan_i2v_low")
    g["8"] = {"class_type": "LoadImage", "inputs": {"image": p["input_image"]}}
    g["7"] = {"class_type": "WanImageToVideo",
              "inputs": {"positive": ["5", 0], "negative": ["6", 0],
                         "vae": ["4", 0], "start_image": ["8", 0],
                         "width": int(p.get("width", 832)),
                         "height": int(p.get("height", 480)),
                         "length": int(p.get("frames", 81)), "batch_size": 1}}
    return _wan_sampler_chain(g, ["7", 2], p)


def wan_animate(p: dict) -> dict:
    """Wan 2.2 Animate: drive a character image with a reference video.

    mode 'animate'  -> character performs the reference video's motion.
    mode 'replace'  -> character replaces the person inside the reference video.
    """
    g = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": model("wan_animate"), "weight_dtype": "default"}},
        "2": {"class_type": "UNETLoader",
              "inputs": {"unet_name": model("wan_animate"), "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": model("wan_text_encoder"), "type": "wan",
                         "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": model("wan_vae")}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0],
                         "text": p.get("prompt", "a person moving naturally")}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0],
                         "text": p.get("negative_prompt",
                                       "blurry, deformed, extra limbs, watermark")}},
        "20": {"class_type": "LoadImage", "inputs": {"image": p["character_image"]}},
        "21": {"class_type": "LoadVideo", "inputs": {"file": p["reference_video"]}},
        "22": {"class_type": "GetVideoComponents", "inputs": {"video": ["21", 0]}},
        "23": {"class_type": "WanAnimateToVideo",
               "inputs": {"positive": ["5", 0], "negative": ["6", 0],
                          "vae": ["4", 0],
                          "reference_image": ["20", 0],
                          "video_frames": ["22", 0],
                          "mode": p.get("mode", "animate"),
                          "width": int(p.get("width", 832)),
                          "height": int(p.get("height", 480)),
                          "length": int(p.get("frames", 77)),
                          "batch_size": 1}},
    }
    g = _wan_sampler_chain(g, ["23", 2], p)
    for nid in ("10", "11"):
        g[nid]["inputs"]["positive"] = ["23", 0]
        g[nid]["inputs"]["negative"] = ["23", 1]
    return g


# -------------------------------------------------------------------- upscale

def upscale(p: dict) -> dict:
    g = {
        "1": {"class_type": "LoadImage", "inputs": {"image": p["input_image"]}},
        "2": {"class_type": "UpscaleModelLoader",
              "inputs": {"model_name": model("upscale_model")}},
        "3": {"class_type": "ImageUpscaleWithModel",
              "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "90": {"class_type": "SaveImage",
               "inputs": {"images": ["3", 0], "filename_prefix": "render_studio/up"}},
    }
    if float(p.get("refine_denoise", 0)) > 0:
        g.update({
            "4": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": model("sdxl_checkpoint")}},
            "5": {"class_type": "VAEEncode",
                  "inputs": {"pixels": ["3", 0], "vae": ["4", 2]}},
            "6": {"class_type": "CLIPTextEncode",
                  "inputs": {"clip": ["4", 1],
                             "text": p.get("prompt", "high quality, sharp, detailed")}},
            "7": {"class_type": "CLIPTextEncode",
                  "inputs": {"clip": ["4", 1], "text": "blurry, artifacts"}},
            "8": {"class_type": "KSampler",
                  "inputs": {"model": ["4", 0], "positive": ["6", 0],
                             "negative": ["7", 0], "latent_image": ["5", 0],
                             "seed": _seed(p), "steps": 20, "cfg": 5.0,
                             "sampler_name": "dpmpp_2m", "scheduler": "karras",
                             "denoise": float(p.get("refine_denoise", 0.3))}},
            "9": {"class_type": "VAEDecode",
                  "inputs": {"samples": ["8", 0], "vae": ["4", 2]}},
        })
        g["90"]["inputs"]["images"] = ["9", 0]
    return g


BUILDERS = {
    "image": lambda p: (flux_txt2img if str(p.get("model", "flux-dev")).startswith("flux")
                        else sdxl_txt2img)(p),
    "video_t2v": wan_t2v,
    "video_i2v": wan_i2v,
    "img2img": img2img,
    "kontext": kontext_edit,
    "architecture": architecture,
    "animate": wan_animate,
    "upscale": upscale,
}
