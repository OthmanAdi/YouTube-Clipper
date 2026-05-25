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

// ---------- multi-segment state ----------

// Mirror of the SegmentSelection shape from lib/state.ts (can't import here — MV3 content
// scripts have no module support). Keep field names in lock-step with state.ts.
interface SegmentRecord {
  segment_id: string;
  url: string;
  start_s: number;
  end_s: number;
  video_title: string | null;
  channel_name: string | null;
  captured_at: number;
  color_idx: number;
}

// 6-color palette — matches lib/state.ts SEGMENT_COLORS and content.css.
const SEGMENT_COLORS = ["rose", "cyan", "amber", "green", "violet", "orange"] as const;
const MAX_SEGMENTS = SEGMENT_COLORS.length;

// Live drag state (one at a time — separate from confirmed overlays).
let dragging = false;
let dragStartS = 0;
let dragEndS = 0;
let dragColorIdx = 0; // assigned at drag start = current segments.length % palette

// Confirmed overlays cached from chrome.storage.session.
let confirmed: SegmentRecord[] = [];

// DOM refs.
let dragOverlay: HTMLDivElement | null = null; // the live drag preview
let tooltip: HTMLDivElement | null = null;
// Map segment_id → overlay element so we can patch positions/colors without nuking the DOM.
const confirmedOverlayEls = new Map<string, HTMLDivElement>();

function injectStyles() {
  if (document.getElementById("ytc-styles")) return;
  const link = document.createElement("link");
  link.id = "ytc-styles";
  link.rel = "stylesheet";
  link.href = chrome.runtime.getURL("assets/content.css");
  document.head.appendChild(link);
}

function ensureDragOverlay(bar: HTMLElement): HTMLDivElement {
  if (dragOverlay && dragOverlay.isConnected) return dragOverlay;
  dragOverlay = document.createElement("div");
  dragOverlay.id = "ytc-overlay-drag";
  dragOverlay.classList.add(`ytc-seg-${SEGMENT_COLORS[dragColorIdx]}`);
  bar.appendChild(dragOverlay);
  return dragOverlay;
}

function clearDragOverlay() {
  dragOverlay?.remove();
  dragOverlay = null;
}

function ensureTooltip(): HTMLDivElement {
  if (tooltip && tooltip.isConnected) return tooltip;
  tooltip = document.createElement("div");
  tooltip.id = "ytc-tooltip";
  document.body.appendChild(tooltip);
  return tooltip;
}

function clearTooltip() {
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
  const s = Math.min(dragStartS, dragEndS);
  const e = Math.max(dragStartS, dragEndS);
  const colorName = SEGMENT_COLORS[dragColorIdx];
  tt.textContent = `[${colorName}] ${mmss(s)} → ${mmss(e)}  (${lengthLabel(e - s)})`;
  tt.style.left = `${clientX + 12}px`;
  tt.style.top = `${clientY + 12}px`;
}

// Repaint all confirmed-segment overlays from `confirmed` array.
// Only segments whose URL matches the current page get rendered (so switching videos
// doesn't show stale overlays from another video, even though storage retains them).
function renderConfirmedOverlays() {
  const bar = getProgressBarEl();
  const video = getVideoEl();
  if (!bar || !video || !isFinite(video.duration)) return;

  const ctx = readYouTubeContext();
  const currentUrl = ctx?.url ?? null;

  // Build set of segment IDs that should be visible on this video right now.
  const visibleIds = new Set<string>();
  for (const seg of confirmed) {
    if (currentUrl && seg.url === currentUrl) visibleIds.add(seg.segment_id);
  }

  // Remove overlays whose segment is gone (or now belongs to a different video).
  for (const [id, el] of confirmedOverlayEls.entries()) {
    if (!visibleIds.has(id)) {
      el.remove();
      confirmedOverlayEls.delete(id);
    }
  }

  // Add/update overlays for each visible segment.
  for (const seg of confirmed) {
    if (!visibleIds.has(seg.segment_id)) continue;
    let el = confirmedOverlayEls.get(seg.segment_id);
    if (!el || !el.isConnected) {
      el = document.createElement("div");
      el.className = "ytc-segment-overlay";
      el.dataset.segmentId = seg.segment_id;
      bar.appendChild(el);
      confirmedOverlayEls.set(seg.segment_id, el);
    }
    // Refresh color class (in case palette mapping ever changes).
    el.classList.remove(
      ...SEGMENT_COLORS.map((c) => `ytc-seg-${c}`)
    );
    el.classList.add(`ytc-seg-${SEGMENT_COLORS[seg.color_idx % SEGMENT_COLORS.length]}`);
    // Position.
    const s = Math.min(seg.start_s, seg.end_s);
    const e = Math.max(seg.start_s, seg.end_s);
    el.style.left = `${secondsToPct(s, video.duration)}%`;
    el.style.width = `${secondsToPct(e, video.duration) - secondsToPct(s, video.duration)}%`;
    el.title = `[${SEGMENT_COLORS[seg.color_idx % SEGMENT_COLORS.length]}] ${mmss(s)} → ${mmss(e)} (${lengthLabel(e - s)})`;
  }
}

async function syncConfirmedFromStorage(): Promise<void> {
  try {
    const got = await chrome.storage.session.get(["pendingSegments"]);
    confirmed = ((got.pendingSegments as SegmentRecord[] | undefined) ?? []).slice();
    renderConfirmedOverlays();
  } catch (err) {
    console.warn("[ytc] failed to sync segments from storage:", err);
  }
}

// ---------- drag handlers ----------

function onMouseDown(ev: MouseEvent) {
  if (!ev.altKey) return;
  if (ev.button !== 0) return;

  const target = ev.target as HTMLElement | null;
  let bar = target?.closest(".ytp-progress-bar") as HTMLElement | null;
  if (!bar) {
    bar = getProgressBarEl();
    if (!bar) {
      console.log("[ytc] alt+mousedown but no .ytp-progress-bar found");
      return;
    }
    const r = bar.getBoundingClientRect();
    if (ev.clientY < r.top - 6 || ev.clientY > r.bottom + 6) {
      console.log("[ytc] alt+mousedown outside seekbar band, ignoring");
      return;
    }
  }
  const video = getVideoEl();
  if (!video || !isFinite(video.duration)) {
    console.log("[ytc] alt+mousedown but no video element / duration not ready");
    return;
  }

  // Cap reached? Show toast and bail before painting an overlay we'll never persist.
  if (confirmed.length >= MAX_SEGMENTS) {
    toast(
      `Max ${MAX_SEGMENTS} segments reached. Remove one in the extension popup first.`
    );
    return;
  }

  ev.preventDefault();
  ev.stopImmediatePropagation();
  dragging = true;
  // Pre-assign the color the new segment will use — matches the SW's color_idx assignment
  // (segments.length % MAX_SEGMENTS). This keeps the live drag preview the same color the
  // confirmed overlay will land in.
  dragColorIdx = confirmed.length % MAX_SEGMENTS;
  dragStartS = xToSeconds(bar, ev.clientX, video.duration);
  dragEndS = dragStartS;
  const ov = ensureDragOverlay(bar);
  ov.style.left = `${secondsToPct(dragStartS, video.duration)}%`;
  ov.style.width = `0%`;
  ensureTooltip();
  updateTooltip(ev.clientX, ev.clientY);
  console.log("[ytc] drag start at", dragStartS, "color", SEGMENT_COLORS[dragColorIdx]);
}

function onMouseMove(ev: MouseEvent) {
  if (!dragging) return;
  const bar = getProgressBarEl();
  const video = getVideoEl();
  if (!bar || !video) return;
  dragEndS = xToSeconds(bar, ev.clientX, video.duration);
  const s = Math.min(dragStartS, dragEndS);
  const e = Math.max(dragStartS, dragEndS);
  const ov = ensureDragOverlay(bar);
  ov.style.left = `${secondsToPct(s, video.duration)}%`;
  ov.style.width = `${secondsToPct(e, video.duration) - secondsToPct(s, video.duration)}%`;
  updateTooltip(ev.clientX, ev.clientY);
}

function onMouseUp(_ev: MouseEvent) {
  if (!dragging) return;
  dragging = false;
  const s = Math.min(dragStartS, dragEndS);
  const e = Math.max(dragStartS, dragEndS);
  clearDragOverlay();
  clearTooltip();
  if (e - s < 2) {
    toast("Range too short (need at least 2 seconds). Ignored.");
    return;
  }
  const ctx = readYouTubeContext();
  if (!ctx) {
    toast("Not a YouTube watch page.");
    return;
  }
  try {
    if (!chrome?.runtime?.id) {
      toast(
        "Extension was reloaded. Refresh this YouTube tab (F5) so the new version can take over."
      );
      return;
    }
    chrome.runtime.sendMessage(
      {
        type: "clip.segment_added",
        url: ctx.url,
        start_s: s,
        end_s: e,
        video_title: ctx.videoTitle,
        channel_name: ctx.channelName,
      },
      (resp: any) => {
        const err = chrome.runtime.lastError;
        if (err) {
          console.warn("[ytc] sendMessage error:", err.message);
          toast(
            "Couldn't reach the extension. Refresh this YouTube tab (F5) and try again."
          );
          return;
        }
        if (resp?.ok === false && resp?.full) {
          toast(`Max ${resp.max ?? MAX_SEGMENTS} segments. Remove one in the popup first.`);
          return;
        }
        // Success: SW persisted the segment; the storage listener will repaint overlays.
      }
    );
    toast(
      `Segment captured: ${mmss(s)} → ${mmss(e)}. Alt+drag again for more, or open the popup.`
    );
  } catch (err) {
    console.warn("[ytc] sendMessage threw:", err);
    toast(
      "Extension was reloaded. Refresh this YouTube tab (F5) so the new version can take over."
    );
  }
}

function onKeyDown(ev: KeyboardEvent) {
  if (ev.key === "Escape" && dragging) {
    dragging = false;
    clearDragOverlay();
    clearTooltip();
  }
}

function onBlur() {
  if (dragging) {
    dragging = false;
    clearDragOverlay();
    clearTooltip();
  }
}

// Listen for storage changes so popup-side actions (extract, remove, clear) propagate
// to overlays on this page automatically — no tab-id push needed.
function onStorageChanged(
  changes: { [key: string]: chrome.storage.StorageChange },
  area: chrome.storage.AreaName
) {
  if (area !== "session") return;
  if (!("pendingSegments" in changes)) return;
  const next = (changes.pendingSegments.newValue as SegmentRecord[] | undefined) ?? [];
  confirmed = next.slice();
  renderConfirmedOverlays();
}

// Re-render overlays when the page mutates (YouTube re-renders the seekbar on SPA nav).
let renderTimer: number | null = null;
function scheduleRender() {
  if (renderTimer !== null) return;
  renderTimer = window.setTimeout(() => {
    renderTimer = null;
    renderConfirmedOverlays();
  }, 200);
}

function start() {
  injectStyles();
  document.addEventListener("mousedown", onMouseDown, true);
  document.addEventListener("mousemove", onMouseMove, true);
  document.addEventListener("mouseup", onMouseUp, true);
  document.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("blur", onBlur, true);

  chrome.storage.onChanged.addListener(onStorageChanged);
  void syncConfirmedFromStorage();

  // YouTube SPA navigation triggers DOM rewrites. Watch for them and re-render overlays.
  const mo = new MutationObserver(scheduleRender);
  mo.observe(document.body, { childList: true, subtree: true });

  // YouTube also fires this on SPA route changes.
  window.addEventListener("yt-navigate-finish", () => {
    scheduleRender();
    void syncConfirmedFromStorage();
  });

  console.log(
    "[ytc] content script loaded — Alt+drag on the seekbar to mark segments (up to",
    MAX_SEGMENTS,
    "with different colors)"
  );
}

start();
