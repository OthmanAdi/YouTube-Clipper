// Background service worker.
// - Owns the WS connections to the daemon (one per active job).
// - Persists all state in chrome.storage.session so the popup is always re-renderable from disk
//   and we survive MV3 service-worker eviction.

import { postClip, openEventsWs, getDaemonJob } from "../lib/api.js";
import {
  type JobView,
  type PendingSelection,
  getPending,
  setPending,
  upsertJob,
  patchJob,
  getJob,
  removeJob,
  getJobs,
} from "../lib/state.js";

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

async function handleRangeSelected(msg: PendingSelection) {
  const p: PendingSelection = {
    url: msg.url,
    start_s: msg.start_s,
    end_s: msg.end_s,
    video_title: msg.video_title ?? null,
    channel_name: msg.channel_name ?? null,
    captured_at: nowMs(),
  };
  await setPending(p);
  await maybeOpenPopup();
}

async function handleExtract(summarizer: "azure" | "ollama"): Promise<{ ok: boolean; job_id?: string; error?: string }> {
  const pending = await getPending();
  if (!pending) return { ok: false, error: "no pending selection" };

  try {
    const resp = await postClip({
      url: pending.url,
      start_s: pending.start_s,
      end_s: pending.end_s,
      summarizer,
      video_title: pending.video_title,
      channel_name: pending.channel_name,
    });
    const job: JobView = {
      job_id: resp.job_id,
      clip_id: resp.clip_id,
      url: pending.url,
      start_s: pending.start_s,
      end_s: pending.end_s,
      summarizer,
      video_title: pending.video_title,
      channel_name: pending.channel_name,
      created_at: nowMs(),
      state: "queued",
      current_stage: null,
      stages_done: [],
      last_log: "queued",
      note_path: null,
      error_stage: null,
      error_message: null,
      durations_ms: {},
    };
    await upsertJob(job);
    await setPending(null);
    await attachWs(job);
    return { ok: true, job_id: resp.job_id };
  } catch (e: any) {
    return { ok: false, error: String(e?.message ?? e) };
  }
}

async function handleDismissPending(): Promise<void> {
  await setPending(null);
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
      if (msg?.type === "clip.range_selected") {
        await handleRangeSelected(msg);
        sendResponse({ ok: true });
        return;
      }
      if (msg?.type === "popup.extract") {
        const summarizer = msg.summarizer === "ollama" ? "ollama" : "azure";
        const r = await handleExtract(summarizer);
        sendResponse(r);
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

// On SW start or after eviction, try to re-attach WSs for any unfinished jobs.
void handleRehydrate();
