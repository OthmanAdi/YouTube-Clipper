// Shared persistent state (chrome.storage.session). Survives MV3 service-worker restarts.
// Survives popup close. Cleared on browser quit. Good fit for ephemeral "today's clips" UX.

// ---------- segment selections (multi-segment selection on the YouTube seekbar) ----------

// 6-color palette for segment overlays. Index 0..5 maps to a CSS class suffix.
// Kept in sync with public/assets/content.css and popup/popup.css.
export const SEGMENT_COLORS = ["rose", "cyan", "amber", "green", "violet", "orange"] as const;
export type SegmentColor = typeof SEGMENT_COLORS[number];
export const MAX_SEGMENTS = SEGMENT_COLORS.length; // 6

export interface SegmentSelection {
  // Stable id (crypto.randomUUID()) — used to address one segment for remove/extract.
  segment_id: string;
  url: string;
  start_s: number;
  end_s: number;
  video_title: string | null;
  channel_name: string | null;
  captured_at: number;
  // Index into SEGMENT_COLORS. Stable for the segment's lifetime.
  color_idx: number;
}

// Back-compat alias for callers that don't care about segment_id/color_idx.
// New code should prefer SegmentSelection directly.
export type PendingSelection = Omit<SegmentSelection, "segment_id" | "color_idx">;

// ---------- jobs ----------

export type JobState = "queued" | "running" | "done" | "failed";

export type DetailLevel = "quick" | "standard" | "deep";

export type Provider = "azure" | "ollama" | "qwen";

export interface JobView {
  job_id: string;
  clip_id: string;
  url: string;
  start_s: number;
  end_s: number;
  summarizer: Provider;
  // Per-clip model. null = config default for the chosen provider.
  model: string | null;
  detail: DetailLevel;
  video_title: string | null;
  channel_name: string | null;
  output_dir_override: string | null;
  created_at: number;
  state: JobState;
  current_stage: string | null;
  stages_done: string[];
  last_log: string;
  note_path: string | null;
  website_path: string | null;
  error_stage: string | null;
  error_message: string | null;
  durations_ms: Record<string, number>;
}

// ---------- ui prefs (chrome.storage.local — persistent across browser restarts) ----------

export interface UiPrefs {
  output_dir_override: string | null;
  // Combined provider+model selector value, e.g. "ollama", "azure:gpt-5-mini", "qwen:qwen3.7-max".
  // Matches the <option value> in popup.html. Default is "ollama" (local, free).
  default_summarizer_model: string;
  default_detail: DetailLevel;
}

const DEFAULT_PREFS: UiPrefs = {
  output_dir_override: null,
  default_summarizer_model: "ollama",
  default_detail: "standard",
};

export async function getPrefs(): Promise<UiPrefs> {
  const got = await chrome.storage.local.get(["ui_prefs"]);
  return { ...DEFAULT_PREFS, ...(got.ui_prefs as Partial<UiPrefs> | undefined) };
}

export async function setPrefs(patch: Partial<UiPrefs>): Promise<UiPrefs> {
  const current = await getPrefs();
  const merged = { ...current, ...patch };
  await chrome.storage.local.set({ ui_prefs: merged });
  return merged;
}

// ---------- session state (chrome.storage.session — ephemeral) ----------

interface StateShape {
  pendingSegments: SegmentSelection[];
  jobs: Record<string, JobView>;
}

const DEFAULT_STATE: StateShape = { pendingSegments: [], jobs: {} };

async function readAll(): Promise<StateShape> {
  const got = await chrome.storage.session.get(["pendingSegments", "jobs"]);
  return {
    pendingSegments: (got.pendingSegments as SegmentSelection[]) ?? [],
    jobs: (got.jobs as Record<string, JobView>) ?? {},
  };
}

// ---------- segment helpers ----------

export async function getSegments(): Promise<SegmentSelection[]> {
  const s = await readAll();
  return s.pendingSegments;
}

/** Append a new segment. Returns the added segment, or null if the cap was reached. */
export async function addSegment(
  partial: Omit<SegmentSelection, "segment_id" | "color_idx">
): Promise<SegmentSelection | null> {
  const existing = await getSegments();
  if (existing.length >= MAX_SEGMENTS) return null;
  const seg: SegmentSelection = {
    ...partial,
    segment_id:
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `seg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    // Color index = current count modulo palette size. Re-uses a color after a removal+add,
    // which is fine: colors are visual cues, not identity (the segment_id is identity).
    color_idx: existing.length % MAX_SEGMENTS,
  };
  await chrome.storage.session.set({ pendingSegments: [...existing, seg] });
  return seg;
}

export async function removeSegment(segmentId: string): Promise<void> {
  const existing = await getSegments();
  const next = existing.filter((s) => s.segment_id !== segmentId);
  await chrome.storage.session.set({ pendingSegments: next });
}

export async function clearSegments(): Promise<void> {
  await chrome.storage.session.set({ pendingSegments: [] });
}

// ---------- back-compat shims (used by older popup code paths) ----------

/** Returns the first pending segment (legacy "single pending" API). */
export async function getPending(): Promise<SegmentSelection | null> {
  const segs = await getSegments();
  return segs[0] ?? null;
}

/** Sets a single pending segment (clears + adds). Pass null to clear all. */
export async function setPending(p: PendingSelection | null): Promise<void> {
  if (p === null) {
    await clearSegments();
    return;
  }
  await clearSegments();
  await addSegment(p);
}

// ---------- jobs ----------

export async function getJobs(): Promise<JobView[]> {
  const s = await readAll();
  return Object.values(s.jobs).sort((a, b) => b.created_at - a.created_at);
}

export async function getJob(jobId: string): Promise<JobView | null> {
  const s = await readAll();
  return s.jobs[jobId] ?? null;
}

export async function upsertJob(job: JobView): Promise<void> {
  const s = await readAll();
  s.jobs[job.job_id] = job;
  await chrome.storage.session.set({ jobs: s.jobs });
}

export async function patchJob(
  jobId: string,
  patch: Partial<JobView>
): Promise<JobView | null> {
  const s = await readAll();
  const existing = s.jobs[jobId];
  if (!existing) return null;
  const merged: JobView = { ...existing, ...patch };
  s.jobs[jobId] = merged;
  await chrome.storage.session.set({ jobs: s.jobs });
  return merged;
}

export async function removeJob(jobId: string): Promise<void> {
  const s = await readAll();
  delete s.jobs[jobId];
  await chrome.storage.session.set({ jobs: s.jobs });
}

export async function clearAll(): Promise<void> {
  await chrome.storage.session.set(DEFAULT_STATE);
}

// ---------- change subscription ----------

// Subscribe to session-state changes. Fires when pendingSegments or jobs change.
// Returns an unsubscribe function.
export function onChange(
  cb: (state: StateShape) => void
): () => void {
  const handler = (
    changes: { [key: string]: chrome.storage.StorageChange },
    area: chrome.storage.AreaName
  ) => {
    if (area !== "session") return;
    if (!("pendingSegments" in changes) && !("jobs" in changes)) return;
    void readAll().then(cb);
  };
  chrome.storage.onChanged.addListener(handler);
  return () => chrome.storage.onChanged.removeListener(handler);
}
