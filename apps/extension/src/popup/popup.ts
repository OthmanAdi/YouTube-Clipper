// Popup: reads state from chrome.storage.session, re-renders on every change.
// All persistence lives in SW + storage — the popup is pure view.

import { getHealth } from "../lib/api.js";
import { mmss, lengthLabel } from "../lib/format.js";
import {
  type JobView,
  type PendingSelection,
  getPending,
  getJobs,
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
  // While running a stage that is not yet in stages_done, show "completed + half of current".
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
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    /* ignore */
  }
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
  sub.textContent = `${range} · ${stageLabel} · ${job.summarizer}`;

  const bar = node.querySelector(".job-bar") as HTMLElement;
  bar.style.width = `${progressPercent(job)}%`;
  if (job.state === "done") bar.classList.add("done");
  if (job.state === "failed") bar.classList.add("failed");

  const logEl = node.querySelector(".job-log")!;
  logEl.textContent = job.last_log || "";

  // Stages pill row
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

  // Actions
  const actions = node.querySelector(".job-actions") as HTMLElement;
  actions.innerHTML = "";
  if (job.note_path) {
    const pathEl = document.createElement("div");
    pathEl.className = "path-text";
    pathEl.textContent = job.note_path;
    actions.parentElement!.insertBefore(pathEl, actions);
    const copyNote = document.createElement("button");
    copyNote.textContent = "Copy note path";
    copyNote.onclick = () => copyText(job.note_path || "");
    actions.appendChild(copyNote);
    const copyFolder = document.createElement("button");
    copyFolder.textContent = "Copy folder";
    copyFolder.onclick = () => {
      const folder = (job.note_path || "").replace(/[\\/][^\\/]+$/, "");
      copyText(folder);
    };
    actions.appendChild(copyFolder);
  }
  if (job.state === "failed" && job.error_message) {
    const errEl = document.createElement("div");
    errEl.className = "error-text";
    errEl.textContent = `${job.error_stage}: ${job.error_message}`;
    actions.parentElement!.insertBefore(errEl, actions);
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
  // Default expanded if running, failed, or done (so user sees full info).
  details.hidden = job.state === "queued";
  if (!details.hidden) toggle.classList.add("open");
  toggle.onclick = () => {
    details.hidden = !details.hidden;
    toggle.classList.toggle("open", !details.hidden);
  };

  return node;
}

function renderPending(pending: PendingSelection | null) {
  if (!pending) {
    show("pending-card", false);
    return;
  }
  show("pending-card", true);
  setText("p-title", pending.video_title || "(untitled)");
  setText("p-channel", pending.channel_name || "");
  setText(
    "p-range",
    `${mmss(pending.start_s)} → ${mmss(pending.end_s)}  (${lengthLabel(pending.end_s - pending.start_s)})`
  );
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
  list.innerHTML = "";
  for (const job of jobs) {
    list.appendChild(buildJobRow(job));
  }
}

function renderEmptyState(pending: PendingSelection | null, jobs: JobView[]) {
  const empty = !pending && jobs.length === 0;
  show("empty-state", empty);
}

async function render() {
  const [pending, jobs] = await Promise.all([getPending(), getJobs()]);
  renderPending(pending);
  renderJobs(jobs);
  renderEmptyState(pending, jobs);
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

async function onExtractClicked() {
  const summarizer = (q<HTMLSelectElement>("summarizer-select")).value;
  const r = await chrome.runtime.sendMessage({ type: "popup.extract", summarizer });
  if (!r?.ok) {
    alert(`Extract failed: ${r?.error || "unknown"}`);
  }
  await render();
}

async function onDismissPending() {
  await chrome.runtime.sendMessage({ type: "popup.dismiss_pending" });
}

async function init() {
  await wireHealthChip();
  // Ask SW to re-attach any in-flight WSs that might have been lost on eviction.
  try {
    await chrome.runtime.sendMessage({ type: "popup.rehydrate" });
  } catch {
    /* SW may be cold-booting; render anyway */
  }
  await render();

  q("extract-btn")?.addEventListener("click", () => void onExtractClicked());
  q("dismiss-pending-btn")?.addEventListener("click", () => void onDismissPending());

  // Live updates: whenever the SW updates the storage, re-render the whole popup.
  onChange(() => void render());

  // Re-check daemon health every 3s while the popup is open.
  setInterval(() => void wireHealthChip(), 3000);
}

init().catch((e) => {
  console.error(e);
  alert(String(e?.message ?? e));
});
