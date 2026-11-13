"""Deterministic Markdown rendering for document projections (Issue #1374 S3).

Pure functions only: no ORM access, no clock, no environment. The service
resolves the inputs and this module turns them into bytes. Determinism is the
contract — two runs over the same logical content must be byte-identical, or a
repository diff becomes noise (concept §7.3).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: Kind -> repository folder. Kept as a literal table so a new kind is a
#: deliberate decision, not an accidental ``docs/<kind>/`` folder.
_KIND_FOLDER: dict[str, str] = {
    "Spec": "docs/superpowers/specs",
    "Plan": "docs/superpowers/plans",
    "AuditReport": "docs/audit",
    "Review": "docs/reviews",
    "Concept": "docs/concepts",
    "Conclusion": "docs/conclusions",
    "Guide": "docs/guides",
}

_MAX_SLUG = 80


@dataclass(frozen=True)
class ProjectedContent:
    """The rendered body (without the generated header) and its hash."""

    content: str
    sha256: str
    warnings: tuple[str, ...]


def slugify(text: str) -> str:
    """ASCII, lowercase, dash-separated, at most 80 characters.

    Non-ASCII characters are transliterated (``ä`` -> ``a``); anything that is
    not a letter/digit becomes a single dash. The result can never contain a
    path separator or ``..``.
    """
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    ascii_text = ascii_text[:_MAX_SLUG].strip("-")
    return ascii_text or "document"


def _confine(path: str) -> str:
    """Make *path* a relative, traversal-free file path."""
    segments = [seg for seg in (path or "").replace("\\", "/").split("/") if seg]
    safe: list[str] = []
    for segment in segments:
        if segment in (".", ".."):
            continue
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", segment).strip(".")
        if cleaned:
            safe.append(cleaned)
    return "/".join(safe)


def projection_path(document: Any) -> str:
    """Repository path for one document.

    ``source_path`` wins when set (a repo-external document keeps its place).
    Otherwise the path is ``docs/<folder-of-kind>/[<date>-]<slug>.md``.
    """
    source_path = _confine(getattr(document, "source_path", "") or "")
    if source_path:
        return source_path

    folder = _KIND_FOLDER.get(str(getattr(document, "kind", "")), "docs/documents")
    doc_date = getattr(document, "doc_date", None)
    prefix = f"{doc_date.isoformat()}-" if doc_date else ""
    return f"{folder}/{prefix}{slugify(str(getattr(document, 'title', '')))}.md"


def _sorted_edges(edges: Iterable[Any]) -> list[Any]:
    return sorted(
        edges,
        key=lambda edge: (
            str(getattr(edge, "link_type", edge.get("link_type") if isinstance(edge, dict) else "")),
            str(getattr(edge, "target_label", edge.get("target_label") if isinstance(edge, dict) else "")),
        ),
    )


def render_document(
    document: Any,
    *,
    anchors: Sequence[Any] = (),
    edges: Sequence[Any] = (),
    glossary: Mapping[str, str] | None = None,
    state: str = "",
) -> ProjectedContent:
    """Render one document to Markdown plus its content hash.

    Args:
        document: A duck-typed document row (``uid``, ``title``, ``kind``,
            ``description``, ``body``, ``version``).
        anchors: ``InlineAnchor`` rows. A dead target (``target_lifecycle``
            other than ``active``, or ``0``) is rendered as plain text and
            reported in ``warnings``.
        edges: Objects with ``link_type`` and ``target_label``.
        glossary: Term -> definition; rendered as an alphabetical appendix.
        state: Workflow state shown in the header.
    """
    warnings: list[str] = []
    body = str(getattr(document, "body", "") or "").rstrip("\n")
    description = str(getattr(document, "description", "") or "").strip()

    replacement_by_token: dict[str, str] = {}
    for anchor in sorted(
        anchors,
        key=lambda item: (str(getattr(item, "token", "")), str(getattr(item, "id", ""))),
    ):
        lifecycle = getattr(anchor, "target_lifecycle", "active")
        if lifecycle == "active":
            continue
        token = str(getattr(anchor, "token", ""))
        label = str(getattr(anchor, "target_label", "") or token)
        replacement_by_token[token] = f"{label} *(dead reference)*"
        warnings.append(f"dead reference: {token}")

    for token, replacement in replacement_by_token.items():
        body = body.replace(token, replacement)

    sections: list[str] = [f"# {str(getattr(document, 'title', '') or 'Untitled')}"]
    if description:
        sections.append(description)
    if body:
        sections.append(body)

    glossary = glossary or {}
    if glossary:
        lines = ["## Glossary", ""]
        for term in sorted(glossary):
            lines.append(f"- **{term}** — {glossary[term]}")
        sections.append("\n".join(lines))

    sorted_edges = _sorted_edges(edges)
    if sorted_edges:
        lines = ["## References", ""]
        for edge in sorted_edges:
            if isinstance(edge, dict):
                link_type = edge.get("link_type", "")
                label = edge.get("target_label", "")
            else:
                link_type = getattr(edge, "link_type", "")
                label = getattr(edge, "target_label", "")
            lines.append(f"- `{link_type}` → {label}")
        sections.append("\n".join(lines))

    content = "\n\n".join(section for section in sections if section) + "\n"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return ProjectedContent(
        content=content,
        sha256=digest,
        warnings=tuple(warnings),
    )


def with_header(projected: ProjectedContent, *, document: Any, state: str = "") -> str:
    """Prepend the generated header (the hash covers the content without it)."""
    header_lines = [
        "<!-- GENERATED by ReqogniLoom — do not edit.",
        (
            f"     document: {getattr(document, 'uid', '') or '(no uid)'} · "
            f"version {getattr(document, 'version', 0)} · state {state or 'unknown'} "
            f"· hash {projected.sha256}"
        ),
    ]
    if projected.warnings:
        header_lines.append(f"     warnings: {'; '.join(projected.warnings)}")
    header_lines.append(
        f"     regenerate: reqlo project {getattr(document, 'uid', '') or '<uid>'}   "
        "(oder MCP: document.project) -->"
    )
    return "\n".join(header_lines) + "\n\n" + projected.content
