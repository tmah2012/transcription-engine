---
name: transcription-engine
description: >
  Automatically triggered when any transcript or meeting recording content exceeds
  80,000 characters. Detects oversized transcripts from: Notion meeting recording pages
  (fetched via URL where page content >80k), uploaded transcript files (.md, .txt, .vtt)
  over 80k characters, or Plaud.ai/Zoom/Teams transcript exports over 80k. Also triggered
  explicitly by @transcript prefix or phrases like "process this call", "clean this
  transcript", "summarize this meeting recording". Compresses noisy auto-transcriptions
  to fit within context limits while preserving substantive content. Produces structured
  meeting summaries using type-specific templates (demo, discovery, internal, general).
  Saves cleaned transcripts to /outputs. Chains with notion-crm-skill for deal updates.
---

# Transcription Engine

Compress large meeting transcripts (150k–300k+ chars) to under 80k. Generate structured
summaries by meeting type. Save cleaned output for user reference.

## Auto-Trigger

Activate when ANY of these conditions are met:
- Notion page fetch returns >80k characters
- Uploaded file (.md, .txt, .vtt) exceeds 80k characters
- User says @transcript, "process this call", "summarize this recording"

If content ≤80k chars, do NOT invoke this skill.

## Workflow

### Step 1: Source Detection

Check source type and size:

| Source | Detection | Size check |
|--------|-----------|------------|
| Notion URL | notion.so link fetched via `notion-fetch` | Char count of returned markdown |
| Uploaded file | .md/.txt/.vtt in `/mnt/user-data/uploads/` | `wc -c` on file |
| Plaud.ai | Uploaded .txt with speaker labels + timestamps | `wc -c` |
| Zoom/Teams | .vtt with `WEBVTT` header or `[HH:MM:SS]` format | `wc -c` |

**Notion URL and >80k** → Prompt user to export and upload:

> "This Notion page is [X]k characters — too large for me to process in-place.
> Can you export it? In Notion: ••• → Export → Markdown & CSV, then upload the
> .md file here. I'll compress and summarize it automatically."

**Uploaded file >80k** → Proceed to Step 2 automatically.

### Step 2: Compress

Run the bundled script:

```bash
python [skill_path]/scripts/clean_transcript.py \
  --input "[source_file]" \
  --output "/home/claude/cleaned_transcript.md" \
  --target 75000 \
  --source-type auto
```

The script: separates notes from raw transcript → scores each speech block for
substantive content → progressively raises threshold until output fits target →
fixes transcription errors → strips filler and garbled audio.

**After compression**: Copy cleaned file to `/mnt/user-data/outputs/` and report:
- Original size → compressed size (ratio)
- Blocks kept / total blocks
- Score threshold used

**If script fails**: Fall back manually — read file in chunks via `view` tool,
extract paragraphs containing substantive terms, reassemble.

### Step 3: Select Summary Template

Read `references/templates.md` for full structures. Match by meeting type:

| Type | Signals | Template |
|------|---------|----------|
| **Demo** | Product walkthrough, feature demo, vendor eval, technical Q&A | `demo` |
| **Discovery** | Pain points, requirements, budget, timeline, decision makers | `discovery` |
| **Internal** | Team planning, deal review, strategy, assignments | `internal` |
| **General** | None of the above | `general` |

### Step 4: Generate Summary

Write summary using selected template. Key rules:
- Executive-ready — concise, no filler
- Attribute to speakers when identifiable
- Mark unclear audio as `[Audio unclear]` — never guess
- Open items: specify WHO owes WHAT
- Observations section: analytical synthesis, not a list

**Transcription corrections** (also in `scripts/clean_transcript.py` CORRECTIONS dict):

| Wrong | Correct |
|-------|---------|
| Savannah | Savana |
| Pfizer, PyServe | Fiserv |
| FinZag, FinZact, FinSec, FinSac | Finxact |
| Enteract | Interact |
| ICPS | ICBS |

### Step 5: Deliver + Optional CRM Update

**Always do**: Save cleaned transcript to `/mnt/user-data/outputs/`, present summary.

**If @CRM or user requests deal update**:
1. Present summary for review
2. On approval, hand off to notion-crm-skill:
   - Search for deal → update properties (last activity, stage) → post summary as timeline entry
3. Open items from summary become deal-level items (not personal tasks)

**If no CRM request**: Deliver files only.

## Files

- `scripts/clean_transcript.py` — Compression engine. Run with `--help` for options.
- `references/templates.md` — Summary templates by meeting type.
- `references/formats.md` — Source format patterns and per-source cleaning rules.
