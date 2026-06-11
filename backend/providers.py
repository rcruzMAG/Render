"""Optional cloud compute: fal.ai and Replicate connectors.

Used when a tab's Compute selector is switched away from Local (ComfyUI) —
e.g. for 720p video without the VRAM. Keys live in config.json and never
leave the machine except in requests to the chosen provider.
"""

import asyncio

import httpx

from . import config


class ProviderError(RuntimeError):
    pass


# Task -> hosted model endpoints. Mirrors the local model lineup.
FAL_MODELS = {
    "image": "fal-ai/flux/dev",
    "kontext": "fal-ai/flux-pro/kontext",
    "video_t2v": "fal-ai/wan/v2.2-a14b/text-to-video",
    "video_i2v": "fal-ai/wan/v2.2-a14b/image-to-video",
}

REPLICATE_MODELS = {
    "image": "black-forest-labs/flux-dev",
    "kontext": "black-forest-labs/flux-kontext-dev",
    "video_t2v": "wan-video/wan-2.2-t2v-fast",
    "video_i2v": "wan-video/wan-2.2-i2v-fast",
}


async def run_fal(task: str, params: dict) -> list[dict]:
    key = config.load()["providers"].get("fal", {}).get("api_key", "")
    if not key:
        raise ProviderError("No fal.ai API key set — add one in Settings.")
    model_id = FAL_MODELS.get(task)
    if not model_id:
        raise ProviderError(f"Task '{task}' has no fal.ai mapping; run it locally.")
    payload = {"prompt": params.get("prompt", "")}
    if params.get("image_url"):
        payload["image_url"] = params["image_url"]
    if task == "image":
        payload.update({
            "image_size": {"width": int(params.get("width", 1024)),
                           "height": int(params.get("height", 1024))},
            "num_inference_steps": int(params.get("steps", 28)),
            "guidance_scale": float(params.get("guidance", 3.5)),
        })
    headers = {"Authorization": f"Key {key}"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"https://queue.fal.run/{model_id}",
                         json=payload, headers=headers)
        if r.status_code not in (200, 201):
            raise ProviderError(f"fal.ai error: {r.text[:500]}")
        status_url = r.json().get("status_url")
        response_url = r.json().get("response_url")
        for _ in range(600):
            s = await c.get(status_url, headers=headers)
            if s.json().get("status") == "COMPLETED":
                break
            await asyncio.sleep(2)
        else:
            raise ProviderError("fal.ai job timed out")
        result = (await c.get(response_url, headers=headers)).json()
    return _collect_urls(result)


async def run_replicate(task: str, params: dict) -> list[dict]:
    token = config.load()["providers"].get("replicate", {}).get("api_token", "")
    if not token:
        raise ProviderError("No Replicate API token set — add one in Settings.")
    model_id = REPLICATE_MODELS.get(task)
    if not model_id:
        raise ProviderError(f"Task '{task}' has no Replicate mapping; run it locally.")
    inputs = {"prompt": params.get("prompt", "")}
    if params.get("image_url"):
        inputs["image"] = params["image_url"]
    if task == "image":
        inputs.update({"num_inference_steps": int(params.get("steps", 28)),
                       "guidance": float(params.get("guidance", 3.5))})
    headers = {"Authorization": f"Bearer {token}", "Prefer": "wait=60"}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            f"https://api.replicate.com/v1/models/{model_id}/predictions",
            json={"input": inputs}, headers=headers)
        if r.status_code not in (200, 201):
            raise ProviderError(f"Replicate error: {r.text[:500]}")
        pred = r.json()
        poll_url = pred.get("urls", {}).get("get")
        while pred.get("status") in ("starting", "processing"):
            await asyncio.sleep(2)
            pred = (await c.get(poll_url, headers=headers)).json()
        if pred.get("status") != "succeeded":
            raise ProviderError(f"Replicate job {pred.get('status')}: "
                                f"{str(pred.get('error'))[:500]}")
    return _collect_urls(pred.get("output"))


def _collect_urls(result) -> list[dict]:
    """Normalize provider responses to [{url, kind}]."""
    urls = []

    def walk(node):
        if isinstance(node, str) and node.startswith("http"):
            urls.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(result)
    out = []
    for u in urls:
        kind = "video" if any(u.split("?")[0].endswith(ext)
                              for ext in (".mp4", ".webm", ".mov")) else "image"
        out.append({"url": u, "kind": kind})
    return out


async def run(provider: str, task: str, params: dict) -> list[dict]:
    if provider == "fal":
        return await run_fal(task, params)
    if provider == "replicate":
        return await run_replicate(task, params)
    raise ProviderError(f"Unknown provider '{provider}'")
