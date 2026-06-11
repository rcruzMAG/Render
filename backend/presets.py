"""Recommended parameter sets per task, served to the UI at /api/presets.

These mirror the tables in README.md — change them here and the UI
pre-fills update automatically.
"""

PRESETS = {
    "image": {
        "flux-dev": {
            "label": "FLUX.1-dev — best quality (recommended)",
            "steps": 28, "guidance": 3.5, "sampler": "euler",
            "scheduler": "simple", "width": 1024, "height": 1024,
            "notes": "Guidance 2.5–4. No negative prompt needed. Keep total "
                     "pixels under ~2MP.",
        },
        "flux-schnell": {
            "label": "FLUX.1-schnell — 4-step drafts",
            "steps": 4, "guidance": 0.0, "sampler": "euler",
            "scheduler": "simple", "width": 1024, "height": 1024,
            "notes": "Distilled: guidance is ignored. Use for fast iteration, "
                     "then re-run the keeper on FLUX.1-dev.",
        },
        "sdxl": {
            "label": "SDXL — biggest LoRA/ControlNet ecosystem",
            "steps": 30, "cfg": 6.0, "sampler": "dpmpp_2m",
            "scheduler": "karras", "width": 1024, "height": 1024,
            "negative_prompt": "lowres, bad anatomy, watermark, jpeg artifacts",
            "notes": "CFG 5–7. Portrait 896×1152, landscape 1152×896.",
        },
    },
    "modify": {
        "touchup": {"label": "Subtle touch-up / relight", "denoise": 0.35,
                    "notes": "Keeps composition and identity."},
        "restyle": {"label": "Restyle, keep structure (recommended)",
                    "denoise": 0.55,
                    "notes": "The sweet spot for most edits."},
        "reimagine": {"label": "Heavy reimagining", "denoise": 0.72,
                      "notes": "Structure starts to drift above ~0.75."},
        "kontext": {"label": "FLUX Kontext — instruction edit", "steps": 20,
                    "guidance": 2.5,
                    "notes": "Plain-language commands: 'replace the sky with "
                             "sunset', 'make it watercolor'. Preserves identity."},
    },
    "architecture": {
        "model_render": {
            "label": "From 3D model render (recommended)",
            "control_type": "depth", "control_strength": 0.8,
            "control_end": 0.7, "denoise": 1.0, "steps": 30, "cfg": 6.0,
            "notes": "Depth ControlNet locks massing/geometry; the prompt "
                     "supplies materials and lighting.",
        },
        "line_drawing": {
            "label": "From sketch / elevation / line drawing",
            "control_type": "canny", "control_strength": 0.85,
            "control_end": 0.8, "denoise": 1.0, "steps": 30, "cfg": 6.5,
            "notes": "Canny follows drawn lines tightly.",
        },
        "interior_photo": {
            "label": "Re-materialize an interior photo",
            "control_type": "mlsd", "control_strength": 0.7,
            "control_end": 0.65, "denoise": 0.6, "steps": 30, "cfg": 6.0,
            "notes": "MLSD keeps walls/edges straight; denoise 0.5–0.65 swaps "
                     "finishes and furniture while keeping the room.",
        },
    },
    "video": {
        "fast_480p": {
            "label": "480p fast (with Lightning LoRA)",
            "width": 832, "height": 480, "frames": 81, "fps": 16,
            "steps": 4, "cfg": 1.0,
            "notes": "Requires the Wan 2.2 Lightning (lightx2v) LoRA from the "
                     "LoRA Hub. 5–10× faster.",
        },
        "quality_480p": {
            "label": "480p quality (recommended)",
            "width": 832, "height": 480, "frames": 81, "fps": 16,
            "steps": 20, "cfg": 4.0,
            "notes": "Native Wan 2.2 sampling, two-stage high/low noise.",
        },
        "quality_720p": {
            "label": "720p quality (16 GB+ VRAM)",
            "width": 1280, "height": 720, "frames": 81, "fps": 16,
            "steps": 24, "cfg": 4.0,
            "notes": "Best quality; roughly 4× the compute of 480p.",
        },
    },
    "animate": {
        "default": {
            "label": "Character animation / swap",
            "width": 832, "height": 480, "frames": 77, "fps": 16,
            "steps": 20, "cfg": 4.0,
            "notes": "Use a clean, front-facing character image. Reference "
                     "clips work best at 3–5 s with one visible person.",
        },
    },
    "upscale": {
        "default": {
            "label": "4x-UltraSharp + refine",
            "refine_denoise": 0.3,
            "notes": "Refine pass at denoise 0.2–0.35 adds detail without "
                     "changing content; set 0 to skip.",
        },
    },
}
