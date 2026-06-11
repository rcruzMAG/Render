"""One-click setup engine: detects what's missing on the user's machine and
installs it — ComfyUI itself, PyTorch for the detected GPU, model packs, and
custom nodes — by running the real commands locally and streaming progress
to the browser.

Everything lands under config 'comfyui_dir' (default: ~/RenderStudio/ComfyUI).
"""

import asyncio
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

from . import config

COMFYUI_REPO = "https://github.com/comfyanonymous/ComfyUI"
CONTROLNET_AUX_REPO = "https://github.com/Fannovel16/comfyui_controlnet_aux"

DEFAULT_COMFY_DIR = Path.home() / "RenderStudio" / "ComfyUI"

# Common pre-existing installs to adopt instead of re-downloading 10+ GB.
KNOWN_COMFY_DIRS = [
    DEFAULT_COMFY_DIR,
    Path.home() / "ComfyUI",
    Path.home() / "Documents" / "ComfyUI",
    Path("C:/ComfyUI"),
    Path.home() / "comfy" / "ComfyUI",
]

HF = "https://huggingface.co"

# Model packs: everything needed for a task, with direct ungated download
# URLs (Comfy-Org repackaged fp8 builds where possible — single files, no
# HuggingFace login). Sizes are approximate, used for the consent prompt.
MODEL_PACKS = {
    "flux_image": {
        "label": "Image Generation — FLUX.1-dev fp8",
        "tasks": ["image"],
        "size_gb": 17.2,
        "files": [
            {"url": f"{HF}/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors",
             "dir": "checkpoints", "name": "flux1-dev-fp8.safetensors"},
        ],
    },
    "flux_schnell": {
        "label": "Fast drafts — FLUX.1-schnell fp8 (4-step)",
        "tasks": ["image"],
        "size_gb": 17.2,
        "files": [
            {"url": f"{HF}/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors",
             "dir": "checkpoints", "name": "flux1-schnell-fp8.safetensors"},
        ],
    },
    "sdxl": {
        "label": "SDXL base — biggest LoRA ecosystem, used by Architecture",
        "tasks": ["image", "architecture", "modify", "upscale"],
        "size_gb": 6.9,
        "files": [
            {"url": f"{HF}/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors",
             "dir": "checkpoints", "name": "sd_xl_base_1.0.safetensors"},
        ],
    },
    "kontext": {
        "label": "Image Modifier — FLUX.1 Kontext (instruction editing)",
        "tasks": ["modify"],
        "size_gb": 17.5,
        "files": [
            {"url": f"{HF}/Comfy-Org/flux1-kontext-dev_ComfyUI/resolve/main/split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors",
             "dir": "diffusion_models", "name": "flux1-dev-kontext_fp8_scaled.safetensors"},
            {"url": f"{HF}/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors",
             "dir": "text_encoders", "name": "clip_l.safetensors"},
            {"url": f"{HF}/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
             "dir": "text_encoders", "name": "t5xxl_fp8_e4m3fn.safetensors"},
            {"url": f"{HF}/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors",
             "dir": "vae", "name": "ae.safetensors"},
        ],
    },
    "wan_video": {
        "label": "Video Generation — Wan 2.2 TI2V-5B (T2V + I2V, 720p, 8GB+ VRAM)",
        "tasks": ["video"],
        "size_gb": 12.5,
        "files": [
            {"url": f"{HF}/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
             "dir": "diffusion_models", "name": "wan2.2_ti2v_5B_fp16.safetensors"},
            {"url": f"{HF}/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
             "dir": "text_encoders", "name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors"},
            {"url": f"{HF}/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors",
             "dir": "vae", "name": "wan2.2_vae.safetensors"},
        ],
    },
    "wan_animate": {
        "label": "Character Animator & Video Swap — Wan 2.2 Animate 14B (16GB+ VRAM)",
        "tasks": ["animate", "swap"],
        "size_gb": 18.0,
        "files": [
            {"url": f"{HF}/Comfy-Org/Wan_2.2_Animate_14B_repackaged/resolve/main/split_files/diffusion_models/wan2.2_animate_14B_fp8_scaled.safetensors",
             "dir": "diffusion_models", "name": "wan2.2_animate_14B_fp8_scaled.safetensors"},
            {"url": f"{HF}/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
             "dir": "text_encoders", "name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors"},
            {"url": f"{HF}/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
             "dir": "vae", "name": "wan_2.1_vae.safetensors"},
        ],
    },
    "controlnet": {
        "label": "Architecture tools — ControlNet Union SDXL + preprocessors",
        "tasks": ["architecture"],
        "size_gb": 2.5,
        "custom_node": CONTROLNET_AUX_REPO,
        "files": [
            {"url": f"{HF}/xinsir/controlnet-union-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors",
             "dir": "controlnet", "name": "controlnet-union-sdxl-1.0.safetensors"},
        ],
    },
    "upscaler": {
        "label": "Upscale & Refine — 4x-UltraSharp",
        "tasks": ["upscale"],
        "size_gb": 0.07,
        "files": [
            {"url": f"{HF}/Kim2091/UltraSharp/resolve/main/4x-UltraSharp.pth",
             "dir": "upscale_models", "name": "4x-UltraSharp.pth"},
        ],
    },
}

# ---------------------------------------------------------------- job infra

JOBS: dict[str, dict] = {}
_busy = asyncio.Lock()
ENGINE_PROC: subprocess.Popen | None = None


def _new_job(kind: str) -> dict:
    job = {"id": uuid.uuid4().hex[:10], "kind": kind, "status": "running",
           "progress": 0.0, "detail": "", "log": [], "created": time.time()}
    JOBS[job["id"]] = job
    return job


def _log(job: dict, line: str):
    job["log"].append(line.rstrip()[:500])
    if len(job["log"]) > 400:
        del job["log"][:100]


async def _run_cmd(job: dict, args: list[str], cwd: Path | None = None) -> int:
    """Run a command, streaming its output into the job log."""
    _log(job, f"$ {' '.join(args)}")
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    assert proc.stdout
    async for raw in proc.stdout:
        _log(job, raw.decode(errors="replace"))
    return await proc.wait()


# ---------------------------------------------------------------- detection

def comfy_dir() -> Path | None:
    cfg = config.load()
    configured = cfg.get("comfyui_dir") or ""
    if configured and (Path(configured) / "main.py").exists():
        return Path(configured)
    for d in KNOWN_COMFY_DIRS:
        if (d / "main.py").exists():
            return d
    return None


def detect_gpu() -> dict:
    if platform.system() == "Darwin":
        return {"kind": "mps", "name": "Apple Silicon (MPS)", "vram_gb": None}
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.check_output(
                [smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                text=True, timeout=5).strip().splitlines()[0]
            name, mem = [p.strip() for p in out.split(",")]
            return {"kind": "cuda", "name": name,
                    "vram_gb": round(float(mem.split()[0]) / 1024, 1)}
        except Exception:
            pass
        return {"kind": "cuda", "name": "NVIDIA GPU", "vram_gb": None}
    return {"kind": "cpu", "name": "No GPU detected (CPU mode — slow)",
            "vram_gb": None}


def pack_status(cdir: Path | None) -> dict:
    out = {}
    for pack_id, pack in MODEL_PACKS.items():
        installed = False
        if cdir:
            installed = all(
                (cdir / "models" / f["dir"] / f["name"]).exists()
                for f in pack["files"])
            if installed and pack.get("custom_node"):
                node_name = pack["custom_node"].rstrip("/").split("/")[-1]
                installed = (cdir / "custom_nodes" / node_name).exists()
        out[pack_id] = {"label": pack["label"], "tasks": pack["tasks"],
                        "size_gb": pack["size_gb"], "installed": installed}
    return out


async def detect() -> dict:
    from .comfy_client import ComfyClient
    cdir = comfy_dir()
    client = ComfyClient()
    running = await client.is_up()
    disk = shutil.disk_usage(str(cdir or Path.home()))
    return {
        "platform": platform.system(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "git": shutil.which("git") is not None,
        "gpu": detect_gpu(),
        "comfyui_installed": cdir is not None,
        "comfyui_dir": str(cdir) if cdir else str(DEFAULT_COMFY_DIR),
        "engine_running": running,
        "engine_managed": ENGINE_PROC is not None and ENGINE_PROC.poll() is None,
        "disk_free_gb": round(disk.free / 2**30, 1),
        "packs": pack_status(cdir),
        "active_jobs": [j for j in JOBS.values() if j["status"] == "running"],
    }


# ------------------------------------------------------------------ actions

def _torch_install_args() -> list[str]:
    gpu = detect_gpu()
    base = [sys.executable, "-m", "pip", "install", "torch", "torchvision",
            "torchaudio"]
    if gpu["kind"] == "cuda":
        base += ["--index-url", "https://download.pytorch.org/whl/cu126"]
    elif gpu["kind"] == "cpu" and platform.system() != "Darwin":
        base += ["--index-url", "https://download.pytorch.org/whl/cpu"]
    return base


async def install_comfyui(job: dict):
    """git clone ComfyUI + install PyTorch for the detected GPU + deps."""
    if not shutil.which("git"):
        raise RuntimeError(
            "git is not installed. Install it from https://git-scm.com "
            "(Windows: 'winget install Git.Git'), then retry.")
    dest = Path(config.load().get("comfyui_dir") or DEFAULT_COMFY_DIR)
    dest.parent.mkdir(parents=True, exist_ok=True)

    job["detail"] = "Cloning ComfyUI…"
    job["progress"] = 0.05
    if not (dest / "main.py").exists():
        rc = await _run_cmd(job, ["git", "clone", "--depth", "1",
                                  COMFYUI_REPO, str(dest)])
        if rc != 0:
            raise RuntimeError("git clone failed — see log")
    else:
        _log(job, f"ComfyUI already present at {dest}, skipping clone")

    job["detail"] = "Installing PyTorch for your GPU (this is the big one)…"
    job["progress"] = 0.15
    rc = await _run_cmd(job, _torch_install_args())
    if rc != 0:
        raise RuntimeError("PyTorch install failed — see log")

    job["detail"] = "Installing ComfyUI requirements…"
    job["progress"] = 0.75
    rc = await _run_cmd(job, [sys.executable, "-m", "pip", "install", "-r",
                              str(dest / "requirements.txt")])
    if rc != 0:
        raise RuntimeError("pip install -r requirements.txt failed — see log")

    cfg = config.load()
    cfg["comfyui_dir"] = str(dest)
    cfg["comfyui_loras_dir"] = str(dest / "models" / "loras")
    config.save(cfg)
    job["progress"] = 1.0
    job["detail"] = "ComfyUI installed."


async def _download_file(job: dict, url: str, dest: Path,
                         done_bytes: int, total_bytes: int):
    """Stream a file with progress + resume support."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    start = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    _log(job, f"downloading {dest.name}" + (f" (resuming at {start>>20} MB)" if start else ""))
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as c:
        async with c.stream("GET", url, headers=headers) as r:
            if r.status_code == 416:          # already fully downloaded
                part.rename(dest)
                return
            if r.status_code not in (200, 206):
                raise RuntimeError(f"{dest.name}: HTTP {r.status_code} from {url}")
            if r.status_code == 200:
                start = 0
            mode = "ab" if start else "wb"
            written = start
            with open(part, mode) as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    f.write(chunk)
                    written += len(chunk)
                    if total_bytes:
                        job["progress"] = min(
                            0.99, (done_bytes + written) / total_bytes)
                    job["detail"] = (f"{dest.name} — "
                                     f"{(done_bytes + written) >> 20} MB done")
    part.rename(dest)
    _log(job, f"✓ {dest.name}")


async def download_pack(job: dict, pack_id: str):
    pack = MODEL_PACKS.get(pack_id)
    if not pack:
        raise RuntimeError(f"unknown pack '{pack_id}'")
    cdir = comfy_dir()
    if not cdir:
        raise RuntimeError("Install ComfyUI first (step 1).")

    total = int(pack["size_gb"] * 2**30)
    done = 0
    for f in pack["files"]:
        dest = cdir / "models" / f["dir"] / f["name"]
        if dest.exists():
            _log(job, f"✓ {f['name']} already installed")
        else:
            await _download_file(job, f["url"], dest, done, total)
        done += dest.stat().st_size if dest.exists() else 0

    if pack.get("custom_node"):
        repo = pack["custom_node"]
        node_dir = cdir / "custom_nodes" / repo.rstrip("/").split("/")[-1]
        if not node_dir.exists():
            job["detail"] = "Installing preprocessor nodes…"
            rc = await _run_cmd(job, ["git", "clone", "--depth", "1", repo,
                                      str(node_dir)])
            if rc != 0:
                raise RuntimeError("custom node clone failed")
            req = node_dir / "requirements.txt"
            if req.exists():
                await _run_cmd(job, [sys.executable, "-m", "pip", "install",
                                     "-r", str(req)])
            _log(job, "Preprocessor nodes installed — restart the engine to load them.")
    job["progress"] = 1.0
    job["detail"] = f"{pack['label']} ready."


async def start_engine(job: dict):
    """Launch ComfyUI as a managed child process and wait until it answers."""
    global ENGINE_PROC
    from .comfy_client import ComfyClient
    client = ComfyClient()
    if await client.is_up():
        job["progress"] = 1.0
        job["detail"] = "Engine already running."
        return
    cdir = comfy_dir()
    if not cdir:
        raise RuntimeError("Install ComfyUI first (step 1).")
    port = client.base_url.rsplit(":", 1)[-1]
    args = [sys.executable, str(cdir / "main.py"), "--port", port]
    if detect_gpu()["kind"] == "cpu":
        args.append("--cpu")
    _log(job, f"$ {' '.join(args)}")
    logfile = open(cdir / "render_studio_engine.log", "ab")
    ENGINE_PROC = subprocess.Popen(args, cwd=str(cdir), stdout=logfile,
                                   stderr=subprocess.STDOUT)
    job["detail"] = "Starting engine (first launch can take a minute)…"
    for i in range(120):
        await asyncio.sleep(2)
        if ENGINE_PROC.poll() is not None:
            tail = (cdir / "render_studio_engine.log").read_bytes()[-3000:]
            raise RuntimeError("Engine exited during startup:\n"
                               + tail.decode(errors="replace"))
        if await client.is_up():
            job["progress"] = 1.0
            job["detail"] = "Engine running."
            return
        job["progress"] = min(0.95, i / 60)
    raise RuntimeError("Engine did not come up within 4 minutes — see "
                       f"{cdir / 'render_studio_engine.log'}")


def stop_engine() -> bool:
    global ENGINE_PROC
    if ENGINE_PROC and ENGINE_PROC.poll() is None:
        ENGINE_PROC.terminate()
        ENGINE_PROC = None
        return True
    return False


ACTIONS = {
    "install_comfyui": install_comfyui,
    "start_engine": start_engine,
}


async def run_action(kind: str, **kwargs) -> dict:
    """Entry point used by the API; one setup job at a time."""
    if _busy.locked():
        raise RuntimeError("Another setup task is already running.")
    job = _new_job(kind)

    async def go():
        async with _busy:
            try:
                if kind == "download_pack":
                    await download_pack(job, kwargs["pack_id"])
                else:
                    await ACTIONS[kind](job)
                job["status"] = "done"
            except Exception as e:
                job["status"] = "error"
                job["detail"] = str(e)
                _log(job, f"ERROR: {e}")

    asyncio.create_task(go())
    return job
