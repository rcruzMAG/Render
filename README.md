# Render Studio — Local AI Image & Video Generator

A local web app for AI image and video generation, built on top of **ComfyUI** —
currently the most capable local generation engine — running the strongest
open-weight models available today:

| Task | Engine / Model | Why it's the current best local option |
|---|---|---|
| Image generation | **FLUX.1-dev** (Black Forest Labs) | Best prompt adherence + photorealism of any open-weight image model |
| Fast image generation | **FLUX.1-schnell** / SDXL + Lightning | 4-step generation, near-realtime on consumer GPUs |
| Image editing / modification | **FLUX.1 Kontext (dev)**, **Qwen-Image-Edit** | Instruction-based editing ("make the sofa green") with identity preservation |
| Video generation (T2V / I2V) | **Wan 2.2** (A14B MoE + TI2V-5B) | Best open video model; 720p, strong motion, runs on 8–24 GB VRAM |
| Character animation from action reference | **Wan 2.2 Animate** (animation mode) | Drives a character image with the motion of a reference video |
| Video character swap | **Wan 2.2 Animate** (replacement mode) / **VACE** | Replaces a person in a video with your character, keeping motion + lighting |
| Architecture / interior | SDXL or FLUX + **ControlNet** (Depth / Canny / MLSD) | Turns 3D model renders, sketches or photos into photoreal visualizations |
| Upscaling / detail | 4x-UltraSharp + img2img refine | Industry-standard latent upscale pipeline |

The app uses **your local GPU through ComfyUI by default**, and can optionally
fall back to **cloud APIs (fal.ai or Replicate)** when you don't have the VRAM
for a given task — switchable per-request in Settings.

---

## Quick start — one double-click

- **Windows:** double-click **`Start-RenderStudio.bat`**. If Python is missing
  it offers to install it for you (winget) after a Y/N prompt.
- **macOS / Linux:** run **`./start.sh`**.

The launcher installs the app's dependencies, starts the server, and opens
your browser at **http://127.0.0.1:8500**. On first run the app lands on the
**Setup** tab, which does everything else *for* you on this machine:

1. **⚡ Set everything up & start generating** — one button that clones
   ComfyUI, installs PyTorch matched to your detected GPU (CUDA / Apple
   Silicon / CPU), downloads the FLUX.1-dev image model, launches the engine,
   and drops you on the Generate tab. Live progress and command logs stream
   into the page.
2. **Model packs** — each remaining function (video, Kontext editing,
   architecture ControlNet, character animate/swap, upscaler) is a one-click
   pack download with its size shown up front. Downloads resume if
   interrupted. An existing ComfyUI install is auto-detected and reused —
   nothing is re-downloaded.

If you open a tab whose models aren't installed yet, a banner offers to
install exactly what's missing (with the download size) — one click, then
generate. The engine runs as a managed child process: the app starts and
stops it for you; no terminal needed after the first double-click.

Everything runs locally; nothing leaves your machine unless you explicitly
enable a cloud provider in Settings. Model packs use ungated single-file
fp8 builds (Comfy-Org repackages) so there's no Hugging Face login. Exact
filenames/URLs live in `backend/setup_manager.py` and `config.json` if you
want different variants (GGUF, 14B Wan, etc.).

---

## Functions

1. **Image Generation** — FLUX.1-dev / FLUX.1-schnell / SDXL, with LoRA stacking.
2. **Video Generation** — Wan 2.2 text-to-video and image-to-video.
3. **Image Modifier** — img2img restyle and FLUX Kontext instruction editing
   ("replace the sky with sunset", "make it watercolor").
4. **Architecture & Interior** — upload a 3D model render (Revit/SketchUp/Blender
   viewport, clay render) or a photo; ControlNet (Depth/Canny/MLSD) preserves the
   geometry while the model re-materializes it photorealistically. Includes
   day/night relight and restyle presets.
5. **Character Animator** — upload a character image + an action reference video;
   Wan 2.2 Animate transfers the motion to your character.
6. **Video Character Swap** — upload a source video + character image; the person
   in the video is replaced while motion, camera and lighting are preserved.
7. **Upscale & Refine** — 4x-UltraSharp + optional diffusion refine pass.
8. **LoRA Hub** — browse the *latest* LoRAs live from the CivitAI API, one-click
   download into ComfyUI, plus a curated recommendation list per task (below).

---

## Recommended LoRAs by task

The same list is shown (and downloadable) in the app's **LoRA Hub** tab, which
also pulls the newest releases live from CivitAI.

| Task | LoRA | Base | What it's best for |
|---|---|---|---|
| Photorealistic people/scenes | **Amateur Photography** | FLUX.1-dev | Kills the "AI gloss", candid phone-photo realism |
| Sharpness fix | **FLUX AntiBlur** | FLUX.1-dev | Deeper depth of field, removes FLUX's default bokeh blur |
| Speed | **FLUX.1 Turbo Alpha** | FLUX.1-dev | 8-step generation at near-full quality |
| Speed (SDXL) | **SDXL Lightning 4/8-step** | SDXL | Realtime-ish iteration while drafting |
| Detail boost | **Detail Tweaker XL (add-detail-xl)** | SDXL | Dial micro-detail up/down with LoRA weight (−2…+2) |
| Interior design | **Interior Design Universal / XSArchi series** | SDXL | Coherent furniture, materials, lighting for interiors |
| Exterior architecture | **Architecture Exterior / ArchModern** | SDXL / FLUX | Clean facades, correct glazing, photoreal exteriors |
| Video speed | **Wan 2.2 Lightning (lightx2v) 4-step** | Wan 2.2 | 4-step video sampling — 5–10× faster, slight motion cost |
| Video motion quality | **Wan motion/camera LoRAs (push-in, orbit…)** | Wan 2.2 | Controlled camera moves for product/arch flythroughs |
| Anime/illustration | **Niji-style / anime aesthetic LoRAs** | SDXL / FLUX | Stylized character art with consistent line work |

---

## Recommended parameters

These defaults are pre-filled per task in the UI (and live in `backend/presets.py`).

### Image generation
| Model | Steps | Guidance / CFG | Sampler / Scheduler | Resolution | Notes |
|---|---|---|---|---|---|
| FLUX.1-dev | 20–30 (28 default) | Guidance **3.5** (2.5–4) | euler + simple/beta | 1024×1024 (≤2 MP) | No negative prompt; CFG fixed at 1 |
| FLUX.1-schnell | **4** | 0 (distilled) | euler + simple | 1024×1024 | Drafting only |
| SDXL | 25–35 | CFG **5–7** | dpmpp_2m + karras | 1024×1024 / 896×1152 | Negative prompt helps |

### Image modification
| Operation | Denoise | Notes |
|---|---|---|
| Subtle touch-up / relight | 0.25–0.40 | Keeps composition + identity |
| Restyle (keep structure) | 0.45–0.60 | The sweet spot for most edits |
| Heavy reimagining | 0.65–0.80 | Structure starts to drift above 0.75 |
| FLUX Kontext edit | n/a (instruction-based) | Guidance 2.5; plain-language edit commands |

### Architecture / interior (ControlNet)
- ControlNet strength **0.6–0.9**, end percent **0.6–0.8** (release the control
  late so materials/lighting can develop).
- **Depth** for 3D model renders & massing studies, **Canny** for line drawings /
  elevations, **MLSD** for clean interior straight-line geometry.
- Pair with denoise 1.0 (txt2img + control) for renders, or img2img denoise
  0.5–0.65 to re-materialize an existing photo.

### Video (Wan 2.2)
| Setting | Recommended | Notes |
|---|---|---|
| Frames | 81 @ 16 fps (~5 s) | Native training length |
| Resolution | 480p (fast) / 720p (quality) | 1280×720 needs ~16 GB+ VRAM |
| Steps | 20–30 — or **4** with Lightning LoRA | |
| CFG | 3.5–5.0 — or **1.0** with Lightning LoRA | |
| Sampler | uni_pc or euler | |

### Upscale
- 4x-UltraSharp model upscale, then optional refine pass at denoise **0.2–0.35**.

---

## Cloud API fallback (optional)

In **Settings**, add a key for **fal.ai** or **Replicate** and flip any tab's
*Compute* selector from `Local (ComfyUI)` to the provider. Useful for 720p video
or FLUX at full precision when local VRAM is the bottleneck. Keys are stored
locally in `config.json` only.

## Project layout

```
backend/
  main.py            FastAPI app + job queue + all API endpoints
  comfy_client.py    ComfyUI HTTP/WS client (queue, poll, fetch outputs, uploads)
  workflows.py       ComfyUI graph builders for every function
  presets.py         Recommended parameter sets served to the UI
  lora_manager.py    Curated LoRA recommendations + CivitAI search/download
  providers.py       fal.ai / Replicate cloud connectors
  config.py          config.json loader
frontend/            Static SPA (no build step)
config.json          ComfyUI URL, model filenames, API keys
```
