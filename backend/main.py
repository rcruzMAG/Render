"""Render Studio backend: FastAPI app, job queue, and all API endpoints.

Run with:  python -m backend.main
"""

import asyncio
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, lora_manager, providers, workflows
from .comfy_client import ComfyClient, ComfyError
from .presets import PRESETS

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Render Studio")

# In-memory job registry; the frontend polls /api/jobs/{id}.
JOBS: dict[str, dict] = {}


class JobRequest(BaseModel):
    task: str                       # key into workflows.BUILDERS
    params: dict = {}
    compute: str = "local"          # local | fal | replicate


def _new_job(task: str) -> dict:
    job = {"id": uuid.uuid4().hex[:12], "task": task, "status": "queued",
           "created": time.time(), "outputs": [], "error": None}
    JOBS[job["id"]] = job
    return job


async def _run_local(job: dict, task: str, params: dict):
    builder = workflows.BUILDERS.get(task)
    if not builder:
        raise ComfyError(f"unknown task '{task}'")
    client = ComfyClient()
    if not await client.is_up():
        raise ComfyError(
            "ComfyUI is not reachable at "
            f"{client.base_url} — start it, or switch this tab's Compute "
            "to a cloud provider in Settings.")
    outputs = await client.run(builder(params))
    for out in outputs:
        dest = OUTPUT_DIR / f"{job['id']}_{out['filename'].replace('/', '_')}"
        dest.write_bytes(out["bytes"])
        job["outputs"].append({"url": f"/outputs/{dest.name}", "kind": out["kind"]})


async def _run_cloud(job: dict, compute: str, task: str, params: dict):
    job["outputs"] = await providers.run(compute, task, params)


async def _execute(job: dict, req: JobRequest):
    job["status"] = "running"
    try:
        if req.compute == "local":
            await _run_local(job, req.task, req.params)
        else:
            await _run_cloud(job, req.compute, req.task, req.params)
        job["status"] = "done"
    except (ComfyError, providers.ProviderError) as e:
        job["status"] = "error"
        job["error"] = str(e)
    except Exception as e:  # surface unexpected failures to the UI
        job["status"] = "error"
        job["error"] = f"{type(e).__name__}: {e}"


@app.post("/api/jobs")
async def create_job(req: JobRequest):
    job = _new_job(req.task)
    asyncio.create_task(_execute(job, req))
    return {"id": job["id"]}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job


@app.get("/api/jobs")
async def list_jobs():
    return sorted(JOBS.values(), key=lambda j: -j["created"])[:50]


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """Forward an input image/video to ComfyUI's input store."""
    client = ComfyClient()
    if not await client.is_up():
        raise HTTPException(502, "ComfyUI is not reachable — uploads need the "
                                 "local engine running.")
    name = await client.upload_media(file.filename, await file.read())
    return {"name": name}


@app.get("/api/status")
async def status():
    client = ComfyClient()
    up = await client.is_up()
    info = {"comfyui": up, "comfyui_url": client.base_url, "gpu": None}
    if up:
        try:
            stats = await client.system_stats()
            dev = (stats.get("devices") or [{}])[0]
            info["gpu"] = {
                "name": dev.get("name"),
                "vram_total_gb": round((dev.get("vram_total") or 0) / 2**30, 1),
                "vram_free_gb": round((dev.get("vram_free") or 0) / 2**30, 1),
            }
        except Exception:
            pass
    cfg = config.load()
    info["providers"] = {
        "fal": bool(cfg["providers"].get("fal", {}).get("api_key")),
        "replicate": bool(cfg["providers"].get("replicate", {}).get("api_token")),
    }
    return info


@app.get("/api/models")
async def models():
    client = ComfyClient()
    if not await client.is_up():
        return {"checkpoints": [], "diffusion_models": [], "loras": [], "vaes": []}
    return await client.list_models()


@app.get("/api/presets")
async def presets():
    return PRESETS


@app.get("/api/loras/recommended")
async def loras_recommended():
    return lora_manager.RECOMMENDED


@app.get("/api/loras/search")
async def loras_search(query: str = "", base_model: str = "",
                       sort: str = "Newest"):
    try:
        return await lora_manager.search_civitai(query, base_model, sort)
    except Exception as e:
        raise HTTPException(502, f"CivitAI search failed: {e}")


class LoraDownload(BaseModel):
    url: str
    filename: str


@app.post("/api/loras/download")
async def loras_download(req: LoraDownload):
    try:
        path = await lora_manager.download_lora(req.url, req.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"saved_to": path}


@app.get("/api/settings")
async def get_settings():
    cfg = config.load()
    # Mask secrets; the UI only needs to know whether a key is set.
    return {
        "comfyui_url": cfg["comfyui_url"],
        "comfyui_loras_dir": cfg.get("comfyui_loras_dir", ""),
        "fal_key_set": bool(cfg["providers"].get("fal", {}).get("api_key")),
        "replicate_token_set": bool(
            cfg["providers"].get("replicate", {}).get("api_token")),
    }


class SettingsUpdate(BaseModel):
    comfyui_url: str | None = None
    comfyui_loras_dir: str | None = None
    fal_api_key: str | None = None
    replicate_api_token: str | None = None


@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    cfg = config.load()
    if req.comfyui_url is not None:
        cfg["comfyui_url"] = req.comfyui_url
    if req.comfyui_loras_dir is not None:
        cfg["comfyui_loras_dir"] = req.comfyui_loras_dir
    if req.fal_api_key is not None:
        cfg.setdefault("providers", {}).setdefault("fal", {})["api_key"] = \
            req.fal_api_key
    if req.replicate_api_token is not None:
        cfg.setdefault("providers", {}).setdefault("replicate", {})["api_token"] = \
            req.replicate_api_token
    config.save(cfg)
    return await get_settings()


app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")


@app.exception_handler(404)
async def spa_fallback(request, exc):
    index = ROOT / "frontend" / "index.html"
    if request.url.path.startswith(("/api/", "/outputs/")) or not index.exists():
        raise exc
    return FileResponse(index)


if __name__ == "__main__":
    cfg = config.load()
    uvicorn.run(app, host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 8500)))
