#!/usr/bin/env python3
"""
Transcript compression engine for large meeting recordings.
Scores speech blocks for substantive content and progressively filters
to meet a target character count while preserving maximum signal.

Usage:
  python clean_transcript.py --input FILE --output FILE [--target CHARS] [--source-type TYPE]

Source types: notion, plaud, zoom, teams, generic (or auto)
Default target: 75000 characters

Tested: 258k char Notion recording → 73k chars (3.7:1 compression, 154/1027 blocks kept)
"""

import argparse
import re
from pathlib import Path

# ============================================================================
# CONFIGURATION — Edit these to tune for your domain
# ============================================================================

# Substantive content terms. Each match scores +3.
SUBSTANTIVE_TERMS = {
    # Banking / finance
    'product', 'interest', 'rate', 'balance', 'account', 'deposit', 'term',
    'loan', 'credit', 'debit', 'withdrawal', 'penalty', 'grace', 'maturity',
    'rollover', 'dormant', 'inactive', 'escheat', 'collateral', 'escrow',
    'ledger', 'gl ', 'cd', 'treasury', 'kyc', 'kyb', 'aml', 'fraud',
    'sanction', 'withhold', 'tax', 'tier', 'matrix', 'float', 'check', 'fee',
    'regcc', 'pci', 'pan', 'tokeniz',
    # Technology / architecture
    'api', 'endpoint', 'rest', 'swagger', 'openapi', 'microservice',
    'kubernetes', 'k8s', 'docker', 'container', 'openshift',
    'azure', 'aws', 'gcp', 'cloud', 'saas', 'on-prem', 'on prem',
    'deploy', 'release', 'cicd', 'pipeline', 'version', 'zero downtime',
    'event', 'kafka', 'websocket', 'stream', 'cdc', 'batch', 'real-time',
    'schema', 'extension', 'business rule', 'typescript', 'extensib',
    'tenant', 'isolation', 'vpc', 'multi-az', 'multi az',
    'disaster', 'recovery', 'rto', 'rpo', 'bcp', 'availability',
    'security', 'okta', 'saml', 'oauth', 'mtls', 'jwt', 'token',
    'crowdstrike', 'wiz', 'hashicorp', 'vault', 'certificate',
    'encrypt', 'ssl', 'tls', 'idempoten', 'acid',
    'archive', 'archival', 'retention', 'purge',
    'extract', 'etl', 'report', 'monitor', 'datadog', 'observab',
    'scale', 'performance', 'benchmark', 'volume',
    'sql', 'postgres', 'redis', 'flutter', 'dart', 'c#', 'go ',
    'webhook', 'integration', 'architecture', 'infrastructure',
    # Business / deal
    'question', 'answer', 'require', 'spec', 'scope', 'proposal',
    'timeline', 'schedule', 'demo', 'present', 'vendor', 'evaluat',
    'implementation', 'migration', 'conversion', 'contract', 'commercial',
    'budget', 'decision', 'stakeholder', 'sponsor',
    'workflow', 'bpm', 'orchestrat', 'onboarding', 'servicing',
    'statement', 'communication', 'notification',
    'functional', 'non-functional', 'nfr',
    'bian', 'iso', 'regulatory', 'compliance', 'audit',
    # Savana / Fiserv / Finxact ecosystem
    'savana', 'finxact', 'fiserv', 'interact', 'signature', 'finxact.io',
}

# Low-value content terms. Each match scores -5.
LOW_VALUE_TERMS = {
    'hear me', 'hear us', 'mic', 'microphone', 'audio issue',
    'screen share', 'laptop', 'logged out', 'permission to share',
    'hdmi', 'connectivity issue',
    'lunch', 'coffee', 'restroom', 'break time',
    'good morning', 'good afternoon', 'good evening',
    'thank you for joining', 'thanks everyone', 'thanks for your time',
    'mobile phone', 'silent', 'mute yourself',
    'next slide', 'previous slide', 'can you go back',
    'raise your hand', 'speak over each other',
}

# Garbled audio. Blocks containing these are discarded (score -10).
GARBAGE_PATTERNS = [
    'this is the app. this is the app',
    'perfectly informative',
    'finish my story with a beat',
    'i can use my electricity',
    'the unique itself actually needs',
]

# Transcription error corrections. 'common' applies to all source types.
CORRECTIONS = {
    'common': {
        'Savannah': 'Savana', 'Pfizer': 'Fiserv', 'PyServe': 'Fiserv',
        'FinZag': 'Finxact', 'FinZact': 'Finxact', 'Finzact': 'Finxact',
        'FinSec': 'Finxact', 'FinSac': 'Finxact',
        'Enteract': 'Interact', 'ICPS': 'ICBS',
    },
    'notion': {'chainsaw': 'Savana'},
    'plaud': {},
    'zoom': {},
    'teams': {},
    'generic': {},
}

# Filler words/phrases stripped inline.
FILLER_PATTERNS = [
    r'\byou know,?\s*', r'\bI mean,?\s*', r'\bkind of\s+', r'\bsort of\s+',
    r'\ba little bit\s*', r'\bif you will,?\s*', r'\bat the end of the day,?\s*',
    r'\bso to speak,?\s*', r'\bper se,?\s*', r'\band things like that\b',
    r'\band stuff like that\b', r'\band so forth\b',
    r'\b(?:essentially|basically|actually|really|quite|fairly|pretty much|probably|potentially)\s+',
    r'\b100%\.\s*100%', r'Does that make sense\?\s*', r'if that makes sense\.?\s*',
    r'That makes sense\.?\s*', r'Makes sense\.?\s*',
]

# ============================================================================
# SOURCE DETECTION
# ============================================================================

def detect_source_type(text):
    """Auto-detect transcript source from content patterns."""
    if 'WEBVTT' in text[:200]:
        return 'zoom'
    if re.search(r'Speaker \d+.*\d{2}:\d{2}:\d{2}', text[:2000]):
        return 'plaud'
    if text.startswith('# ') and 'Transcript' in text[:5000]:
        return 'notion'
    return 'generic'

# ============================================================================
# SPLITTING — Separate notes from raw transcript by source type
# ============================================================================

def split_notion(text):
    """Split Notion export into notes section and raw transcript."""
    lines = text.split('\n')
    raw_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i > 50 and len(stripped) > 100 and not stripped.startswith(('#', '-', '*', '|', '>')):
            if any(w in stripped.lower() for w in ['so ', 'okay', 'yeah', 'thank', 'hello', 'morning', 'welcome']):
                raw_start = i
                break
    if raw_start is None:
        for i, line in enumerate(lines):
            if line.strip() == 'Transcript':
                for j in range(i + 1, min(i + 50, len(lines))):
                    if len(lines[j].strip()) > 100:
                        raw_start = j
                        break
                break
    if raw_start is None:
        raw_start = len(lines) // 4
    return '\n'.join(lines[:raw_start]), '\n'.join(lines[raw_start:])


def split_plaud(text):
    """Plaud exports are all transcript — no notes section."""
    return '', text


def split_vtt(text):
    """Strip VTT formatting, return as plain text blocks."""
    lines = text.split('\n')
    blocks = []
    current = []
    for line in lines:
        stripped = line.strip()
        if stripped == 'WEBVTT' or re.match(r'^\d+$', stripped):
            continue
        if re.match(r'\d{2}:\d{2}:\d{2}\.\d{3}\s*-->', stripped):
            continue
        if stripped:
            current.append(stripped)
        elif current:
            blocks.append(' '.join(current))
            current = []
    if current:
        blocks.append(' '.join(current))
    return '', '\n\n'.join(blocks)


def split_generic(text):
    """Treat entire file as transcript."""
    return '', text

# ============================================================================
# SCORING — Rate each speech block for substantive content
# ============================================================================

def score_block(block):
    """Score a speech block. Higher = more substantive."""
    lower = block.lower()

    if any(g in lower for g in GARBAGE_PATTERNS):
        return -10

    score = 0
    for term in SUBSTANTIVE_TERMS:
        if term in lower:
            score += 3
    for term in LOW_VALUE_TERMS:
        if term in lower:
            score -= 5

    if len(block) > 400: score += 2
    if len(block) > 800: score += 3
    if '?' in block: score += 2
    if len(block) < 60: score -= 3

    return score

# ============================================================================
# CLEANING — Fix errors and strip filler
# ============================================================================

def apply_corrections(text, source_type):
    for wrong, right in CORRECTIONS['common'].items():
        text = text.replace(wrong, right)
    for wrong, right in CORRECTIONS.get(source_type, {}).items():
        text = text.replace(wrong, right)
    return text


def apply_filler_removal(text):
    for pattern in FILLER_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)
    return text

# ============================================================================
# COMPRESSION — Progressive threshold filtering
# ============================================================================

def compress(raw, target, source_type):
    """Compress raw transcript to target chars using block scoring."""
    blocks = [b.strip() for b in raw.split('\n\n') if len(b.strip()) > 20]
    if not blocks:
        return raw, {'total_blocks': 0, 'kept_blocks': 0, 'threshold': 0}

    # Score, correct, and clean each block
    processed = []
    for i, block in enumerate(blocks):
        score = score_block(block)
        cleaned = apply_corrections(block, source_type)
        cleaned = apply_filler_removal(cleaned)
        if len(cleaned.strip()) > 20:
            processed.append((score, i, cleaned.strip()))

    # Raise threshold until output fits
    for threshold in range(0, 30):
        kept = [(i, b) for s, i, b in processed if s >= threshold]
        kept.sort(key=lambda x: x[0])
        total = sum(len(b) for _, b in kept) + len(kept) * 2
        if total <= target:
            result = '\n\n'.join(b for _, b in kept)
            return result, {
                'total_blocks': len(blocks),
                'kept_blocks': len(kept),
                'threshold': threshold,
                'original_chars': len(raw),
                'compressed_chars': len(result),
                'ratio': f"{len(raw)/max(len(result),1):.1f}:1",
            }

    # Even at max threshold, return what we have
    kept = [(i, b) for s, i, b in processed if s >= 29]
    kept.sort(key=lambda x: x[0])
    result = '\n\n'.join(b for _, b in kept)
    return result, {
        'total_blocks': len(blocks), 'kept_blocks': len(kept), 'threshold': 29,
        'original_chars': len(raw), 'compressed_chars': len(result),
        'ratio': f"{len(raw)/max(len(result),1):.1f}:1",
    }

# ============================================================================
# MAIN PIPELINE
# ============================================================================

SPLITTERS = {
    'notion': split_notion,
    'plaud': split_plaud,
    'zoom': split_vtt,
    'teams': split_vtt,
    'generic': split_generic,
}

def process(input_path, output_path, target, source_type):
    text = Path(input_path).read_text(encoding='utf-8', errors='replace')
    original_size = len(text)

    if source_type == 'auto':
        source_type = detect_source_type(text)

    print(f"Source: {source_type}")
    print(f"Original: {original_size:,} chars")

    splitter = SPLITTERS.get(source_type, split_generic)
    notes, raw = splitter(text)

    print(f"Notes: {len(notes):,} chars")
    print(f"Transcript: {len(raw):,} chars")

    transcript_target = target - len(notes) - 200

    if len(raw) <= transcript_target:
        print("Fits within target — corrections only")
        cleaned = apply_filler_removal(apply_corrections(raw, source_type))
        stats = {'compressed': True, 'original_chars': len(raw),
                 'compressed_chars': len(cleaned), 'ratio': 'N/A (no compression)'}
    else:
        print(f"Compressing to ~{transcript_target:,} chars...")
        cleaned, stats = compress(raw, transcript_target, source_type)

    # Assemble output
    parts = []
    if notes.strip():
        parts.append(notes.strip())
    parts.append('---\n\n## Cleaned Transcript\n')
    parts.append(cleaned)
    result = '\n\n'.join(parts)

    Path(output_path).write_text(result, encoding='utf-8')

    print(f"\n--- Stats ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  Final: {len(result):,} chars")
    print(f"  Target: {target:,}")
    print(f"  Status: {'PASS' if len(result) <= target else 'OVER'}")
    print(f"  Output: {output_path}")


def main():
    p = argparse.ArgumentParser(description='Compress large meeting transcripts')
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--target', type=int, default=75000)
    p.add_argument('--source-type', default='auto',
                   choices=['auto', 'notion', 'plaud', 'zoom', 'teams', 'generic'])
    args = p.parse_args()
    process(args.input, args.output, args.target, args.source_type)


if __name__ == '__main__':
    main()
