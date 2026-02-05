# Transcript Format Reference

Source-specific detection patterns and cleaning rules.

---

## Notion Meeting Recordings

**Detection**: Markdown file starting with `# [Title]`. Contains a `Transcript` section
header. Exported filenames include Notion page ID hash.

**Structure**:
```
# [Page Title]
[User handwritten notes — HIGH VALUE, preserve verbatim]
Transcript
[Auto-generated Q&A sections — MEDIUM VALUE]
[Raw speech blocks separated by blank lines — NEEDS CLEANING]
```

**Characteristics**:
- Notes: 1-5k chars. Transcript: 100-300k chars.
- No speaker labels. No inline timestamps.
- Garbled audio produces gibberish fragments.
- Room echo causes repeated phrases.

**Cleaning**: Preserve everything above `Transcript` header. Score and filter speech blocks.

---

## Plaud.ai Exports

**Detection**: .txt file with speaker labels like `Speaker 1:` or named speakers
with `HH:MM:SS` timestamps.

**Structure**:
```
Speaker 1 00:01:23
Speech content here.

Speaker 2 00:01:45
Response content.
```

**Characteristics**:
- Has speaker labels (numbered or named).
- Timestamps per speech turn.
- Cleaner than Notion (dedicated AI transcription).
- May include `[inaudible]` markers.

**Cleaning**: Preserve speaker labels and timestamps. Merge short consecutive turns
by same speaker. Keep `[inaudible]` as-is.

---

## Zoom Auto-Transcripts

**Detection**: .vtt file with `WEBVTT` header and `HH:MM:SS.mmm --> HH:MM:SS.mmm`
timestamps. Or .txt with `[HH:MM:SS] Speaker: text` format.

**Structure (VTT)**:
```
WEBVTT

1
00:00:01.000 --> 00:00:04.500
Speaker Name: Speech content

2
00:00:04.500 --> 00:00:08.200
Another Speaker: More content
```

**Cleaning**: Strip VTT formatting. Merge consecutive same-speaker entries.
Remove `[Music]`, `[Silence]` markers.

---

## Teams Auto-Transcripts

**Detection**: .vtt or .docx. Similar to Zoom VTT format. May include confidence
scores and language tags.

**Cleaning**: Same approach as Zoom.

---

## Generic / Manual Notes

**Detection**: .md or .txt that doesn't match above patterns.

**Cleaning**: Minimal — fix company/product name typos, normalize formatting.
If >80k chars, apply substantive-content scoring.
