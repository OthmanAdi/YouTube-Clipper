// Content script. Self-contained — MV3 content scripts can't import ES modules,
// so the small helpers from lib/ are inlined here on purpose.

// ---------- inlined: format ----------
function mmss(s: number): string {
  s = Math.max(0, Math.floor(s));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}
function lengthLabel(s: number): string {
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}m ${sec}s`;
}

// ---------- inlined: youtube ----------
interface YouTubeContext {
  url: string;
  videoId: string;
  channelName: string | null;
  videoTitle: string | null;
}
function readYouTubeContext(): YouTubeContext | null {
  const url = location.href;
  const match = url.match(/[?&]v=([^&]+)/);
  if (!match) return null;
  const videoId = match[1];
  const titleEl = document.querySelector(
    "h1.ytd-watch-metadata yt-formatted-string, h1.title yt-formatted-string"
  ) as HTMLElement | null;
  const channelEl = document.querySelector(
    "ytd-channel-name yt-formatted-string a, #channel-name a"
  ) as HTMLElement | null;
  return {
    url: `https://www.youtube.com/watch?v=${videoId}`,
    videoId,
    videoTitle:
      titleEl?.textContent?.trim() ??
      (document.title.replace(/ - YouTube$/, "").trim() || null),
    channelName: channelEl?.textContent?.trim() ?? null,
  };
}
function getVideoEl(): HTMLVideoElement | null {
  return document.querySelector("video.html5-main-video") as HTMLVideoElement | null;
}
function getProgressBarEl(): HTMLElement | null {
  return document.querySelector(".ytp-progress-bar") as HTMLElement | null;
}

// ---------- state ----------
let dragging = false;
let startS = 0;
let endS = 0;
let overlay: HTMLDivElement | null = null;
let tooltip: HTMLDivElement | null = null;

function injectStyles() {
  if (document.getElementById("ytc-styles")) return;
  const link = document.createElement("link");
  link.id = "ytc-styles";
  link.rel = "stylesheet";
  link.href = chrome.runtime.getURL("assets/content.css");
  document.head.appendChild(link);
}

function ensureOverlay(bar: HTMLElement): HTMLDivElement {
  if (overlay && overlay.isConnected) return overlay;
  overlay = document.createElement("div");
  overlay.id = "ytc-overlay";
  bar.appendChild(overlay);
  return overlay;
}

function ensureTooltip(): HTMLDivElement {
  if (tooltip && tooltip.isConnected) return tooltip;
  tooltip = document.createElement("div");
  tooltip.id = "ytc-tooltip";
  document.body.appendChild(tooltip);
  return tooltip;
}

function clearUi() {
  overlay?.remove();
  overlay = null;
  tooltip?.remove();
  tooltip = null;
}

function toast(msg: string, ms = 2400) {
  const t = document.createElement("div");
  t.id = "ytc-toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

function xToSeconds(bar: HTMLElement, x: number, duration: number): number {
  const rect = bar.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (x - rect.left) / rect.width));
  return ratio * duration;
}

function secondsToPct(sec: number, duration: number): number {
  return Math.max(0, Math.min(1, sec / duration)) * 100;
}

function updateTooltip(clientX: number, clientY: number) {
  const tt = ensureTooltip();
  const s = Math.min(startS, endS);
  const e = Math.max(startS, endS);
  tt.textContent = `${mmss(s)} → ${mmss(e)}  (${lengthLabel(e - s)})`;
  tt.style.left = `${clientX + 12}px`;
  tt.style.top = `${clientY + 12}px`;
}

function onMouseDown(ev: MouseEvent) {
  // Alt+drag — YouTube reserves Ctrl for its own seekbar shortcuts (frame-step / chapter jump).
  if (!ev.altKey) return;
  const bar = getProgressBarEl();
  const video = getVideoEl();
  if (!bar || !video || !isFinite(video.duration)) return;
  const barRect = bar.getBoundingClientRect();
  if (ev.clientY < barRect.top - 12 || ev.clientY > barRect.bottom + 12) return;
  ev.preventDefault();
  ev.stopImmediatePropagation();
  dragging = true;
  startS = xToSeconds(bar, ev.clientX, video.duration);
  endS = startS;
  const ov = ensureOverlay(bar);
  ov.style.left = `${secondsToPct(startS, video.duration)}%`;
  ov.style.width = `0%`;
  ensureTooltip();
  updateTooltip(ev.clientX, ev.clientY);
}

function onMouseMove(ev: MouseEvent) {
  if (!dragging) return;
  const bar = getProgressBarEl();
  const video = getVideoEl();
  if (!bar || !video) return;
  endS = xToSeconds(bar, ev.clientX, video.duration);
  const s = Math.min(startS, endS);
  const e = Math.max(startS, endS);
  const ov = ensureOverlay(bar);
  ov.style.left = `${secondsToPct(s, video.duration)}%`;
  ov.style.width = `${secondsToPct(e, video.duration) - secondsToPct(s, video.duration)}%`;
  updateTooltip(ev.clientX, ev.clientY);
}

function onMouseUp(_ev: MouseEvent) {
  if (!dragging) return;
  dragging = false;
  const s = Math.min(startS, endS);
  const e = Math.max(startS, endS);
  clearUi();
  if (e - s < 2) {
    toast("Range too short (need at least 2 seconds). Ignored.");
    return;
  }
  const ctx = readYouTubeContext();
  if (!ctx) {
    toast("Not a YouTube watch page.");
    return;
  }
  chrome.runtime.sendMessage({
    type: "clip.range_selected",
    url: ctx.url,
    start_s: s,
    end_s: e,
    video_title: ctx.videoTitle,
    channel_name: ctx.channelName,
  });
  toast(`Range captured: ${mmss(s)} → ${mmss(e)}. Open the extension popup to extract.`);
}

function onKeyDown(ev: KeyboardEvent) {
  if (ev.key === "Escape" && dragging) {
    dragging = false;
    clearUi();
  }
}

function onBlur() {
  if (dragging) {
    dragging = false;
    clearUi();
  }
}

function start() {
  injectStyles();
  document.addEventListener("mousedown", onMouseDown, true);
  document.addEventListener("mousemove", onMouseMove, true);
  document.addEventListener("mouseup", onMouseUp, true);
  document.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("blur", onBlur, true);
}

start();
