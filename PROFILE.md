# Session Profile — YouTube-Clipper

## Who is using this

**Ahmad-Othman Adi** — Senior Applied AI Engineer, AI/Python teacher (8,000+ hours), Berlin.

Builds for himself: teaching prep + second-brain. High taste in tooling. Wants exact verbatim, never paraphrase. Wants every clip he hears to become quotable, searchable, reusable.

## Use cases driving the design

1. **Prepping a Morphos / KI Python lecture.** Watching Karpathy / 3Blue1Brown / Sebastian Raschka. Hears a 90-second explanation that's better than his own. Wants it pasted into the lecture markdown with attribution + audio fallback.
2. **Second brain ingest.** Watching a long interview (Lex, Hub Berman). One 2-minute section is gold. Wants it in his Obsidian-style vault as a permanent note.
3. **Repeating quotes in class.** Plays the actual audio clip in class instead of paraphrasing — students hear it from the source.
4. **Language flexibility.** German and English videos both happen. Whisper auto-detects, summary follows transcript language.

## Personality of the tool

- Quiet. Lives in the system tray-less background. Speaks only when spoken to.
- Fast on the happy path. Verbose on failure.
- Logs like an engineer's tool, not a marketer's product.
- Markdown-native everywhere.
- No telemetry. No accounts. No analytics. Local-first.

## Project relationships

- **qmd**: optional later — clip notes become a qmd collection so RAG works across them.
- **OpenMark**: optional later — clips ingested into the knowledge graph.
- **Teaching modules**: clip notes referenced directly from module markdown via relative links.

## Mission session goal

> By end of this brainstorming session: a clean folder, a written + reviewed design spec, and a clear next step (writing-plans) for implementation.
