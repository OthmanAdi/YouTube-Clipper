export const DAEMON_BASE = "http://127.0.0.1:7777";
export const DAEMON_WS = "ws://127.0.0.1:7777";

export type Provider = "azure" | "ollama" | "qwen";

export interface ClipRequest {
  url: string;
  start_s: number;
  end_s: number;
  summarizer: Provider;
  video_title?: string | null;
  channel_name?: string | null;
  output_dir?: string | null;
  detail?: "quick" | "standard" | "deep";
  // Per-clip model override. None/omit = use config default for the chosen summarizer.
  model?: string | null;
}

export interface ClipResponse {
  job_id: string;
  clip_id: string;
  job_dir?: string;
}

export async function postClip(req: ClipRequest): Promise<ClipResponse> {
  const resp = await fetch(`${DAEMON_BASE}/clip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`POST /clip ${resp.status}: ${txt.slice(0, 300)}`);
  }
  return (await resp.json()) as ClipResponse;
}

export async function getHealth(): Promise<unknown> {
  const resp = await fetch(`${DAEMON_BASE}/health`);
  if (!resp.ok) throw new Error(`health ${resp.status}`);
  return resp.json();
}

export interface DaemonJobView {
  job_id: string;
  clip_id: string;
  state: string;
  current_stage: string | null;
  stages_done: string[];
  failed_at_stage: string | null;
  error_class: string | null;
  error_message: string | null;
  durations_ms: Record<string, number>;
  summarizer_used: string | null;
  paths: {
    note: string | null;
  };
}

export async function getDaemonJob(jobId: string): Promise<DaemonJobView | null> {
  const resp = await fetch(`${DAEMON_BASE}/jobs/${encodeURIComponent(jobId)}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`GET /jobs/${jobId} ${resp.status}`);
  return (await resp.json()) as DaemonJobView;
}

export async function makeWebsite(jobId: string): Promise<{ path: string }> {
  const resp = await fetch(`${DAEMON_BASE}/clip/${encodeURIComponent(jobId)}/website`, {
    method: "POST",
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`POST /clip/${jobId}/website ${resp.status}: ${txt.slice(0, 300)}`);
  }
  return (await resp.json()) as { path: string };
}

export function openEventsWs(jobId: string, onMessage: (m: any) => void): WebSocket {
  const ws = new WebSocket(`${DAEMON_WS}/events/${encodeURIComponent(jobId)}`);
  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data));
    } catch {
      /* ignore bad frame */
    }
  };
  return ws;
}
