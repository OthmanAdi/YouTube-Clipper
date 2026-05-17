// Background service worker: bridges popup <-> local daemon.

import { postClip, openEventsWs } from "../lib/api.js";

interface PendingSelection {
  url: string;
  start_s: number;
  end_s: number;
  video_title: string | null;
  channel_name: string | null;
}

let pending: PendingSelection | null = null;
let currentJobId: string | null = null;
let currentWs: WebSocket | null = null;
let lastEvent: any = null;

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      if (msg?.type === "clip.range_selected") {
        pending = msg as PendingSelection;
        try {
          await chrome.action.openPopup();
        } catch {
          /* The popup can't be opened programmatically on every chrome version.
             That's OK — the user can click the extension icon. */
        }
        sendResponse({ ok: true });
        return;
      }

      if (msg?.type === "popup.get_state") {
        sendResponse({ pending, currentJobId, lastEvent });
        return;
      }

      if (msg?.type === "popup.extract") {
        if (!pending) {
          sendResponse({ ok: false, error: "no pending selection" });
          return;
        }
        const summarizer = msg.summarizer === "ollama" ? "ollama" : "azure";
        const resp = await postClip({
          url: pending.url,
          start_s: pending.start_s,
          end_s: pending.end_s,
          summarizer,
          video_title: pending.video_title,
          channel_name: pending.channel_name,
        });
        currentJobId = resp.job_id;
        lastEvent = { type: "enqueued", job_id: resp.job_id };
        if (currentWs) {
          try {
            currentWs.close();
          } catch {
            /* ignore */
          }
        }
        currentWs = openEventsWs(resp.job_id, (m: any) => {
          lastEvent = m;
          chrome.runtime.sendMessage({ type: "popup.event", event: m }).catch(() => {});
          if (m?.type === "done" || m?.type === "failed") {
            try {
              currentWs?.close();
            } catch {
              /* ignore */
            }
            currentWs = null;
          }
        });
        sendResponse({ ok: true, job_id: resp.job_id });
        return;
      }

      if (msg?.type === "popup.cancel") {
        pending = null;
        sendResponse({ ok: true });
        return;
      }

      if (msg?.type === "popup.reset") {
        pending = null;
        currentJobId = null;
        lastEvent = null;
        sendResponse({ ok: true });
        return;
      }

      sendResponse({ ok: false, error: `unknown message: ${msg?.type}` });
    } catch (e: any) {
      sendResponse({ ok: false, error: String(e?.message ?? e) });
    }
  })();
  return true; // async response channel
});
