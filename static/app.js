"use strict";

const $ = (id) => document.getElementById(id);
const state = {frames: [], index: 0, playing: false, busy: false, importing: false,
  lossless: false, result: null, mode: "source", dragIndex: null, timer: null, closed: false};
const natural = new Intl.Collator("zh-CN", {numeric: true, sensitivity: "base"});
const MAX_FRAMES = 500;
const MAX_BYTES = 128 * 1024 * 1024;
let noticeTimer;

function notify(text, error = false) {
  clearTimeout(noticeTimer);
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
  $("message").hidden = false;
  noticeTimer = setTimeout(() => {$("message").hidden = true;}, error ? 9000 : 4500);
}
function sizeLabel(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
}
function fps() {
  const value = Number($("fps").value);
  return Number.isInteger(value) && value >= 1 && value <= 60 ? value : null;
}
function totalBytes() {return state.frames.reduce((sum, f) => sum + f.file.size, 0);}
function roundDimension(value) {
  // Match Python's ties-to-even rounding at exactly half a pixel.
  const base = Math.floor(value);
  return Math.max(1, value - base === 0.5 ? base + base % 2 : Math.round(value));
}
function outputSize() {
  if (!state.frames.length) return null;
  const scale = Number($("scale").value) / 100;
  return [roundDimension(state.frames[0].width * scale), roundDimension(state.frames[0].height * scale)];
}
function invalidateResult() {
  if (state.result) URL.revokeObjectURL(state.result.url);
  state.result = null;
  state.mode = "source";
  $("result-card").hidden = true;
  $("result-tab").disabled = true;
  $("result-dot").hidden = true;
  $("download").removeAttribute("href");
  updateTabs();
}
function updateTabs() {
  for (const mode of ["source", "result"]) {
    $(`${mode}-tab`).classList.toggle("active", state.mode === mode);
    $(`${mode}-tab`).setAttribute("aria-pressed", String(state.mode === mode));
  }
}
function update() {
  const count = state.frames.length;
  const locked = state.busy || state.importing || state.closed;
  const dims = outputSize();
  $("empty-state").hidden = count > 0;
  $("preview").hidden = count === 0;
  $("stage-meta").hidden = count === 0;
  $("frame-count").textContent = count;
  $("frame-position").textContent = `${String(count ? state.index + 1 : 0).padStart(3, "0")} / ${String(count).padStart(3, "0")}`;
  $("duration-label").textContent = `${count && fps() ? (count / fps()).toFixed(2) : "0.00"} s`;
  $("output-dimensions").textContent = dims ? `${dims[0]} × ${dims[1]}` : "— × —";
  $("output-duration").textContent = count ? `${count} 帧 / ${fps() ? (count / fps()).toFixed(2) : "—"} s` : "— / —";
  $("input-size").textContent = count ? sizeLabel(totalBytes()) : "—";
  $("scrubber").max = Math.max(0, count - 1);
  $("scrubber").value = state.index;
  $("selected-name").textContent = count ? state.frames[state.index].file.name : "支持一次导入多张 PNG";
  $("selected-name").title = count ? state.frames[state.index].file.name : "";
  $("preview-label").textContent = state.mode === "result" ? "动态 WEBP" : "PNG 序列";
  const previewDims = state.mode === "result" ? [state.result.width, state.result.height] : count ? [state.frames[0].width, state.frames[0].height] : null;
  $("preview-dimensions").textContent = previewDims ? `${previewDims[0]} × ${previewDims[1]}` : "";
  for (const id of ["play", "previous-frame", "next-frame", "scrubber"]) $(id).disabled = !count || locked || state.mode === "result";
  for (const id of ["sort", "reverse", "clear", "remove"]) $(id).disabled = !count || locked;
  $("move-left").disabled = !count || !state.index || locked;
  $("move-right").disabled = !count || state.index === count - 1 || locked;
  for (const id of ["import-top", "import-stage", "demo-button", "file-input"]) $(id).disabled = locked;
  $("settings-fields").disabled = locked;
  $("quality").disabled = locked || state.lossless;
  $("export").disabled = !count || !fps() || locked;
  $("quit").disabled = locked;
  document.body.classList.toggle("busy", locked);
  if (count) {
    const src = state.mode === "result" ? state.result.url : state.frames[state.index].url;
    if ($("preview").getAttribute("src") !== src) $("preview").src = src;
  } else $("preview").removeAttribute("src");
  $("play-icon").hidden = state.playing;
  $("pause-icon").hidden = !state.playing;
  $("play").setAttribute("aria-label", state.playing ? "暂停动画" : "播放动画");
  document.querySelectorAll(".frame-item").forEach((item, i) => {
    item.classList.toggle("selected", i === state.index);
    item.setAttribute("aria-pressed", String(i === state.index));
    item.disabled = locked;
    item.draggable = !locked;
  });
}
function stop() {
  state.playing = false;
  cancelAnimationFrame(state.timer);
  state.timer = null;
}
function play() {
  if (!state.frames.length || state.busy || state.importing || state.closed) return;
  if (state.playing) {stop(); update(); return;}
  if (!fps()) {notify("请输入 1–60 之间的整数帧率。", true); return;}
  state.mode = "source";
  updateTabs();
  state.playing = true;
  const startIndex = state.index;
  const start = performance.now();
  const tick = (now) => {
    if (!state.playing) return;
    const steps = Math.floor((now - start) * fps() / 1000);
    const loops = Number($("loop").value);
    if (loops > 0 && startIndex + steps >= state.frames.length * loops) {
      state.index = state.frames.length - 1;
      stop(); update(); return;
    }
    const next = (startIndex + steps) % state.frames.length;
    if (next !== state.index) {state.index = next; update();}
    state.timer = requestAnimationFrame(tick);
  };
  update();
  state.timer = requestAnimationFrame(tick);
}
function selectFrame(index, scroll = false) {
  if (state.busy || state.importing || !state.frames.length) return;
  stop(); state.mode = "source";
  state.index = Math.max(0, Math.min(index, state.frames.length - 1));
  updateTabs(); update();
  if (scroll) $("frame-list").children[state.index]?.scrollIntoView({block: "nearest", inline: "nearest"});
}
function renderTimeline() {
  $("frame-list").replaceChildren();
  if (!state.frames.length) {
    const empty = document.createElement("div");
    empty.className = "timeline-empty";
    empty.textContent = "你的序列将在这里展开";
    $("frame-list").append(empty);
    return;
  }
  const fragment = document.createDocumentFragment();
  state.frames.forEach((frame, index) => {
    const item = document.createElement("button");
    item.className = "frame-item"; item.draggable = true;
    item.setAttribute("role", "listitem");
    item.setAttribute("aria-label", `第 ${index + 1} 帧：${frame.file.name}`);
    item.title = frame.file.name;
    const thumb = document.createElement("span"); thumb.className = "frame-thumb";
    const img = document.createElement("img"); img.src = frame.thumbUrl; img.alt = ""; img.draggable = false;
    const label = document.createElement("span"); label.className = "frame-index"; label.textContent = String(index + 1).padStart(3, "0");
    thumb.append(img); item.append(thumb, label);
    item.addEventListener("click", () => selectFrame(index));
    item.addEventListener("dragstart", (event) => {
      if (state.busy || state.importing) {event.preventDefault(); return;}
      stop(); state.dragIndex = index;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(index));
      item.classList.add("dragging");
    });
    item.addEventListener("dragover", (event) => {
      if (state.dragIndex !== null) {event.preventDefault(); item.classList.add("drag-over");}
    });
    item.addEventListener("dragleave", () => item.classList.remove("drag-over"));
    item.addEventListener("drop", (event) => {
      if (state.dragIndex === null || state.busy || state.importing) return;
      event.preventDefault(); event.stopPropagation();
      const [moved] = state.frames.splice(state.dragIndex, 1);
      state.frames.splice(index, 0, moved); state.index = index;
      state.dragIndex = null; invalidateResult(); renderTimeline(); update();
    });
    item.addEventListener("dragend", () => {
      state.dragIndex = null;
      document.querySelectorAll(".frame-item").forEach((el) => el.classList.remove("dragging", "drag-over"));
      update();
    });
    fragment.append(item);
  });
  $("frame-list").append(fragment);
}
function releaseFrame(frame) {URL.revokeObjectURL(frame.url); URL.revokeObjectURL(frame.thumbUrl);}
async function makeFrame(file) {
  const bitmap = await createImageBitmap(file);
  try {
    if (bitmap.width * bitmap.height > 16_000_000) throw new Error(`「${file.name}」超过 1600 万像素，请先缩小图片。`);
    const canvas = document.createElement("canvas");
    canvas.width = 112; canvas.height = 100;
    const context = canvas.getContext("2d");
    const scale = Math.min(100 / bitmap.width, 88 / bitmap.height);
    const w = bitmap.width * scale, h = bitmap.height * scale;
    context.drawImage(bitmap, (112 - w) / 2, (100 - h) / 2, w, h);
    const thumb = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!thumb) throw new Error("无法生成预览，请重新导入。");
    return {file, width: bitmap.width, height: bitmap.height, url: URL.createObjectURL(file), thumbUrl: URL.createObjectURL(thumb)};
  } finally {bitmap.close();}
}
async function importFiles(fileList) {
  if (state.busy || state.importing || state.closed) return;
  const files = Array.from(fileList);
  $("file-input").value = "";
  if (!files.length) return;
  if (files.some((file) => !/\.png$/i.test(file.name))) {notify("请选择 PNG 图片。可以一次选择整个序列。", true); return;}
  if (files.length + state.frames.length > MAX_FRAMES) {notify("一次最多导入 500 帧。", true); return;}
  if (files.reduce((sum, file) => sum + file.size, totalBytes()) > MAX_BYTES) {notify("PNG 文件总大小不能超过 128 MiB。", true); return;}
  const duplicates = new Set(state.frames.map((f) => `${f.file.name}\0${f.file.size}\0${f.file.lastModified}`));
  const incoming = files.filter((f) => {
    const key = `${f.name}\0${f.size}\0${f.lastModified}`;
    if (duplicates.has(key)) return false;
    duplicates.add(key); return true;
  });
  if (!incoming.length) {notify("这些图片已经在序列中了。"); return;}
  stop(); state.importing = true; update();
  $("export-label").textContent = "正在读取 PNG…";
  const staged = [];
  let currentName = "";
  try {
    for (const file of incoming.sort((a, b) => natural.compare(a.name, b.name))) {
      currentName = file.name;
      const header = await file.slice(0, 24).arrayBuffer();
      const signature = new Uint8Array(header);
      if ([137,80,78,71,13,10,26,10].some((byte, i) => signature[i] !== byte)) throw new Error(`「${file.name}」不是有效的 PNG 图片。`);
      if (header.byteLength < 24) throw new Error(`「${file.name}」的数据不完整。`);
      const dimensions = new DataView(header);
      const width = dimensions.getUint32(16), height = dimensions.getUint32(20);
      if (!width || !height || width * height > 16_000_000) throw new Error(`「${file.name}」的尺寸无效或超过 1600 万像素，请先检查图片。`);
      const frame = await makeFrame(file);
      staged.push(frame);
      const first = state.frames[0] || staged[0];
      if (frame.width !== first.width || frame.height !== first.height) throw new Error(`「${file.name}」为 ${frame.width} × ${frame.height}，请将所有帧统一为 ${first.width} × ${first.height}。`);
    }
    invalidateResult();
    state.frames.push(...staged);
    state.frames.sort((a, b) => natural.compare(a.file.name, b.file.name));
    state.index = 0;
    renderTimeline();
    notify(`已导入 ${staged.length} 帧，按文件名自然排序。`);
  } catch (error) {
    staged.forEach(releaseFrame);
    notify(error.message || `无法读取「${currentName}」，请检查图片是否损坏。`, true);
  } finally {
    state.importing = false;
    $("export-label").textContent = "生成动态 WebP";
    update();
  }
}
function getFilename() {
  const cleaned = $("filename").value.trim().replace(/\.webp$/i, "").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/[. ]+$/, "");
  return `${cleaned || "animation"}.webp`;
}
function settingsChanged() {
  stop(); invalidateResult();
  document.querySelectorAll("[data-fps]").forEach((button) => {
    const selected = Number(button.dataset.fps) === fps();
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  $("quality-value").replaceChildren(document.createTextNode($("quality").value), Object.assign(document.createElement("span"), {textContent: "%"}));
  update();
}
function setLossless(value) {
  state.lossless = value;
  $("lossless").classList.toggle("selected", value);
  $("lossy").classList.toggle("selected", !value);
  $("lossless").setAttribute("aria-pressed", String(value));
  $("lossy").setAttribute("aria-pressed", String(!value));
  document.querySelector(".quality-field").classList.toggle("quality-disabled", value);
  $("quality-hint").textContent = value ? "保留像素画质，画质滑块不参与无损压缩。" : "推荐 80–90，兼顾画质与文件体积。";
  settingsChanged();
}
async function convert() {
  if (!state.frames.length || state.busy || state.importing || state.closed || !fps()) return;
  const dims = outputSize();
  const estimate = dims[0] * dims[1] * 4 * state.frames.length + state.frames[0].width * state.frames[0].height * 4;
  if (estimate > 256 * 1024 ** 2) {notify("序列帧解码后超过 256 MiB，请降低输出比例或减少帧数。", true); return;}
  stop(); state.busy = true; update();
  $("export-label").textContent = "正在编码…";
  $("export-arrow").hidden = true; $("export-spinner").hidden = false;
  $("export-note").textContent = "正在本机转换，较大的序列可能需要一些时间";
  const form = new FormData();
  form.append("settings", JSON.stringify({fps: fps(), quality: Number($("quality").value),
    lossless: state.lossless, scale: Number($("scale").value), loop: Number($("loop").value)}));
  state.frames.forEach((frame) => form.append("frames", frame.file, frame.file.name));
  try {
    const response = await fetch("/api/convert", {method: "POST", body: form});
    if (!response.ok) {
      const details = await response.json().catch(() => ({}));
      throw new Error(details.error || `转换失败（${response.status}），请重试。`);
    }
    const blob = await response.blob();
    invalidateResult();
    state.result = {url: URL.createObjectURL(blob), size: blob.size,
      width: Number(response.headers.get("X-Image-Width")), height: Number(response.headers.get("X-Image-Height"))};
    state.mode = "result";
    $("download").href = state.result.url;
    $("download").download = getFilename();
    $("result-card").hidden = false; $("result-dot").hidden = false; $("result-tab").disabled = false;
    $("result-size").textContent = sizeLabel(blob.size);
    $("result-dimensions").textContent = `${state.result.width} × ${state.result.height}`;
    const saved = (1 - blob.size / totalBytes()) * 100;
    $("saved-size").textContent = saved >= 0 ? `体积减少 ${saved.toFixed(1)}%` : `比 PNG 增大 ${(-saved).toFixed(1)}%`;
    $("saved-size").title = "与导入的全部 PNG 文件总大小相比";
    updateTabs();
    notify(state.frames.length === 1 ? "单张 PNG 已导出为静态 WebP。" : "动态 WebP 已生成，可以预览并下载。");
  } catch (error) {
    notify(error instanceof TypeError ? "无法连接本机转换器，请确认启动窗口仍在运行。" : error.message, true);
  } finally {
    state.busy = false;
    $("export-label").textContent = "生成动态 WebP";
    $("export-arrow").hidden = false; $("export-spinner").hidden = true;
    $("export-note").textContent = "透明背景会自动保留";
    update();
  }
}
function moveFrame(direction) {
  if (state.busy || state.importing) return;
  const target = state.index + direction;
  if (target < 0 || target >= state.frames.length) return;
  stop();
  const [frame] = state.frames.splice(state.index, 1);
  state.frames.splice(target, 0, frame); state.index = target;
  invalidateResult(); renderTimeline(); selectFrame(target, true);
}
async function loadDemo() {
  if (state.busy || state.importing) return;
  $("demo-button").disabled = true;
  const files = [];
  const canvas = document.createElement("canvas"); canvas.width = 256; canvas.height = 256;
  const ctx = canvas.getContext("2d");
  const box = (x, y, w, h, r, fill) => {ctx.fillStyle = fill; ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.fill();};
  try {
    for (let i = 0; i < 24; i++) {
      const angle = i / 24 * Math.PI * 2;
      const bounce = Math.sin(angle) * 9;
      ctx.clearRect(0, 0, 256, 256);
      ctx.fillStyle = "#3c4a3820"; ctx.beginPath(); ctx.ellipse(128, 224, 43 + bounce / 2, 5, 0, 0, Math.PI * 2); ctx.fill();
      ctx.save(); ctx.translate(128, 129 + bounce); ctx.rotate(Math.sin(angle) * .055);
      box(-37, 62, 23, 23, 8, "#46563f"); box(14, 62, 23, 23, 8, "#46563f");
      box(-67, -8, 23, 46, 11, "#ef9c69");
      ctx.save(); ctx.translate(53, -4); ctx.rotate(-.3 + Math.sin(angle) * .6); box(-8, -41, 18, 52, 9, "#ef9c69"); ctx.restore();
      box(-49, -58, 98, 130, 29, "#e75f3f");
      box(-38, -47, 76, 82, 21, "#ffdd9c");
      ctx.fillStyle = "#394235";
      if (i === 11 || i === 12) {box(-23, -13, 13, 3, 2, "#394235"); box(10, -13, 13, 3, 2, "#394235");}
      else {box(-20, -22, 7, 13, 4, "#394235"); box(13, -22, 7, 13, 4, "#394235");}
      ctx.beginPath(); ctx.arc(0, -1, 12, .2, Math.PI - .2); ctx.lineWidth = 3; ctx.strokeStyle = "#394235"; ctx.lineCap = "round"; ctx.stroke();
      box(-11, 45, 22, 7, 3, "#f8b16e");
      ctx.restore();
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      files.push(new File([blob], `demo_${String(i + 1).padStart(3, "0")}.png`, {type: "image/png", lastModified: 0}));
    }
    await importFiles(files);
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches && state.frames.length) play();
  } catch {notify("示例生成失败，请导入自己的 PNG 序列。", true);}
  finally {update();}
}

for (const id of ["import-top", "import-stage"]) $(id).addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", (event) => importFiles(event.target.files));
$("demo-button").addEventListener("click", loadDemo);
$("play").addEventListener("click", play);
$("previous-frame").addEventListener("click", () => selectFrame((state.index - 1 + state.frames.length) % state.frames.length, true));
$("next-frame").addEventListener("click", () => selectFrame((state.index + 1) % state.frames.length, true));
$("scrubber").addEventListener("input", () => selectFrame(Number($("scrubber").value)));
$("source-tab").addEventListener("click", () => {state.mode = "source"; updateTabs(); update();});
$("result-tab").addEventListener("click", () => {if (state.result) {stop(); state.mode = "result"; updateTabs(); update();}});
$("sort").addEventListener("click", () => {stop(); state.frames.sort((a, b) => natural.compare(a.file.name, b.file.name)); state.index = 0; invalidateResult(); renderTimeline(); update();});
$("reverse").addEventListener("click", () => {stop(); state.frames.reverse(); state.index = 0; invalidateResult(); renderTimeline(); update();});
$("clear").addEventListener("click", () => {stop(); invalidateResult(); state.frames.forEach(releaseFrame); state.frames = []; state.index = 0; renderTimeline(); update();});
$("remove").addEventListener("click", () => {stop(); invalidateResult(); releaseFrame(state.frames.splice(state.index, 1)[0]); state.index = Math.max(0, Math.min(state.index, state.frames.length - 1)); renderTimeline(); update();});
$("move-left").addEventListener("click", () => moveFrame(-1));
$("move-right").addEventListener("click", () => moveFrame(1));
for (const id of ["fps", "quality", "scale", "loop"]) $(id).addEventListener("input", settingsChanged);
$("fps").addEventListener("change", () => {if (!fps()) notify("帧率需要是 1–60 之间的整数。", true);});
document.querySelectorAll("[data-fps]").forEach((button) => button.addEventListener("click", () => {$("fps").value = button.dataset.fps; settingsChanged();}));
$("lossy").addEventListener("click", () => setLossless(false));
$("lossless").addEventListener("click", () => setLossless(true));
$("filename").addEventListener("input", () => {$("download").download = getFilename();});
$("filename").addEventListener("change", () => {$("filename").value = getFilename().slice(0, -5);});
$("export").addEventListener("click", convert);
$("quit").addEventListener("click", async () => {
  if (state.busy || state.importing || state.closed) return;
  $("quit").disabled = true;
  try {
    const response = await fetch("/api/shutdown", {method: "POST"});
    if (!response.ok) throw new Error("暂时无法退出，请完成当前转换后再试。");
    stop(); state.closed = true; update();
    document.querySelector(".local-badge").textContent = "应用已退出";
    $("export-note").textContent = "应用已退出。需要继续时，请重新打开 Frameflow。";
    notify("应用已退出，已生成的文件仍可下载。可以关闭此页面了。");
  } catch (error) {notify(error.message || "无法连接本机应用。", true); $("quit").disabled = false;}
});
document.querySelectorAll("[data-bg]").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll("[data-bg]").forEach((other) => {other.classList.toggle("active", other === button); other.setAttribute("aria-pressed", String(other === button));});
  $("drop-zone").classList.remove("checker-stage", "light-stage", "dark-stage");
  $("drop-zone").classList.add(`${button.dataset.bg}-stage`);
}));
let dragDepth = 0;
document.addEventListener("dragenter", (event) => {
  if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
  event.preventDefault(); dragDepth++;
  if (!state.busy && !state.importing) $("drop-overlay").hidden = false;
});
document.addEventListener("dragleave", () => {dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $("drop-overlay").hidden = true;});
document.addEventListener("dragover", (event) => {
  if (Array.from(event.dataTransfer?.types || []).includes("Files")) {event.preventDefault(); event.dataTransfer.dropEffect = state.busy || state.importing ? "none" : "copy";}
});
document.addEventListener("drop", (event) => {
  dragDepth = 0; $("drop-overlay").hidden = true;
  if (event.dataTransfer?.files.length) {event.preventDefault(); importFiles(event.dataTransfer.files);}
});
document.addEventListener("visibilitychange", () => {if (document.hidden) {stop(); update();}});
document.addEventListener("keydown", (event) => {
  if (["INPUT", "SELECT", "TEXTAREA", "BUTTON", "A"].includes(document.activeElement?.tagName) || state.busy || state.importing || !state.frames.length) return;
  if (event.code === "Space") {event.preventDefault(); play();}
  if (event.code === "ArrowLeft") {event.preventDefault(); selectFrame(Math.max(0, state.index - 1), true);}
  if (event.code === "ArrowRight") {event.preventDefault(); selectFrame(Math.min(state.frames.length - 1, state.index + 1), true);}
});
update();
