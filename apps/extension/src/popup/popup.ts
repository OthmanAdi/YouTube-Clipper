// Popup: reads state from chrome.storage.session, re-renders on every change.
// Persists prefs (default summarizer, output dir override) in chrome.storage.local.

import { getHealth } from "../lib/api.js";
import { mmss, lengthLabel } from "../lib/format.js";
import {
  type JobView,
  type SegmentSelection,
  type UiPrefs,
  SEGMENT_COLORS,
  getSegments,
  getJobs,
  getPrefs,
  setPrefs,
  onChange,
} from "../lib/state.js";

const STAGE_ORDER = ["resolve", "download", "normalize", "transcribe", "summarize", "write_note"];

function q<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

function show(id: string, visible: boolean) {
  const el = document.getElementById(id);
  if (el) el.hidden = !visible;
}

function setText(id: string, text: string) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function stageIndex(stage: string | null): number {
  if (!stage) return -1;
  return STAGE_ORDER.indexOf(stage);
}

function progressPercent(job: JobView): number {
  if (job.state === "done") return 100;
  if (job.state === "failed") {
    const idx = stageIndex(job.error_stage);
    return idx >= 0 ? ((idx + 1) / STAGE_ORDER.length) * 100 : 0;
  }
  const doneCount = job.stages_done.length;
  if (doneCount === STAGE_ORDER.length) return 100;
  const inFlight = job.current_stage && !job.stages_done.includes(job.current_stage) ? 0.5 : 0;
  return ((doneCount + inFlight) / STAGE_ORDER.length) * 100;
}

function iconFor(job: JobView): string {
  switch (job.state) {
    case "queued":
      return "⏳";
    case "running":
      return "⚙";
    case "done":
      return "✓";
    case "failed":
      return "⚠";
  }
}

async function copyText(text: string) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    /* ignore */
  }
}

function folderOf(p: string): string {
  return p.replace(/[\\/][^\\/]+$/, "");
}

// Build a comprehensive Claude Code prompt for custom website design.
function buildClaudePrompt(job: JobView): string {
  const folder = job.note_path ? folderOf(job.note_path) : "";
  return `Use the frontend-design skill to build a stunning custom single-page website for this YouTube clip extraction.

Inputs:
- Folder: ${folder}
- note.md (full markdown, with TL;DR, bullets, notable quotes, transcript)
- summary.json (structured: tldr, bullets, notable_quotes, tags)
- transcript.json (word-level segments with timestamps)
- audio.mp3 (playable in browser)

Title: "${job.video_title ?? ""}"
Channel: "${job.channel_name ?? ""}"
Range: ${mmss(job.start_s)} → ${mmss(job.end_s)} (${lengthLabel(job.end_s - job.start_s)})
Source: ${job.url}

Output: a single self-contained index.html in the SAME folder. Embed the audio (audio.mp3) with a click-to-jump transcript. Editorial dark theme. No CDN dependencies — inline CSS and minimal vanilla JS only. Make it beautiful and shareable.

Do NOT overwrite the existing index.html that the daemon's built-in template wrote — save your custom version as index.custom.html next to it.`;
}

function buildJobRow(job: JobView): HTMLElement {
  const tpl = document.getElementById("job-row-tpl") as HTMLTemplateElement;
  const node = tpl.content.firstElementChild!.cloneNode(true) as HTMLElement;
  node.dataset.jobId = job.job_id;

  const icon = node.querySelector(".job-icon")!;
  icon.textContent = iconFor(job);
  icon.classList.add(job.state);

  const title = node.querySelector(".job-title")!;
  title.textContent = job.video_title || "(untitled)";

  const sub = node.querySelector(".job-sub")!;
  const range = `${mmss(job.start_s)} → ${mmss(job.end_s)} · ${lengthLabel(job.end_s - job.start_s)}`;
  const stageLabel =
    job.state === "done"
      ? "done"
      : job.state === "failed"
        ? `failed at ${job.error_stage ?? "?"}`
        : job.current_stage
          ? `${job.current_stage} (${stageIndex(job.current_stage) + 1}/${STAGE_ORDER.length})`
          : "queued";
  const provLabel = job.model ? `${job.summarizer}:${job.model}` : job.summarizer;
  sub.textContent = `${range} · ${stageLabel} · ${provLabel} · ${job.detail || "standard"}`;

  const bar = node.querySelector(".job-bar") as HTMLElement;
  bar.style.width = `${progressPercent(job)}%`;
  if (job.state === "done") bar.classList.add("done");
  if (job.state === "failed") bar.classList.add("failed");

  const logEl = node.querySelector(".job-log")!;
  logEl.textContent = job.last_log || "";

  // Stage pills
  const stagesWrap = node.querySelector(".job-stages") as HTMLElement;
  stagesWrap.innerHTML = "";
  for (const s of STAGE_ORDER) {
    const pill = document.createElement("span");
    pill.className = "stage-pill";
    if (job.stages_done.includes(s)) pill.classList.add("done");
    else if (s === job.current_stage && job.state === "running") pill.classList.add("running");
    else if (s === job.error_stage && job.state === "failed") pill.classList.add("failed");
    const dur = job.durations_ms[s];
    pill.textContent = dur ? `${s} ${dur}ms` : s;
    stagesWrap.appendChild(pill);
  }

  // Actions row
  const actions = node.querySelector(".job-actions") as HTMLElement;
  const detailsEl = node.querySelector(".job-details") as HTMLElement;
  actions.innerHTML = "";

  if (job.note_path) {
    const pathEl = document.createElement("div");
    pathEl.className = "path-text";
    pathEl.textContent = job.note_path;
    detailsEl.insertBefore(pathEl, actions);

    const copyNote = document.createElement("button");
    copyNote.textContent = "Copy note path";
    copyNote.onclick = () => copyText(job.note_path || "");
    actions.appendChild(copyNote);

    const copyFolder = document.createElement("button");
    copyFolder.textContent = "Copy folder";
    copyFolder.onclick = () => copyText(folderOf(job.note_path || ""));
    actions.appendChild(copyFolder);
  }

  if (job.state === "done") {
    if (job.website_path) {
      const openSite = document.createElement("button");
      openSite.textContent = "Open website";
      openSite.onclick = () => {
        const u = "file:///" + (job.website_path || "").replace(/\\/g, "/");
        chrome.tabs.create({ url: u }).catch(() => copyText(job.website_path || ""));
      };
      actions.appendChild(openSite);
    } else {
      const makeSite = document.createElement("button");
      makeSite.textContent = "Generate website";
      makeSite.className = "primary";
      makeSite.onclick = async () => {
        makeSite.disabled = true;
        makeSite.textContent = "Generating…";
        const r = await chrome.runtime.sendMessage({ type: "popup.make_website", job_id: job.job_id });
        if (!r?.ok) {
          makeSite.disabled = false;
          makeSite.textContent = "Generate website";
          alert(`Website generation failed: ${r?.error ?? "unknown"}`);
        }
        // success: storage onChange triggers a re-render with the "Open website" button.
      };
      actions.appendChild(makeSite);
    }

    const handoff = document.createElement("button");
    handoff.textContent = "Custom design (Claude prompt)";
    handoff.title = "Copies a frontend-design prompt to clipboard for use in Claude Code";
    handoff.onclick = () => copyText(buildClaudePrompt(job));
    actions.appendChild(handoff);
  }

  if (job.state === "failed" && job.error_message) {
    const errEl = document.createElement("div");
    errEl.className = "error-text";
    errEl.textContent = `${job.error_stage}: ${job.error_message}`;
    detailsEl.insertBefore(errEl, actions);
  }

  const dismiss = document.createElement("button");
  dismiss.textContent = "Dismiss";
  dismiss.onclick = async () => {
    await chrome.runtime.sendMessage({ type: "popup.dismiss_job", job_id: job.job_id });
  };
  actions.appendChild(dismiss);

  // Toggle expansion
  const toggle = node.querySelector(".job-toggle") as HTMLButtonElement;
  const details = node.querySelector(".job-details") as HTMLElement;
  details.hidden = job.state === "queued";
  if (!details.hidden) toggle.classList.add("open");
  toggle.onclick = () => {
    details.hidden = !details.hidden;
    toggle.classList.toggle("open", !details.hidden);
  };

  return node;
}

// Build one segment row from the template. Bound on click handlers go through the SW.
function buildSegmentRow(seg: SegmentSelection): HTMLElement {
  const tpl = document.getElementById("segment-row-tpl") as HTMLTemplateElement;
  const node = tpl.content.firstElementChild!.cloneNode(true) as HTMLElement;
  node.dataset.segmentId = seg.segment_id;

  const colorName = SEGMENT_COLORS[seg.color_idx % SEGMENT_COLORS.length];
  const dot = node.querySelector(".seg-dot") as HTMLElement;
  dot.classList.add(`seg-${colorName}`);
  dot.title = colorName;

  const title = node.querySelector(".seg-title")!;
  title.textContent = seg.video_title || "(untitled)";

  const range = node.querySelector(".seg-range")!;
  range.textContent = `${mmss(seg.start_s)} → ${mmss(seg.end_s)} · ${lengthLabel(seg.end_s - seg.start_s)}`;

  const extractBtn = node.querySelector(".seg-extract") as HTMLButtonElement;
  extractBtn.onclick = () => void extractSegments(seg.segment_id, extractBtn);

  const removeBtn = node.querySelector(".seg-remove") as HTMLButtonElement;
  removeBtn.onclick = async () => {
    await chrome.runtime.sendMessage({
      type: "popup.remove_segment",
      segment_id: seg.segment_id,
    });
  };

  return node;
}

function renderPending(segments: SegmentSelection[], prefs: UiPrefs) {
  if (segments.length === 0) {
    show("pending-card", false);
    return;
  }
  show("pending-card", true);
  setText("pending-count", `(${segments.length})`);

  const list = q("pending-list");
  list.innerHTML = "";
  for (const seg of segments) {
    list.appendChild(buildSegmentRow(seg));
  }

  // Restore last-used summarizer:model + detail + output dir.
  const sel = q<HTMLSelectElement>("summarizer-select");
  if (sel) {
    // Guard against a saved value that no longer exists in the dropdown (e.g. after we
    // change the pre-baked options). Fall back to "ollama".
    const opts = Array.from(sel.options).map((o) => o.value);
    sel.value = opts.includes(prefs.default_summarizer_model)
      ? prefs.default_summarizer_model
      : "ollama";
  }
  const detSel = q<HTMLSelectElement>("detail-select");
  if (detSel) detSel.value = prefs.default_detail;
  const od = q<HTMLInputElement>("output-dir-input");
  if (od && !od.value) od.value = prefs.output_dir_override ?? "";
}

function renderJobs(jobs: JobView[]) {
  const list = q("jobs-list");
  if (jobs.length === 0) {
    show("jobs-section", false);
    list.innerHTML = "";
    return;
  }
  show("jobs-section", true);
  setText("jobs-count", `(${jobs.length})`);
  const finishedCount = jobs.filter((j) => j.state === "done" || j.state === "failed").length;
  show("clear-done-btn", finishedCount > 0);
  list.innerHTML = "";
  for (const job of jobs) {
    list.appendChild(buildJobRow(job));
  }
}

function renderEmptyState(segments: SegmentSelection[], jobs: JobView[]) {
  const empty = segments.length === 0 && jobs.length === 0;
  show("empty-state", empty);
}

async function render() {
  const [segments, jobs, prefs] = await Promise.all([getSegments(), getJobs(), getPrefs()]);
  renderPending(segments, prefs);
  renderJobs(jobs);
  renderEmptyState(segments, jobs);
}

async function wireHealthChip() {
  const chip = q("health-chip");
  try {
    await getHealth();
    chip.classList.remove("dim", "bad");
    chip.classList.add("ok");
    chip.title = "Daemon up";
  } catch {
    chip.classList.remove("ok", "dim");
    chip.classList.add("bad");
    chip.title = "Daemon not running — run scripts\\start-daemon.ps1";
  }
}

// Extract one segment (by id) or all pending (id = null). Disables the button while in flight
// so the user can't double-fire. Settings are read from the shared header on each call.
async function extractSegments(segmentId: string | null, btn?: HTMLButtonElement) {
  const summarizerModel = q<HTMLSelectElement>("summarizer-select").value;
  const detail = (q<HTMLSelectElement>("detail-select")).value as "quick" | "standard" | "deep";
  const outputDir = (q<HTMLInputElement>("output-dir-input")).value.trim();
  await setPrefs({
    default_summarizer_model: summarizerModel,
    default_detail: detail,
    output_dir_override: outputDir || null,
  });
  if (btn) {
    btn.disabled = true;
    btn.dataset.prevText = btn.textContent || "";
    btn.textContent = segmentId ? "Extracting…" : "Extracting all…";
  }
  const r = await chrome.runtime.sendMessage({
    type: "popup.extract",
    summarizer: summarizerModel,
    segment_id: segmentId,
    output_dir: outputDir || null,
    detail,
  });
  if (btn) {
    btn.disabled = false;
    btn.textContent = btn.dataset.prevText || "Extract";
  }
  if (!r?.ok) {
    alert(`Extract failed: ${r?.error || "unknown"}`);
  }
  await render();
}

async function onDismissPending() {
  await chrome.runtime.sendMessage({ type: "popup.dismiss_pending" });
}

async function onClearDone() {
  await chrome.runtime.sendMessage({ type: "popup.clear_done" });
}

async function init() {
  await wireHealthChip();
  try {
    await chrome.runtime.sendMessage({ type: "popup.rehydrate" });
  } catch {
    /* SW may be cold-booting; render anyway */
  }
  await render();

  q("extract-all-btn")?.addEventListener("click", (ev) => {
    const btn = ev.currentTarget as HTMLButtonElement;
    void extractSegments(null, btn);
  });
  q("dismiss-pending-btn")?.addEventListener("click", () => void onDismissPending());
  q("clear-done-btn")?.addEventListener("click", () => void onClearDone());

  onChange(() => void render());

  setInterval(() => void wireHealthChip(), 3000);
}

init().catch((e) => {
  console.error(e);
  alert(String(e?.message ?? e));
});
