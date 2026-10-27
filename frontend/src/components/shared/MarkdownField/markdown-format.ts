/**
 * ARCH-L1-001 ReactFrontend — markdown formatting primitives (#1287, Plan C
 * T-C2-8).
 *
 * One pure function owns every marker placement so the toolbar component stays
 * presentational and the editor only has to forward the textarea selection and
 * re-apply the returned offsets. Keeping it pure is what makes the caret
 * contract testable without a DOM.
 *
 * Behaviour per action:
 *
 * - `bold` / `italic` / `code` wrap the selection in their marker and keep the
 *   text selected; an empty selection inserts `****`, `**`, ` `` ` and puts the
 *   caret between the markers so the user can type straight away.
 * - `link` builds `[text](url)`; the `url` placeholder is selected so typing
 *   replaces it. An empty selection builds `[](url)` with the caret between the
 *   brackets (the visible text is what the user types first).
 * - `heading` prefixes the **line the caret is on** with `## ` (a heading is a
 *   block property, so one line — not the whole selection). Clicking it again on
 *   an already `## `-prefixed line removes the marker (toggle).
 * - `bulletList` / `numberedList` prefix **every line of the selected block**
 *   with `- ` / `1. `. When every line in the block already carries the prefix
 *   it is removed again (toggle); otherwise only unprefixed lines get one, so a
 *   mixed block is normalised instead of double-prefixed.
 *
 * The selection is remapped through the same offsets the markers were inserted
 * at, so a multi-line list edit keeps its selection instead of collapsing it to
 * the caret.
 */

export type MarkdownAction =
  | "bold"
  | "italic"
  | "heading"
  | "bulletList"
  | "numberedList"
  | "link"
  | "code";

export interface MarkdownFormatResult {
  value: string;
  selStart: number;
  selEnd: number;
}

/**
 * `[text](url)` is inserted with `url` as a placeholder; it is selected so the
 * next keystroke replaces it.
 */
const LINK_URL_PLACEHOLDER = "url";
const HEADING_PREFIX = "## ";

function clamp(value: string, offset: number): number {
  if (Number.isNaN(offset)) return value.length;
  return Math.min(Math.max(offset, 0), value.length);
}

/** Wrap the selection in `marker`, keeping the text selected. */
function wrapSelection(
  value: string,
  selStart: number,
  selEnd: number,
  marker: string
): MarkdownFormatResult {
  const before = value.slice(0, selStart);
  const selected = value.slice(selStart, selEnd);
  const after = value.slice(selEnd);
  const next = `${before}${marker}${selected}${marker}${after}`;

  if (selStart === selEnd) {
    const caret = selStart + marker.length;
    return { value: next, selStart: caret, selEnd: caret };
  }
  return {
    value: next,
    selStart: selStart + marker.length,
    selEnd: selEnd + marker.length,
  };
}

function applyLink(
  value: string,
  selStart: number,
  selEnd: number
): MarkdownFormatResult {
  const before = value.slice(0, selStart);
  const selected = value.slice(selStart, selEnd);
  const after = value.slice(selEnd);

  if (selStart === selEnd) {
    // `[](url)` — caret between the brackets, ready for the visible text.
    return {
      value: `${before}[](${LINK_URL_PLACEHOLDER})${after}`,
      selStart: selStart + 1,
      selEnd: selStart + 1,
    };
  }

  const next = `${before}[${selected}](${LINK_URL_PLACEHOLDER})${after}`;
  const urlStart = selStart + selected.length + 3; // "[" + "]" + "("
  return {
    value: next,
    selStart: urlStart,
    selEnd: urlStart + LINK_URL_PLACEHOLDER.length,
  };
}

function applyHeading(
  value: string,
  selStart: number,
  selEnd: number
): MarkdownFormatResult {
  const lineStart = value.lastIndexOf("\n", selStart - 1) + 1;
  const lineEndCandidate = value.indexOf("\n", selStart);
  const lineEnd = lineEndCandidate === -1 ? value.length : lineEndCandidate;
  const line = value.slice(lineStart, lineEnd);

  const removing = line.startsWith(HEADING_PREFIX);
  const prefix = removing ? "" : HEADING_PREFIX;
  const body = removing ? line.slice(HEADING_PREFIX.length) : line;
  const next = `${value.slice(0, lineStart)}${prefix}${body}${value.slice(lineEnd)}`;

  const delta = removing ? -HEADING_PREFIX.length : HEADING_PREFIX.length;
  const map = (offset: number): number => {
    if (offset < lineStart) return offset;
    if (removing) {
      // A caret inside the removed marker collapses to the line start.
      return Math.max(lineStart, offset + delta);
    }
    return offset + delta;
  };

  return { value: next, selStart: map(selStart), selEnd: map(selEnd) };
}

function applyListPrefix(
  value: string,
  selStart: number,
  selEnd: number,
  prefix: string
): MarkdownFormatResult {
  const blockStart = value.lastIndexOf("\n", selStart - 1) + 1;
  const blockEndCandidate = value.indexOf("\n", selEnd);
  const blockEnd = blockEndCandidate === -1 ? value.length : blockEndCandidate;
  const block = value.slice(blockStart, blockEnd);
  const lines = block.split("\n");

  const allPrefixed = lines.every((line) => line.startsWith(prefix));
  const deltas = lines.map((line) => {
    if (allPrefixed) return -prefix.length;
    return line.startsWith(prefix) ? 0 : prefix.length;
  });

  const lineStarts: number[] = [];
  let cursor = 0;
  for (const line of lines) {
    lineStarts.push(cursor);
    cursor += line.length + 1; // + the "\n" this line consumes
  }

  const nextBlock = lines
    .map((line) => {
      if (allPrefixed) return line.slice(prefix.length);
      return line.startsWith(prefix) ? line : `${prefix}${line}`;
    })
    .join("\n");

  const mapOffset = (offset: number): number => {
    let mapped = offset;
    lines.forEach((_line, index) => {
      const lineStart = lineStarts[index];
      const delta = deltas[index];
      if (delta > 0) {
        if (offset >= lineStart) mapped += delta;
        return;
      }
      if (delta < 0) {
        const removedEnd = lineStart - delta; // lineStart + |delta|
        if (offset >= removedEnd) {
          mapped += delta;
        } else if (offset > lineStart) {
          mapped = lineStart;
        }
      }
    });
    return mapped;
  };

  return {
    value: `${value.slice(0, blockStart)}${nextBlock}${value.slice(blockEnd)}`,
    selStart: blockStart + mapOffset(selStart - blockStart),
    selEnd: blockStart + mapOffset(selEnd - blockStart),
  };
}

/**
 * Apply one formatting action at the given selection.
 *
 * Pure: the same input always yields the same `{value, selStart, selEnd}` and
 * nothing outside the returned object changes.
 */
export function applyMarkdownFormat(
  value: string,
  selStart: number,
  selEnd: number,
  action: MarkdownAction
): MarkdownFormatResult {
  const rawStart = clamp(value, selStart);
  const rawEnd = clamp(value, selEnd);
  const start = Math.min(rawStart, rawEnd);
  const end = Math.max(rawStart, rawEnd);

  switch (action) {
    case "bold":
      return wrapSelection(value, start, end, "**");
    case "italic":
      return wrapSelection(value, start, end, "*");
    case "code":
      return wrapSelection(value, start, end, "`");
    case "link":
      return applyLink(value, start, end);
    case "heading":
      return applyHeading(value, start, end);
    case "bulletList":
      return applyListPrefix(value, start, end, "- ");
    case "numberedList":
      return applyListPrefix(value, start, end, "1. ");
  }
}
