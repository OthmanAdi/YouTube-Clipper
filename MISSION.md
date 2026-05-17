# YouTube-Clipper — Mission

## North Star

When I hear something good in any YouTube video — a quote, an idea, a teaching moment — I press Ctrl, drag across the seekbar to mark the range, and within seconds I have:

- the exact audio of that range on disk,
- the verbatim transcript of what was said,
- an AI summary plus crisp bullet points,
- all wrapped in a single Obsidian-friendly markdown note I can paste into class material or my second brain.

It must feel **magical**, work **every time**, log **everything** for me when it doesn't.

## Why this exists

- **Teaching prep:** I prepare modules and lectures. I quote things I heard. Right now I rewind, scrub, type, lose the source. Hours wasted per week.
- **Second-brain feed:** I want every good idea I hear ingested into my own knowledge graph (later: qmd / OpenMark).
- **Speed of capture:** the difference between "I'll save this later" and "I have it forever" is 5 seconds vs 5 minutes. This system collapses it.
- **Truth of capture:** YouTube auto-captions are wrong on 30% of videos. I need real verbatim, Whisper-quality.

## Success criteria

1. **Ctrl+drag on any YouTube seekbar produces a complete note.md within 30 seconds for a 2-minute clip.**
2. **Zero copy-paste.** I never type a URL or a timestamp.
3. **Every stage of the pipeline emits structured logs correlated by `job_id`.** When something fails I grep one ID and see the whole story.
4. **The "My Notes" section of every note.md is never overwritten** by re-runs.
5. **Five of six pipeline stages are deterministic.** Only the summarizer is AI. The robustness comes from minimizing the AI surface.
6. **Works offline** via Ollama. Online with Azure Foundry by default.
7. **Recoverable failures.** Failed jobs preserve partial artifacts. I can re-run from any stage.

## Out of scope

- Multi-user / cloud sync.
- Video output (audio only is enough — I quote what I *hear*).
- Browsers other than Chrome (MV3 first).
- Mobile.
- Built-in clip browser UI — the markdown note IS the UI.
- Auto-push to qmd / OpenMark — keep as separate later integration.

## Tools the user already has

- **Azure Foundry** API keys (online summarizer).
- **Ollama** local (offline summarizer, transcript privacy).
- **GPU + CUDA** for faster-whisper large-v3.
- **yt-dlp + ffmpeg** as battle-tested CLI tools.

## Owner

Ahmad-Othman Adi — first user, only user, decides everything.
