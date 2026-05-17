export interface YouTubeContext {
  url: string;
  videoId: string;
  channelName: string | null;
  videoTitle: string | null;
}

export function readYouTubeContext(): YouTubeContext | null {
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
    videoTitle: titleEl?.textContent?.trim() ?? document.title.replace(/ - YouTube$/, "").trim() ?? null,
    channelName: channelEl?.textContent?.trim() ?? null,
  };
}

export function getVideoEl(): HTMLVideoElement | null {
  return document.querySelector("video.html5-main-video") as HTMLVideoElement | null;
}

export function getProgressBarEl(): HTMLElement | null {
  return document.querySelector(".ytp-progress-bar") as HTMLElement | null;
}
