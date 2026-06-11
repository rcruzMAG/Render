"""Async client for the ComfyUI HTTP API.

Submits workflow graphs, polls history for completion, fetches output
images/videos, and uploads input media.
"""

import asyncio
import uuid

import httpx

from . import config


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or config.load()["comfyui_url"]).rstrip("/")
        self.client_id = uuid.uuid4().hex

    async def is_up(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{self.base_url}/system_stats")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def system_stats(self) -> dict:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.base_url}/system_stats")
            r.raise_for_status()
            return r.json()

    async def object_info(self, node_class: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.base_url}/object_info/{node_class}")
            r.raise_for_status()
            return r.json()

    async def list_models(self) -> dict:
        """Return checkpoints, diffusion models, loras and vaes known to ComfyUI."""
        out = {"checkpoints": [], "diffusion_models": [], "loras": [], "vaes": []}
        lookups = [
            ("CheckpointLoaderSimple", "ckpt_name", "checkpoints"),
            ("UNETLoader", "unet_name", "diffusion_models"),
            ("LoraLoader", "lora_name", "loras"),
            ("VAELoader", "vae_name", "vaes"),
        ]
        for node, field, key in lookups:
            try:
                info = await self.object_info(node)
                values = info[node]["input"]["required"][field][0]
                if isinstance(values, list):
                    out[key] = values
            except Exception:
                pass
        return out

    async def upload_media(self, filename: str, data: bytes) -> str:
        """Upload an input image/video; returns the server-side filename."""
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{self.base_url}/upload/image",
                files={"image": (filename, data)},
                data={"overwrite": "true"},
            )
            r.raise_for_status()
            return r.json()["name"]

    async def queue(self, workflow: dict) -> str:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": self.client_id},
            )
            if r.status_code != 200:
                raise ComfyError(f"ComfyUI rejected workflow: {r.text[:2000]}")
            return r.json()["prompt_id"]

    async def wait(self, prompt_id: str, poll_s: float = 1.5,
                   timeout_s: float = 3600, progress_cb=None) -> dict:
        """Poll /history until the prompt completes; returns the history entry."""
        elapsed = 0.0
        async with httpx.AsyncClient(timeout=15) as c:
            while elapsed < timeout_s:
                r = await c.get(f"{self.base_url}/history/{prompt_id}")
                if r.status_code == 200:
                    hist = r.json()
                    if prompt_id in hist:
                        entry = hist[prompt_id]
                        status = entry.get("status", {})
                        if status.get("status_str") == "error":
                            msgs = [
                                m[1].get("exception_message", "")
                                for m in status.get("messages", [])
                                if m[0] == "execution_error"
                            ]
                            raise ComfyError("; ".join(msgs) or "execution error")
                        if entry.get("outputs"):
                            return entry
                if progress_cb:
                    progress_cb(elapsed)
                await asyncio.sleep(poll_s)
                elapsed += poll_s
        raise ComfyError("timed out waiting for ComfyUI")

    async def fetch_outputs(self, history_entry: dict) -> list[dict]:
        """Download every output image/video; returns [{filename, bytes, kind}]."""
        results = []
        async with httpx.AsyncClient(timeout=300) as c:
            for node_output in history_entry.get("outputs", {}).values():
                for key, kind in (("images", "image"), ("gifs", "video"),
                                  ("videos", "video")):
                    for item in node_output.get(key, []):
                        if item.get("type") == "temp":
                            continue
                        r = await c.get(
                            f"{self.base_url}/view",
                            params={
                                "filename": item["filename"],
                                "subfolder": item.get("subfolder", ""),
                                "type": item.get("type", "output"),
                            },
                        )
                        r.raise_for_status()
                        results.append({
                            "filename": item["filename"],
                            "bytes": r.content,
                            "kind": kind,
                        })
        return results

    async def run(self, workflow: dict, progress_cb=None) -> list[dict]:
        prompt_id = await self.queue(workflow)
        entry = await self.wait(prompt_id, progress_cb=progress_cb)
        return await self.fetch_outputs(entry)
