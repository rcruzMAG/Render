/* Render Studio frontend — no build step, talks to the FastAPI backend. */

const $ = (sel) => document.querySelector(sel);
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

let PRESETS = {};
let LORAS = [];          // lora filenames known to ComfyUI
let currentTab = "image";

/* ---------------------------------------------------------- tiny dom utils */

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c);
  return node;
}

function field(label, input) {
  return el("div", { class: "field" }, el("label", {}, label), input);
}

function textarea(id, placeholder, value = "") {
  const t = el("textarea", { id, placeholder });
  t.value = value;
  return t;
}

function numberInput(id, value, step = 1) {
  return el("input", { id, type: "number", value, step });
}

function select(id, options, selected) {
  const s = el("select", { id });
  for (const [val, label] of options) {
    const o = el("option", { value: val }, label);
    if (val === selected) o.selected = true;
    s.append(o);
  }
  return s;
}

function range(id, min, max, step, value) {
  const out = el("output", {}, String(value));
  const r = el("input", { id, type: "range", min, max, step, value,
    oninput: () => (out.textContent = r.value) });
  return el("div", { class: "range-wrap" }, r, out);
}

function computeSelector(tasksWithCloud = true) {
  const opts = [["local", "Local GPU (ComfyUI)"]];
  if (tasksWithCloud) opts.push(["fal", "Cloud — fal.ai"], ["replicate", "Cloud — Replicate"]);
  return field("Compute", select("compute", opts, "local"));
}

/* Upload widget: sends the file to ComfyUI via the backend, stores the
   server-side filename in a hidden input. */
function dropzone(id, label, accept) {
  const hidden = el("input", { id, type: "hidden" });
  const zone = el("div", { class: "dropzone" }, label, hidden);
  const file = el("input", { type: "file", accept, style: "display:none" });
  zone.append(file);
  zone.addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    if (!file.files[0]) return;
    zone.classList.remove("has-file");
    zone.firstChild.textContent = "uploading…";
    try {
      const fd = new FormData();
      fd.append("file", file.files[0]);
      const res = await api("/api/upload", { method: "POST", body: fd });
      hidden.value = res.name;
      zone.classList.add("has-file");
      zone.firstChild.textContent = `✓ ${file.files[0].name}`;
      const url = URL.createObjectURL(file.files[0]);
      zone.querySelectorAll("img,video").forEach((n) => n.remove());
      zone.append(file.files[0].type.startsWith("video")
        ? el("video", { src: url, muted: "", loop: "", autoplay: "" })
        : el("img", { src: url }));
    } catch (e) {
      zone.firstChild.textContent = `upload failed: ${e.message}`;
    }
  });
  return zone;
}

/* LoRA stack picker — populated from /api/models loras. */
function loraStack() {
  const wrap = el("div", { class: "lora-stack", id: "lora-stack" });
  const addRow = () => {
    const row = el("div", { class: "lora-row" },
      select("", [["", "— choose LoRA —"], ...LORAS.map((l) => [l, l])]),
      el("input", { type: "number", value: "1.0", step: "0.05", title: "strength" }),
      el("button", { onclick: (e) => { e.preventDefault(); row.remove(); } }, "✕"));
    wrap.insertBefore(row, addBtn);
  };
  const addBtn = el("button", { class: "secondary",
    onclick: (e) => { e.preventDefault(); addRow(); } }, "+ Add LoRA");
  wrap.append(addBtn);
  return wrap;
}

function collectLoras() {
  return [...document.querySelectorAll("#lora-stack .lora-row")]
    .map((row) => ({
      name: row.querySelector("select").value,
      strength: parseFloat(row.querySelector("input").value || "1"),
    }))
    .filter((l) => l.name);
}

function presetPicker(group, onApply) {
  const entries = Object.entries(PRESETS[group] || {});
  const s = select("preset", entries.map(([k, v]) => [k, v.label]), entries[0]?.[0]);
  s.addEventListener("change", () => onApply(PRESETS[group][s.value]));
  queueMicrotask(() => entries.length && onApply(PRESETS[group][entries[0][0]]));
  return field("Recommended preset", s);
}

function hint(id) {
  return el("div", { class: "hint", id });
}

const val = (id) => $(`#${id}`)?.value;
const num = (id) => parseFloat(val(id));

function setIf(id, v) {
  const n = $(`#${id}`);
  if (n && v !== undefined) {
    n.value = v;
    n.dispatchEvent(new Event("input"));
  }
}

function applyPreset(p, keys) {
  for (const k of keys) setIf(k, p[k]);
  const h = $("#preset-hint");
  if (h) h.textContent = p.notes || "";
}

/* ------------------------------------------------------------------- tabs */

const TABS = {
  image: {
    label: "🖼 Image Generation",
    render(panel) {
      panel.append(
        el("h2", {}, "Image Generation"),
        el("p", { class: "desc" },
          "Text-to-image on FLUX.1-dev (best quality), FLUX.1-schnell (4-step drafts) or SDXL (largest LoRA ecosystem)."),
        field("Model", select("model", [
          ["flux-dev", "FLUX.1-dev — best quality"],
          ["flux-schnell", "FLUX.1-schnell — fastest"],
          ["sdxl", "SDXL — most LoRAs/ControlNets"],
        ], "flux-dev")),
        presetPicker("image", (p) =>
          applyPreset(p, ["steps", "guidance", "cfg", "width", "height", "negative_prompt"])),
        hint("preset-hint"),
        field("Prompt", textarea("prompt", "A sunlit Scandinavian living room, oak floor, linen sofa, 35mm photo…")),
        field("Negative prompt (SDXL only)", textarea("negative_prompt", "")),
        el("div", { class: "row3" },
          field("Width", numberInput("width", 1024, 64)),
          field("Height", numberInput("height", 1024, 64)),
          field("Steps", numberInput("steps", 28))),
        el("div", { class: "row" },
          field("Guidance (FLUX) / CFG (SDXL)", numberInput("guidance", 3.5, 0.1)),
          field("Seed (−1 = random)", numberInput("seed", -1))),
        field("LoRAs", loraStack()),
        computeSelector(),
        el("button", { class: "primary", onclick: () => submit("image", {
          model: val("model"), prompt: val("prompt"),
          negative_prompt: val("negative_prompt"),
          width: num("width"), height: num("height"), steps: num("steps"),
          guidance: num("guidance"), cfg: num("guidance"), seed: num("seed"),
          loras: collectLoras(),
        }) }, "Generate"));
      $("#model").addEventListener("change", () => {
        const map = { "flux-dev": "flux-dev", "flux-schnell": "flux-schnell", sdxl: "sdxl" };
        const p = PRESETS.image[map[val("model")]];
        if (p) { applyPreset(p, ["steps", "guidance", "cfg", "width", "height"]);
                 setIf("guidance", p.guidance ?? p.cfg); }
      });
    },
  },

  video: {
    label: "🎬 Video Generation",
    render(panel) {
      panel.append(
        el("h2", {}, "Video Generation — Wan 2.2"),
        el("p", { class: "desc" },
          "Text-to-video, or animate a still image (image-to-video). 81 frames @ 16 fps ≈ 5 s. Grab the Wan 2.2 Lightning LoRA from the LoRA Hub for 4-step speed."),
        field("Mode", select("vmode", [
          ["video_t2v", "Text → Video"],
          ["video_i2v", "Image → Video"],
        ], "video_t2v")),
        presetPicker("video", (p) =>
          applyPreset(p, ["width", "height", "frames", "fps", "steps", "cfg"])),
        hint("preset-hint"),
        field("Start image (image→video only)", dropzone("input_image", "Click to upload a start frame", "image/*")),
        field("Prompt", textarea("prompt", "Slow cinematic push-in across a modern kitchen at golden hour…")),
        el("div", { class: "row3" },
          field("Width", numberInput("width", 832, 16)),
          field("Height", numberInput("height", 480, 16)),
          field("Frames", numberInput("frames", 81))),
        el("div", { class: "row3" },
          field("FPS", numberInput("fps", 16)),
          field("Steps", numberInput("steps", 20)),
          field("CFG", numberInput("cfg", 4.0, 0.1))),
        field("Seed (−1 = random)", numberInput("seed", -1)),
        computeSelector(),
        el("button", { class: "primary", onclick: () => submit(val("vmode"), {
          prompt: val("prompt"), input_image: val("input_image"),
          width: num("width"), height: num("height"), frames: num("frames"),
          fps: num("fps"), steps: num("steps"), cfg: num("cfg"), seed: num("seed"),
        }) }, "Generate Video"));
    },
  },

  modify: {
    label: "✏️ Image Modifier",
    render(panel) {
      panel.append(
        el("h2", {}, "Image Modifier"),
        el("p", { class: "desc" },
          "Two engines: FLUX Kontext takes plain-language edit commands and preserves identity; img2img restyles with a denoise dial."),
        field("Engine", select("engine", [
          ["kontext", "FLUX Kontext — instruction edit (recommended)"],
          ["img2img", "img2img — restyle with denoise control"],
        ], "kontext")),
        presetPicker("modify", (p) => applyPreset(p, ["denoise", "steps", "guidance"])),
        hint("preset-hint"),
        field("Image", dropzone("input_image", "Click to upload the image to modify", "image/*")),
        field("Edit instruction / prompt", textarea("prompt",
          "Kontext: 'replace the sofa with a green velvet one' · img2img: describe the full target look")),
        el("div", { class: "row3" },
          field("Denoise (img2img)", range("denoise", 0.1, 0.9, 0.01, 0.55)),
          field("Steps", numberInput("steps", 20)),
          field("Guidance (Kontext)", numberInput("guidance", 2.5, 0.1))),
        field("LoRAs (img2img)", loraStack()),
        computeSelector(),
        el("button", { class: "primary", onclick: () => submit(val("engine"), {
          prompt: val("prompt"), input_image: val("input_image"),
          denoise: num("denoise"), steps: num("steps"), guidance: num("guidance"),
          loras: collectLoras(),
        }) }, "Apply Modification"));
    },
  },

  architecture: {
    label: "🏛 Architecture & Interior",
    render(panel) {
      panel.append(
        el("h2", {}, "Architecture & Interior Visualizer"),
        el("p", { class: "desc" },
          "Upload a 3D model render (Revit/SketchUp/Blender viewport, clay render), sketch or photo. ControlNet locks the geometry; your prompt supplies materials, lighting and style. Grab interior/exterior LoRAs from the Hub for stronger results."),
        presetPicker("architecture", (p) =>
          applyPreset(p, ["control_strength", "control_end", "denoise", "steps", "cfg"])
          || setIf("control_type", p.control_type)),
        hint("preset-hint"),
        field("Source image", dropzone("input_image", "Click to upload model render / sketch / photo", "image/*")),
        field("Geometry lock", select("control_type", [
          ["depth", "Depth — 3D renders & massing (recommended)"],
          ["canny", "Canny — line drawings & elevations"],
          ["mlsd", "MLSD — interiors, straight-line geometry"],
        ], "depth")),
        field("Materials & lighting prompt", textarea("prompt",
          "photorealistic exterior, white concrete and warm timber cladding, floor-to-ceiling glazing, dusk lighting, architectural photography")),
        el("div", { class: "row" },
          field("Control strength (0.6–0.9)", range("control_strength", 0.2, 1.0, 0.05, 0.8)),
          field("Control end % (release late)", range("control_end", 0.3, 1.0, 0.05, 0.7))),
        el("div", { class: "row3" },
          field("Denoise (1.0 = full render)", range("denoise", 0.3, 1.0, 0.05, 1.0)),
          field("Steps", numberInput("steps", 30)),
          field("CFG", numberInput("cfg", 6.0, 0.1))),
        field("LoRAs (interior / exterior packs)", loraStack()),
        computeSelector(false),
        el("button", { class: "primary", onclick: () => submit("architecture", {
          prompt: val("prompt"), input_image: val("input_image"),
          control_type: val("control_type"),
          control_strength: num("control_strength"), control_end: num("control_end"),
          denoise: num("denoise"), steps: num("steps"), cfg: num("cfg"),
          loras: collectLoras(),
        }) }, "Render"));
      const pre = PRESETS.architecture;
      $("#preset").addEventListener("change", () =>
        setIf("control_type", pre[val("preset")]?.control_type));
    },
  },

  animate: {
    label: "🕺 Character Animator",
    render(panel) {
      panel.append(
        el("h2", {}, "Character Animator"),
        el("p", { class: "desc" },
          "Wan 2.2 Animate: your character image performs the motion from an action reference video. Best with a clean, front-facing character and a 3–5 s clip of one person."),
        presetPicker("animate", (p) =>
          applyPreset(p, ["width", "height", "frames", "fps", "steps", "cfg"])),
        hint("preset-hint"),
        field("Character image", dropzone("character_image", "Click to upload the character", "image/*")),
        field("Action reference video", dropzone("reference_video", "Click to upload the motion reference", "video/*")),
        field("Optional prompt", textarea("prompt", "the character dancing in a studio, soft light")),
        el("div", { class: "row3" },
          field("Width", numberInput("width", 832, 16)),
          field("Height", numberInput("height", 480, 16)),
          field("Frames", numberInput("frames", 77))),
        el("div", { class: "row" },
          field("Steps", numberInput("steps", 20)),
          field("CFG", numberInput("cfg", 4.0, 0.1))),
        computeSelector(false),
        el("button", { class: "primary", onclick: () => submit("animate", {
          mode: "animate", prompt: val("prompt"),
          character_image: val("character_image"),
          reference_video: val("reference_video"),
          width: num("width"), height: num("height"), frames: num("frames"),
          steps: num("steps"), cfg: num("cfg"),
        }) }, "Animate Character"));
    },
  },

  swap: {
    label: "🔄 Video Character Swap",
    render(panel) {
      panel.append(
        el("h2", {}, "Video Character Swap"),
        el("p", { class: "desc" },
          "Wan 2.2 Animate in replacement mode: the person in your source video is swapped with your character — motion, camera and scene lighting are preserved."),
        field("Character image", dropzone("character_image", "Click to upload the replacement character", "image/*")),
        field("Source video", dropzone("reference_video", "Click to upload the video to modify", "video/*")),
        field("Optional prompt", textarea("prompt", "")),
        el("div", { class: "row3" },
          field("Width", numberInput("width", 832, 16)),
          field("Height", numberInput("height", 480, 16)),
          field("Frames", numberInput("frames", 77))),
        el("div", { class: "row" },
          field("Steps", numberInput("steps", 20)),
          field("CFG", numberInput("cfg", 4.0, 0.1))),
        computeSelector(false),
        el("button", { class: "primary", onclick: () => submit("animate", {
          mode: "replace", prompt: val("prompt"),
          character_image: val("character_image"),
          reference_video: val("reference_video"),
          width: num("width"), height: num("height"), frames: num("frames"),
          steps: num("steps"), cfg: num("cfg"),
        }) }, "Swap Character"));
    },
  },

  upscale: {
    label: "🔍 Upscale & Refine",
    render(panel) {
      panel.append(
        el("h2", {}, "Upscale & Refine"),
        el("p", { class: "desc" },
          "4× upscale with 4x-UltraSharp, plus an optional diffusion refine pass that adds real detail (denoise 0.2–0.35; 0 to skip)."),
        field("Image", dropzone("input_image", "Click to upload the image to upscale", "image/*")),
        field("Refine denoise", range("refine_denoise", 0, 0.5, 0.05, 0.3)),
        field("Refine prompt", textarea("prompt", "high quality, sharp, detailed")),
        computeSelector(false),
        el("button", { class: "primary", onclick: () => submit("upscale", {
          input_image: val("input_image"), prompt: val("prompt"),
          refine_denoise: num("refine_denoise"),
        }) }, "Upscale"));
    },
  },

  loras: {
    label: "🧩 LoRA Hub",
    async render(panel) {
      panel.append(
        el("h2", {}, "LoRA Hub"),
        el("p", { class: "desc" },
          "Curated recommendations per task, plus live search of the latest LoRAs on CivitAI. Downloads land in your ComfyUI loras folder and appear in every LoRA picker."),
        el("div", { class: "search-bar" },
          el("input", { id: "lq", placeholder: "Search CivitAI… (empty = latest releases)" }),
          select("lbase", [["", "Any base"], ["Flux.1 D", "FLUX.1-dev"],
            ["SDXL 1.0", "SDXL"], ["Wan Video 2.2", "Wan 2.2"]], ""),
          select("lsort", [["Newest", "Newest"], ["Most Downloaded", "Most downloaded"],
            ["Highest Rated", "Highest rated"]], "Newest"),
          el("button", { class: "secondary", onclick: searchLoras }, "Search")),
        el("h2", { style: "margin-top:18px" }, "Recommended by task"),
        el("div", { class: "lora-grid", id: "lora-reco" }),
        el("h2", { style: "margin-top:18px" }, "CivitAI results"),
        el("div", { class: "lora-grid", id: "lora-results" },
          el("p", { class: "desc" }, "Search above to pull the latest LoRAs.")));
      const reco = await api("/api/loras/recommended");
      const grid = $("#lora-reco");
      for (const r of reco) {
        grid.append(el("div", { class: "lora-card" },
          el("span", { class: "task-tag" }, r.task),
          el("h4", {}, r.name),
          el("span", { class: "base" }, r.base),
          el("p", {}, r.why),
          el("div", { class: "actions" },
            el("button", { class: "secondary", onclick: () => {
              $("#lq").value = r.search; searchLoras();
            } }, "Find latest on CivitAI"))));
      }
    },
  },

  params: {
    label: "📐 Parameter Guide",
    render(panel) {
      panel.append(el("h2", {}, "Recommended Parameters"),
        el("p", { class: "desc" },
          "These are the defaults the presets apply. Full rationale lives in the README."));
      const table = (title, rows, headers) => {
        panel.append(el("h2", { style: "margin-top:16px;font-size:14px" }, title));
        const t = el("table", { class: "params" });
        t.append(el("tr", {}, ...headers.map((h) => el("th", {}, h))));
        rows.forEach((r) => t.append(el("tr", {}, ...r.map((c) => el("td", {}, c)))));
        panel.append(t);
      };
      table("Image generation", [
        ["FLUX.1-dev", "28 (20–30)", "guidance 3.5", "euler/simple", "1024², ≤2MP"],
        ["FLUX.1-schnell", "4", "0 (distilled)", "euler/simple", "1024²"],
        ["SDXL", "30 (25–35)", "CFG 5–7", "dpmpp_2m/karras", "1024² · 896×1152"],
      ], ["Model", "Steps", "Guidance/CFG", "Sampler", "Resolution"]);
      table("Image modification (denoise)", [
        ["Subtle touch-up / relight", "0.25–0.40", "keeps composition + identity"],
        ["Restyle, keep structure", "0.45–0.60", "the sweet spot"],
        ["Heavy reimagining", "0.65–0.80", "structure drifts above 0.75"],
        ["FLUX Kontext", "n/a", "instruction-based, guidance 2.5"],
      ], ["Operation", "Denoise", "Notes"]);
      table("Architecture (ControlNet)", [
        ["3D model render", "Depth", "strength 0.8, end 0.7, denoise 1.0"],
        ["Sketch / elevation", "Canny", "strength 0.85, end 0.8"],
        ["Interior photo re-skin", "MLSD", "strength 0.7, denoise 0.5–0.65"],
      ], ["Source", "Control", "Settings"]);
      table("Video (Wan 2.2)", [
        ["Frames / FPS", "81 @ 16 fps", "≈ 5 s, native training length"],
        ["Resolution", "832×480 / 1280×720", "720p needs 16 GB+ VRAM"],
        ["Steps / CFG", "20–30 / 3.5–5", "or 4 / 1.0 with Lightning LoRA"],
      ], ["Setting", "Value", "Notes"]);
    },
  },

  settings: {
    label: "⚙️ Settings",
    async render(panel) {
      const s = await api("/api/settings");
      panel.append(
        el("h2", {}, "Settings"),
        el("p", { class: "desc" },
          "Local engine connection and optional cloud API keys. Keys are stored only in config.json on this machine."),
        field("ComfyUI URL", el("input", { id: "s-url", type: "text", value: s.comfyui_url })),
        field("ComfyUI loras directory (enables LoRA downloads)",
          el("input", { id: "s-loras", type: "text", value: s.comfyui_loras_dir,
            placeholder: "/path/to/ComfyUI/models/loras" })),
        field(`fal.ai API key ${s.fal_key_set ? "(set ✓)" : ""}`,
          el("input", { id: "s-fal", type: "password", placeholder: "leave blank to keep" })),
        field(`Replicate API token ${s.replicate_token_set ? "(set ✓)" : ""}`,
          el("input", { id: "s-rep", type: "password", placeholder: "leave blank to keep" })),
        el("button", { class: "primary", onclick: async () => {
          const body = { comfyui_url: val("s-url"), comfyui_loras_dir: val("s-loras") };
          if (val("s-fal")) body.fal_api_key = val("s-fal");
          if (val("s-rep")) body.replicate_api_token = val("s-rep");
          await api("/api/settings", { method: "POST",
            headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
          refreshStatus();
          $("#job-state").textContent = "Settings saved.";
        } }, "Save Settings"));
    },
  },
};

/* ----------------------------------------------------------- lora hub api */

async function searchLoras() {
  const grid = $("#lora-results");
  grid.replaceChildren(el("p", { class: "desc" }, "Searching CivitAI…"));
  try {
    const q = new URLSearchParams({ query: $("#lq").value,
      base_model: val("lbase"), sort: val("lsort") });
    const items = await api(`/api/loras/search?${q}`);
    grid.replaceChildren();
    if (!items.length) grid.append(el("p", { class: "desc" }, "No results."));
    for (const m of items) {
      const card = el("div", { class: "lora-card" });
      if (m.thumb) card.append(el("img", { class: "thumb", src: m.thumb, loading: "lazy" }));
      card.append(
        el("h4", {}, m.name),
        el("span", { class: "base" }, `${m.base} · ${m.downloads.toLocaleString()} downloads`),
        m.trained_words?.length
          ? el("p", {}, `trigger: ${m.trained_words.slice(0, 3).join(", ")}`)
          : "",
        el("div", { class: "actions" },
          el("button", { class: "secondary", onclick: async (e) => {
            e.target.textContent = "downloading…";
            try {
              await api("/api/loras/download", { method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: m.download_url, filename: m.filename }) });
              e.target.textContent = "✓ installed";
              loadModels();
            } catch (err) { e.target.textContent = `failed: ${err.message}`; }
          } }, "⬇ Install"),
          el("a", { href: m.page, target: "_blank" }, "view on CivitAI ↗")));
      grid.append(card);
    }
  } catch (e) {
    grid.replaceChildren(el("p", { class: "desc" }, `Search failed: ${e.message}`));
  }
}

/* ------------------------------------------------------------ job handling */

async function submit(task, params) {
  const state = $("#job-state");
  state.className = "job-state running";
  state.textContent = `Running ${task} on ${params.compute || val("compute") || "local"}…`;
  try {
    const { id } = await api("/api/jobs", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, params, compute: val("compute") || "local" }) });
    poll(id);
  } catch (e) {
    state.className = "job-state error";
    state.textContent = e.message;
  }
}

async function poll(id) {
  const state = $("#job-state");
  const job = await api(`/api/jobs/${id}`);
  if (job.status === "done") {
    state.className = "job-state";
    state.textContent = `Done — ${job.task}`;
    showOutputs(job.outputs);
    refreshGallery();
  } else if (job.status === "error") {
    state.className = "job-state error";
    state.textContent = job.error;
  } else {
    setTimeout(() => poll(id), 1500);
  }
}

function mediaNode(o) {
  return o.kind === "video"
    ? el("video", { src: o.url, controls: "", loop: "" })
    : el("img", { src: o.url });
}

function showOutputs(outputs) {
  $("#output").replaceChildren(...outputs.map(mediaNode));
}

async function refreshGallery() {
  const jobs = await api("/api/jobs");
  const g = $("#gallery");
  g.replaceChildren();
  for (const j of jobs) {
    for (const o of j.outputs) {
      const n = mediaNode(o);
      n.removeAttribute("controls");
      n.addEventListener("click", () => showOutputs([o]));
      g.append(n);
    }
  }
}

/* ----------------------------------------------------------------- status */

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    $("#status-dot").className = `dot ${s.comfyui ? "up" : "down"}`;
    $("#status-text").textContent = s.comfyui
      ? `ComfyUI connected${s.gpu?.name ? ` — ${s.gpu.name} (${s.gpu.vram_free_gb}/${s.gpu.vram_total_gb} GB free)` : ""}`
      : `ComfyUI offline (${s.comfyui_url}) — local jobs will fail; cloud still works`;
  } catch {
    $("#status-dot").className = "dot down";
    $("#status-text").textContent = "backend unreachable";
  }
}

async function loadModels() {
  try { LORAS = (await api("/api/models")).loras || []; } catch { LORAS = []; }
}

/* ------------------------------------------------------------------- boot */

function showTab(key) {
  currentTab = key;
  document.querySelectorAll("nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === key));
  const panel = $("#panel");
  panel.replaceChildren();
  TABS[key].render(panel);
}

async function boot() {
  PRESETS = await api("/api/presets").catch(() => ({}));
  await loadModels();
  const nav = $("#tabs");
  for (const [key, tab] of Object.entries(TABS)) {
    nav.append(el("button", { "data-tab": key, onclick: () => showTab(key) }, tab.label));
  }
  showTab("image");
  refreshStatus();
  setInterval(refreshStatus, 15000);
  refreshGallery();
}

boot();
