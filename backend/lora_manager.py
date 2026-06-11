"""LoRA hub: curated task recommendations + live CivitAI search/download.

Search hits CivitAI's public REST API (no key needed for public models).
Downloads are saved into the ComfyUI loras directory configured in
config.json ("comfyui_loras_dir").
"""

from pathlib import Path

import httpx

from . import config

CIVITAI_API = "https://civitai.com/api/v1/models"

# Curated picks, mirrored in README.md. `search` is the CivitAI query that
# finds the model so users can pull the latest version with one click.
RECOMMENDED = [
    {"task": "Image generation", "name": "Amateur Photography",
     "base": "FLUX.1-dev", "search": "amateur photography flux",
     "why": "Kills the 'AI gloss' — candid, phone-photo realism for people "
            "and scenes."},
    {"task": "Image generation", "name": "FLUX AntiBlur",
     "base": "FLUX.1-dev", "search": "flux antiblur",
     "why": "Deeper depth of field; removes FLUX's default heavy bokeh."},
    {"task": "Image generation (speed)", "name": "FLUX.1 Turbo Alpha",
     "base": "FLUX.1-dev", "search": "flux turbo alpha",
     "why": "8-step generation at near-full quality for fast iteration."},
    {"task": "Image generation (speed)", "name": "SDXL Lightning 8-step",
     "base": "SDXL", "search": "sdxl lightning lora",
     "why": "Near-realtime SDXL drafts; pair with CFG 1–2."},
    {"task": "Image modifier / detail", "name": "Detail Tweaker XL",
     "base": "SDXL", "search": "detail tweaker xl",
     "why": "Dial micro-detail up or down with LoRA weight (−2 to +2)."},
    {"task": "Architecture — interior", "name": "Interior Design Universal",
     "base": "SDXL", "search": "interior design sdxl lora",
     "why": "Coherent furniture layout, materials and lighting for interiors."},
    {"task": "Architecture — exterior", "name": "Modern Architecture Exterior",
     "base": "SDXL", "search": "architecture exterior lora",
     "why": "Clean facades, correct glazing and photoreal exteriors."},
    {"task": "Video generation (speed)", "name": "Wan 2.2 Lightning (lightx2v)",
     "base": "Wan 2.2", "search": "wan 2.2 lightning lora",
     "why": "4-step video sampling — 5–10× faster with a small motion cost. "
            "Set steps=4, CFG=1 when active."},
    {"task": "Video generation (camera)", "name": "Wan camera-motion LoRAs",
     "base": "Wan 2.2", "search": "wan camera motion lora",
     "why": "Controlled push-in / orbit / dolly moves — great for product "
            "and architecture flythroughs."},
    {"task": "Stylized characters", "name": "Anime / Niji-style aesthetic",
     "base": "SDXL / FLUX", "search": "niji anime style lora",
     "why": "Consistent line work and palettes for illustrated characters."},
]


async def search_civitai(query: str = "", base_model: str = "",
                         sort: str = "Newest", limit: int = 24) -> list[dict]:
    """Search CivitAI for LoRAs; sort=Newest surfaces the latest releases."""
    params = {"types": "LORA", "sort": sort, "limit": limit, "nsfw": "false"}
    if query:
        params["query"] = query
    if base_model:
        params["baseModels"] = base_model
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(CIVITAI_API, params=params)
        r.raise_for_status()
        items = r.json().get("items", [])
    results = []
    for m in items:
        ver = (m.get("modelVersions") or [{}])[0]
        files = ver.get("files") or [{}]
        results.append({
            "id": m.get("id"),
            "name": m.get("name"),
            "base": ver.get("baseModel", ""),
            "version": ver.get("name", ""),
            "downloads": (m.get("stats") or {}).get("downloadCount", 0),
            "trained_words": ver.get("trainedWords", []),
            "download_url": files[0].get("downloadUrl") or ver.get("downloadUrl"),
            "filename": files[0].get("name", ""),
            "page": f"https://civitai.com/models/{m.get('id')}",
            "thumb": next((img.get("url") for img in ver.get("images", [])
                           if img.get("type") != "video"), None),
        })
    return results


def _loras_dir() -> Path:
    cfg = config.load()
    d = cfg.get("comfyui_loras_dir") or ""
    if not d:
        raise RuntimeError(
            "Set 'comfyui_loras_dir' in config.json (e.g. "
            "/path/to/ComfyUI/models/loras) to enable downloads.")
    path = Path(d).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


async def download_lora(url: str, filename: str) -> str:
    """Stream a LoRA file from CivitAI into the ComfyUI loras directory."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid filename")
    dest = _loras_dir() / filename
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    f.write(chunk)
    return str(dest)
