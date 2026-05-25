// Background service worker.
// - Owns the WS connections to the daemon (one per active job).
// - Persists all state in chrome.storage.session so the popup is always re-renderable from disk
//   and we survive MV3 service-worker eviction.

import { postClip, openEventsWs, getDaemonJob, makeWebsite, type Provider } from "../lib/api.js";
import {
  type JobView,
  type SegmentSelection,
  MAX_SEGMENTS,
  addSegment,
  removeSegment,
  clearSegments,
  getSegments,
  upsertJob,
  patchJob,
  getJob,
  removeJob,
  getJobs,
} from "../lib/state.js";

// Parse the popup's combined "provider:model" select value into separate fields.
// Examples:
//   "ollama"           → { provider: "ollama", model: null }
//   "azure:gpt-5-mini" → { provider: "azure",  model: "gpt-5-mini" }
//   "qwen:qwen3.7-max" → { provider: "qwen",   model: "qwen3.7-max" }
// Model names containing colons or dots are preserved via split-limit-2 (qwen3.7-max).
function parseSummarizerModel(value: string): { provider: Provider; model: string | null } {
  const idx = value.indexOf(":");
  if (idx === -1) {
    // No colon: bare provider, no model override.
    return { provider: value as Provider, model: null };
  }
  const provider = value.slice(0, idx) as Provider;
  const model = value.slice(idx + 1);
  return { provider, model: model.length > 0 ? model : null };
}

// Active WS connections, keyed by job_id. Held in SW memory only — if SW dies we lose them and
// the job will keep running on the daemon side; the popup will just stop receiving live updates
// for it until the user manually reopens the popup (we then attempt re-attach via GET /jobs).
const activeWs = new Map<string, WebSocket>();

// Per-job event queue. WS events arrive faster than chrome.storage round-trips, and patchJob is
// read-modify-write. Without serialization, "done" could be clobbered by a stale "stage_done"
// patch that read the storage before "done" wrote it. This map chains all events for one job
// onto a single Promise so they apply in arrival order.
const applyQueues = new Map<string, Promise<void>>();

function enqueueApply(jobId: string, ev: any): Promise<void> {
  const prev = applyQueues.get(jobId) ?? Promise.resolve();
  const next = prev
    .catch(() => undefined)
    .then(() => applyEventToJob(jobId, ev))
    .catch((err) => {
      console.error("[ytc-sw] applyEventToJob failed:", err);
    });
  applyQueues.set(jobId, next);
  // Best-effort cleanup once this queue drains.
  void next.finally(() => {
    if (applyQueues.get(jobId) === next) applyQueues.delete(jobId);
  });
  return next;
}

function nowMs(): number {
  return Date.now();
}

async function maybeOpenPopup() {
  try {
    await chrome.action.openPopup();
  } catch {
    /* not always allowed; the user can click the toolbar icon */
  }
}

async function attachWs(job: JobView): Promise<void> {
  if (activeWs.has(job.job_id)) return;
  const ws = openEventsWs(job.job_id, (ev: any) => {
    if (!ev || typeof ev !== "object") return;
    // Enqueue rather than await — preserves arrival order and avoids races between
    // closely-spaced stage_done + done events.
    void enqueueApply(job.job_id, ev).then(() => {
      if (ev.type === "done" || ev.type === "failed") {
        try {
          activeWs.get(job.job_id)?.close();
        } catch {
          /* ignore */
        }
        activeWs.delete(job.job_id);
      }
    });
  });
  ws.onclose = () => {
    activeWs.delete(job.job_id);
  };
  ws.onerror = () => {
    // Don't update state on bare WS error; the daemon may still be doing the work.
  };
  activeWs.set(job.job_id, ws);
}

async function applyEventToJob(jobId: string, ev: any): Promise<void> {
  const patch: Partial<JobView> = {};
  if (ev.type === "running" || ev.type === "enqueued") {
    patch.state = ev.type === "enqueued" ? "queued" : "running";
  } else if (ev.type === "stage_start") {
    patch.state = "running";
    patch.current_stage = ev.stage;
    patch.last_log = `${ev.stage}: starting`;
  } else if (ev.type === "stage_done") {
    const existing = await getJob(jobId);
    const stages = new Set(existing?.stages_done ?? []);
    stages.add(ev.stage);
    patch.stages_done = Array.from(stages);
    patch.last_log = `${ev.stage} done in ${ev.duration_ms}ms`;
    patch.durations_ms = {
      ...(existing?.durations_ms ?? {}),
      [ev.stage]: ev.duration_ms,
    };
  } else if (ev.type === "progress") {
    patch.last_log = ev.message || `${ev.stage}…`;
    if (ev.stage) patch.current_stage = ev.stage;
  } else if (ev.type === "done") {
    patch.state = "done";
    patch.current_stage = null;
    patch.note_path = ev.note || null;
    patch.last_log = "done";
  } else if (ev.type === "failed") {
    patch.state = "failed";
    patch.error_stage = ev.stage || null;
    patch.error_message = ev.error_message || ev.error_class || "unknown error";
    patch.last_log = `failed: ${patch.error_message}`;
  } else {
    return;
  }
  await patchJob(jobId, patch);
}

// Content script fires this for each Alt+drag release. We append to the segments array.
// If the user is already at MAX_SEGMENTS, we report the rejection back so the content script
// can show a toast — that lets the seekbar feedback be authoritative without each side
// counting independently.
async function handleSegmentAdded(
  msg: {
    url: string;
    start_s: number;
    end_s: number;
    video_title: string | null;
    channel_name: string | null;
  }
): Promise<{ ok: boolean; full?: boolean; segment_id?: string; color_idx?: number; max?: number }> {
  const added = await addSegment({
    url: msg.url,
    start_s: msg.start_s,
    end_s: msg.end_s,
    video_title: msg.video_title ?? null,
    channel_name: msg.channel_name ?? null,
    captured_at: nowMs(),
  });
  if (added === null) {
    return { ok: false, full: true, max: MAX_SEGMENTS };
  }
  await maybeOpenPopup();
  return { ok: true, segment_id: added.segment_id, color_idx: added.color_idx };
}

// Extract one segment: POST /clip, create a JobView, attach WS, then remove that segment
// from the pendingSegments array so the popup row disappears once a job exists for it.
async function extractOne(
  seg: SegmentSelection,
  summarizerModel: string,
  outputDirOverride: string | null,
  detail: "quick" | "standard" | "deep"
): Promise<{ ok: true; job_id: string } | { ok: false; error: string }> {
  const { provider, model } = parseSummarizerModel(summarizerModel);
  try {
    const resp = await postClip({
      url: seg.url,
      start_s: seg.start_s,
      end_s: seg.end_s,
      summarizer: provider,
      model,
      video_title: seg.video_title,
      channel_name: seg.channel_name,
      output_dir: outputDirOverride || null,
      detail,
    });
    const job: JobView = {
      job_id: resp.job_id,
      clip_id: resp.clip_id,
      url: seg.url,
      start_s: seg.start_s,
      end_s: seg.end_s,
      summarizer: provider,
      model,
      detail,
      video_title: seg.video_title,
      channel_name: seg.channel_name,
      output_dir_override: outputDirOverride,
      created_at: nowMs(),
      state: "queued",
      current_stage: null,
      stages_done: [],
      last_log: "queued",
      note_path: null,
      website_path: null,
      error_stage: null,
      error_message: null,
      durations_ms: {},
    };
    await upsertJob(job);
    await removeSegment(seg.segment_id);
    await attachWs(job);
    return { ok: true, job_id: resp.job_id };
  } catch (e: any) {
    return { ok: false, error: String(e?.message ?? e) };
  }
}

// Extract a single segment (when segmentId is given) or all pending segments (when null).
// For "all", we submit them sequentially so any failure aborts mid-stream and the popup can
// surface a partial result — better than fire-and-forget where one bad clip would silently fail.
async function handleExtract(
  segmentId: string | null,
  summarizerModel: string,
  outputDirOverride: string | null,
  detail: "quick" | "standard" | "deep"
): Promise<{ ok: boolean; job_ids?: string[]; error?: string }> {
  const segments = await getSegments();
  if (segments.length === 0) {
    return { ok: false, error: "no pending segments" };
  }
  const targets = segmentId
    ? segments.filter((s) => s.segment_id === segmentId)
    : segments;
  if (targets.length === 0) {
    return { ok: false, error: `segment ${segmentId} not found` };
  }

  const jobIds: string[] = [];
  for (const seg of targets) {
    const r = await extractOne(seg, summarizerModel, outputDirOverride, detail);
    if (!r.ok) {
      // Partial success: return what we managed to enqueue plus the error.
      return {
        ok: false,
        job_ids: jobIds,
        error: `${jobIds.length}/${targets.length} extracted; failed on next: ${r.error}`,
      };
    }
    jobIds.push(r.job_id);
  }
  return { ok: true, job_ids: jobIds };
}

async function handleMakeWebsite(jobId: string): Promise<{ ok: boolean; path?: string; error?: string }> {
  try {
    const { path } = await makeWebsite(jobId);
    await patchJob(jobId, { website_path: path });
    return { ok: true, path };
  } catch (e: any) {
    return { ok: false, error: String(e?.message ?? e) };
  }
}

async function handleClearDone(): Promise<void> {
  const jobs = await getJobs();
  for (const j of jobs) {
    if (j.state === "done" || j.state === "failed") {
      try {
        activeWs.get(j.job_id)?.close();
      } catch {
        /* ignore */
      }
      activeWs.delete(j.job_id);
      await removeJob(j.job_id);
    }
  }
}

async function handleDismissPending(): Promise<void> {
  // Clears the entire pending-segments array (legacy "Dismiss" / "Clear all").
  await clearSegments();
}

async function handleRemoveSegment(segmentId: string): Promise<void> {
  await removeSegment(segmentId);
}

async function handleDismissJob(jobId: string): Promise<void> {
  try {
    activeWs.get(jobId)?.close();
  } catch {
    /* ignore */
  }
  activeWs.delete(jobId);
  await removeJob(jobId);
}

async function handleRehydrate(): Promise<void> {
  // Two-phase rehydration:
  //   1. For any job our storage thinks is still in flight, ask the daemon for the truth
  //      via GET /jobs/{id}. If the daemon has moved on (done/failed), update storage.
  //   2. For any job still genuinely in flight, re-attach a WS so future events update the UI.
  const jobs = await getJobs();
  for (const job of jobs) {
    if (job.state !== "queued" && job.state !== "running") continue;
    try {
      const truth = await getDaemonJob(job.job_id);
      if (truth) {
        if (truth.state === "done") {
          await patchJob(job.job_id, {
            state: "done",
            current_stage: null,
            stages_done: truth.stages_done ?? job.stages_done,
            durations_ms: truth.durations_ms ?? job.durations_ms,
            note_path: truth.paths?.note ?? null,
            last_log: "done",
          });
          continue;
        }
        if (truth.state === "failed") {
          await patchJob(job.job_id, {
            state: "failed",
            error_stage: truth.failed_at_stage ?? job.current_stage,
            error_message: truth.error_message ?? truth.error_class ?? "unknown error",
            stages_done: truth.stages_done ?? job.stages_done,
            durations_ms: truth.durations_ms ?? job.durations_ms,
            last_log: `failed: ${truth.error_message ?? truth.error_class ?? "unknown"}`,
          });
          continue;
        }
        // Still queued/running on daemon — sync intermediate fields, then re-attach.
        await patchJob(job.job_id, {
          state: truth.state === "queued" ? "queued" : "running",
          current_stage: truth.current_stage,
          stages_done: truth.stages_done ?? job.stages_done,
          durations_ms: truth.durations_ms ?? job.durations_ms,
        });
      }
    } catch (err) {
      console.warn("[ytc-sw] daemon reconcile failed for", job.job_id, err);
    }
    if (!activeWs.has(job.job_id)) {
      await attachWs(job);
    }
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      // New multi-segment message: content script sends one of these per Alt+drag release.
      if (msg?.type === "clip.segment_added") {
        const r = await handleSegmentAdded(msg);
        sendResponse(r);
        return;
      }
      // Legacy single-range message — kept for old content-script bundles in users' browsers
      // while the new build propagates. Aliased onto segment_added.
      if (msg?.type === "clip.range_selected") {
        const r = await handleSegmentAdded(msg);
        sendResponse(r);
        return;
      }
      if (msg?.type === "popup.extract") {
        // msg.summarizer is the combined "provider:model" value from the popup select
        // (e.g. "ollama", "azure:gpt-5-mini", "qwen:qwen3.7-max"). handleExtract splits it.
        // msg.segment_id is the segment to extract; null/undefined = extract all pending.
        const summarizerModel =
          typeof msg.summarizer === "string" && msg.summarizer.length > 0
            ? msg.summarizer
            : "ollama";
        const segmentId =
          typeof msg.segment_id === "string" && msg.segment_id.length > 0
            ? msg.segment_id
            : null;
        const outputDirOverride =
          typeof msg.output_dir === "string" && msg.output_dir.trim().length > 0
            ? msg.output_dir.trim()
            : null;
        const detail =
          msg.detail === "quick" || msg.detail === "deep" ? msg.detail : "standard";
        const r = await handleExtract(segmentId, summarizerModel, outputDirOverride, detail);
        sendResponse(r);
        return;
      }
      if (msg?.type === "popup.remove_segment") {
        await handleRemoveSegment(String(msg.segment_id));
        sendResponse({ ok: true });
        return;
      }
      if (msg?.type === "popup.make_website") {
        const r = await handleMakeWebsite(String(msg.job_id));
        sendResponse(r);
        return;
      }
      if (msg?.type === "popup.clear_done") {
        await handleClearDone();
        sendResponse({ ok: true });
        return;
      }
      if (msg?.type === "popup.dismiss_pending") {
        await handleDismissPending();
        sendResponse({ ok: true });
        return;
      }
      if (msg?.type === "popup.dismiss_job") {
        await handleDismissJob(String(msg.job_id));
        sendResponse({ ok: true });
        return;
      }
      if (msg?.type === "popup.rehydrate") {
        await handleRehydrate();
        sendResponse({ ok: true });
        return;
      }
      sendResponse({ ok: false, error: `unknown message: ${msg?.type}` });
    } catch (e: any) {
      sendResponse({ ok: false, error: String(e?.message ?? e) });
    }
  })();
  return true; // keep channel open for async sendResponse
});

// chrome.storage.session is TRUSTED_CONTEXTS-only by default — content scripts can't read or
// listen for changes on it. Multi-segment overlays need that access (the content script
// re-renders from pendingSegments on every storage change). Setting the access level here,
// from the SW (a trusted context), opens it to content scripts too. Idempotent + cheap; safe
// to call on every SW boot.
try {
  void chrome.storage.session.setAccessLevel({
    accessLevel: "TRUSTED_AND_UNTRUSTED_CONTEXTS",
  });
} catch (err) {
  console.warn("[ytc-sw] setAccessLevel(session) failed:", err);
}

// On SW start or after eviction, try to re-attach WSs for any unfinished jobs.
void handleRehydrate();
