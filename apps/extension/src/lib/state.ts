// Shared persistent state (chrome.storage.session). Survives MV3 service-worker restarts.
// Survives popup close. Cleared on browser quit. Good fit for ephemeral "today's clips" UX.

export interface PendingSelection {
  url: string;
  start_s: number;
  end_s: number;
  video_title: string | null;
  channel_name: string | null;
  captured_at: number;
}

export type JobState = "queued" | "running" | "done" | "failed";

export interface JobView {
  job_id: string;
  clip_id: string;
  url: string;
  start_s: number;
  end_s: number;
  summarizer: "azure" | "ollama";
  video_title: string | null;
  channel_name: string | null;
  created_at: number;
  state: JobState;
  current_stage: string | null;
  stages_done: string[];
  last_log: string;
  note_path: string | null;
  error_stage: string | null;
  error_message: string | null;
  durations_ms: Record<string, number>;
}

interface StateShape {
  pending: PendingSelection | null;
  jobs: Record<string, JobView>;
}

const DEFAULT_STATE: StateShape = { pending: null, jobs: {} };

async function readAll(): Promise<StateShape> {
  const got = await chrome.storage.session.get(["pending", "jobs"]);
  return {
    pending: (got.pending as PendingSelection | null) ?? null,
    jobs: (got.jobs as Record<string, JobView>) ?? {},
  };
}

export async function getPending(): Promise<PendingSelection | null> {
  const s = await readAll();
  return s.pending;
}

export async function setPending(p: PendingSelection | null): Promise<void> {
  await chrome.storage.session.set({ pending: p });
}

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

// Convenience: subscribe to changes. Returns an unsubscribe function.
export function onChange(
  cb: (state: { pending: PendingSelection | null; jobs: Record<string, JobView> }) => void
): () => void {
  const handler = (
    changes: { [key: string]: chrome.storage.StorageChange },
    area: chrome.storage.AreaName
  ) => {
    if (area !== "session") return;
    if (!("pending" in changes) && !("jobs" in changes)) return;
    void readAll().then(cb);
  };
  chrome.storage.onChanged.addListener(handler);
  return () => chrome.storage.onChanged.removeListener(handler);
}
