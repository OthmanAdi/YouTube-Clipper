// Popup controller: health probe + state machine + live WS event handler.

import { getHealth } from "../lib/api.js";
import { mmss, lengthLabel } from "../lib/format.js";

type Section = "empty" | "pending" | "running" | "done" | "failed";

const STAGE_ORDER = [
  "resolve",
  "download",
  "normalize",
  "transcribe",
  "summarize",
  "write_note",
];

function show(sec: Section) {
  for (const id of ["empty", "pending", "running", "done", "failed"]) {
    const el = document.getElementById(`${id}-state`);
    if (el) el.hidden = id !== sec;
  }
}

function q<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

function setProgressByStage(stage: string) {
  const idx = STAGE_ORDER.indexOf(stage);
  const pct = idx >= 0 ? ((idx + 1) / STAGE_ORDER.length) * 100 : 0;
  q<HTMLDivElement>("r-bar").style.width = `${pct}%`;
  q("r-stage").textContent = `Stage ${idx + 1}/6 · ${stage}`;
}

function fillPending(p: any) {
  q("m-title").textContent = p?.video_title || "(untitled)";
  q("m-channel").textContent = p?.channel_name || "";
  q("m-range").textContent =
    p && typeof p.start_s === "number"
      ? `${mmss(p.start_s)} → ${mmss(p.end_s)}  (${lengthLabel(p.end_s - p.start_s)})`
      : "";
}

function handleEvent(ev: any) {
  if (!ev) return;
  if (ev.type === "stage_start") {
    show("running");
    setProgressByStage(ev.stage);
  } else if (ev.type === "stage_done") {
    setProgressByStage(ev.stage);
    q("r-last").textContent = `${ev.stage} done in ${ev.duration_ms}ms`;
  } else if (ev.type === "done") {
    show("done");
    q("d-path").textContent = ev.note || "";
  } else if (ev.type === "failed") {
    show("failed");
    q("f-msg").textContent = `${ev.stage}: ${ev.error_message || ev.error_class}`;
  } else if (ev.type === "progress") {
    q("r-last").textContent = ev.message || "";
  } else if (ev.type === "enqueued" || ev.type === "running") {
    show("running");
    q("r-stage").textContent = "Queued…";
  }
}

async function init() {
  // Health probe
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

  const state = await chrome.runtime.sendMessage({ type: "popup.get_state" });

  if (state?.lastEvent?.type === "done") {
    show("done");
    q("d-path").textContent = state.lastEvent.note || "";
  } else if (state?.lastEvent?.type === "failed") {
    show("failed");
    q("f-msg").textContent = `${state.lastEvent.stage}: ${state.lastEvent.error_message}`;
  } else if (
    state?.currentJobId &&
    state?.lastEvent &&
    state.lastEvent.type !== "done" &&
    state.lastEvent.type !== "failed"
  ) {
    show("running");
    handleEvent(state.lastEvent);
  } else if (state?.pending) {
    show("pending");
    fillPending(state.pending);
  } else {
    show("empty");
  }

  q("extract-btn")?.addEventListener("click", onExtract);
  q("cancel-btn")?.addEventListener("click", onCancel);
  q("reset")?.addEventListener("click", onReset);
  q("failed-reset")?.addEventListener("click", onReset);
  q("open-note")?.addEventListener("click", () => copyPath(q("d-path").textContent || ""));
  q("open-folder")?.addEventListener("click", () => {
    const p = q("d-path").textContent || "";
    if (!p) return;
    const folder = p.replace(/[\\/][^\\/]+$/, "");
    copyPath(folder);
  });

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === "popup.event") handleEvent(msg.event);
  });
}

async function copyPath(p: string) {
  if (!p) return;
  try {
    await navigator.clipboard.writeText(p);
    const r = q("r-last");
    if (r) r.textContent = `Copied: ${p}`;
  } catch {
    /* clipboard write can fail in some contexts; we just ignore */
  }
}

async function onExtract() {
  const summarizer = (q<HTMLSelectElement>("summarizer-select")).value;
  show("running");
  q("r-stage").textContent = "Queued…";
  q("r-last").textContent = "Sending to daemon…";
  const resp = await chrome.runtime.sendMessage({ type: "popup.extract", summarizer });
  if (!resp?.ok) {
    show("failed");
    q("f-msg").textContent = resp?.error || "Unknown error";
  }
}

async function onCancel() {
  await chrome.runtime.sendMessage({ type: "popup.cancel" });
  show("empty");
}

async function onReset() {
  await chrome.runtime.sendMessage({ type: "popup.reset" });
  show("empty");
}

init().catch((e) => {
  show("failed");
  const el = q("f-msg");
  if (el) el.textContent = String(e?.message ?? e);
});
