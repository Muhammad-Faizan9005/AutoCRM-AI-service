from __future__ import annotations

import re


_EMOJI_RE = re.compile(
    "["
    "\U0001f1e6-\U0001f1ff"
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\u2600-\u27bf"
    "]+",
    flags=re.UNICODE,
)

_SECTION_HEADING_RE = re.compile(
    r"\s*(?:#{1,6}\s*)?(Pipeline Overview|Key Observations|Recommended Actions|Next Steps|Note)\s*:?\s*",
    flags=re.IGNORECASE,
)
_IMPLEMENTATION_DETAIL_RE = re.compile(r"\b(RAG|FAISS|embedding|embeddings|prompt|token|tokens|memory)\b", flags=re.IGNORECASE)


def _clean_line(line: str) -> str:
    cleaned = _EMOJI_RE.sub("", str(line or ""))
    cleaned = re.sub(r"#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\w)\*(?!\s)(.*?)(?<!\s)\*(?!\w)", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"\s*[-=]{3,}\s*", " ", cleaned)
    cleaned = re.sub(r"^\s*(?:[-*]+|\d+[.)])\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.strip(" -*:;")


def _split_summary_candidates(text: str) -> list[str]:
    text = _SECTION_HEADING_RE.sub(lambda match: f"\n{match.group(1)}: ", text)
    text = re.sub(r"\s+(?=\d+[.)]\s+)", "\n", text)
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Split AI blobs that use spaced dashes as pseudo bullets.
        parts = re.split(r"\s+[-\u2013\u2014]\s+(?=[A-Z0-9])", line)
        for part in parts:
            # Split long numbered action chains that survived line splitting.
            subparts = re.split(r"\s+(?=\d+[.)]\s+)", part)
            candidates.extend(item.strip() for item in subparts if item.strip())
    if len(candidates) <= 1:
        candidates = re.split(
            r"\s+(?=(?:Follow up|Deal risk|Task due|Meeting note|Data gap|Review|Confirm|Schedule|Investigate|Update|Capture):)",
            text,
        )
    return [item.strip() for item in candidates if item.strip()]


def format_ai_text(value: object, *, max_length: int | None = None) -> str:
    """Normalize AI text before saving or displaying it in CRM surfaces."""
    text = str(value or "").replace("\\n", "\n")
    text = _SECTION_HEADING_RE.sub("\n", text)
    lines = [_clean_line(line) for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 3].rstrip() + "..."
    return cleaned


def format_daily_summary(value: object) -> str:
    text = str(value or "").replace("\\n", "\n")
    raw_lines = _split_summary_candidates(text)

    skipped_prefixes = (
        "daily crm summary",
        "pipeline overview",
        "key observations",
        "recommended actions",
        "next steps",
        "note:",
        "date:",
        "role:",
        "status:",
    )
    removable_prefixes = ("key observations:", "recommended actions:", "next steps:")
    bullets: list[str] = []
    for line in raw_lines:
        cleaned = _clean_line(line)
        if not cleaned:
            continue
        lower = cleaned.lower()
        if any(lower.startswith(prefix) for prefix in skipped_prefixes):
            continue
        for prefix in removable_prefixes:
            if lower.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip(" -:;")
                lower = cleaned.lower()
                break
        if not cleaned:
            continue
        if _IMPLEMENTATION_DETAIL_RE.search(cleaned):
            continue
        if len(cleaned) > 180:
            cleaned = cleaned[:177].rstrip() + "..."
        bullets.append(cleaned)
        if len(bullets) >= 6:
            break

    if not bullets:
        bullets = ["No meaningful CRM activity was available today. Review open leads, pending tasks, and active deals for updates."]

    return "\n".join(f"- {bullet}" for bullet in bullets[:6])
