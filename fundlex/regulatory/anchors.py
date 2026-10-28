"""Source anchors and article/heading helpers shared by DOCX and PDF parsing."""
from __future__ import annotations

import re
from typing import Iterable

ARTICLE_RE = re.compile(r"第([一二三四五六七八九十百零〇\d]+)条")
CHAPTER_RE = re.compile(r"第([一二三四五六七八九十百零〇\d]+)章")
SECTION_RE = re.compile(r"第([一二三四五六七八九十百零〇\d]+)节")


def article_number(text: str) -> str:
    match = ARTICLE_RE.search(text or "")
    return f"第{match.group(1)}条" if match else ""


def heading_level(text: str, style_level: int = 0) -> int:
    stripped = (text or "").strip()
    if not stripped:
        return 0
    if style_level:
        return max(1, min(6, style_level))
    if CHAPTER_RE.match(stripped):
        return 1
    if SECTION_RE.match(stripped):
        return 2
    if ARTICLE_RE.match(stripped) and len(stripped) <= 40:
        return 3
    return 0


def is_article_heading(text: str) -> bool:
    stripped = (text or "").strip()
    match = re.fullmatch(r"第[一二三四五六七八九十百零〇\d]+条\s*", stripped)
    return bool(match)


def clean_line(text: str) -> str:
    """Remove common PDF artefacts while preserving legal content."""
    value = (text or "").replace("\u00a0", " ").replace("\u3000", " ")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def merge_lines(lines: Iterable[str]) -> str:
    """Join PDF lines into one paragraph without inventing spaces in Chinese."""
    output = ""
    for raw in lines:
        line = clean_line(raw)
        if not line:
            continue
        if not output:
            output = line
            continue
        # A heading or article marker on its own line starts a new block.
        if is_article_heading(line) or CHAPTER_RE.match(line) or SECTION_RE.match(line):
            output += "\n" + line
            continue
        # Latin words need a separating space; CJK lines join directly.
        if re.search(r"[A-Za-z0-9]$", output) and re.match(r"[A-Za-z0-9]", line):
            output += " " + line
        else:
            output += line
    return output.strip()


def split_article_groups(blocks) -> list[dict]:
    """Group blocks by article markers for deterministic requirement coverage.

    Returns ``[{"article": "第一条", "block_ids": [...], "text": "..."}]``.
    Text before the first article is its own group (title/preamble).
    """
    groups: list[dict] = []
    current = {"article": "", "block_ids": [], "text": ""}
    for block in blocks:
        text = (block.text or "").strip()
        if not text:
            continue
        found = article_number(text)
        starts_article = bool(found and (is_article_heading(text) or ARTICLE_RE.match(text)))
        if starts_article and current["block_ids"] and (current["article"] != found or is_article_heading(text)):
            groups.append(current)
            current = {"article": found, "block_ids": [], "text": ""}
        if found and not current["article"]:
            current["article"] = found
        current["block_ids"].append(block.block_id)
        current["text"] = (current["text"] + "\n" + text).strip()
    if current["block_ids"]:
        groups.append(current)
    return groups
