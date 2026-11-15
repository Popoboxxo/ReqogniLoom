/**
 * ARCH-L1-001 ReactFrontend — Document reading view chapters (R4, plan
 * 2026-11-15-document-view-on-document.md).
 *
 * The right half of the reading layout: one `<section>` per chapter of the
 * reading object, the left half being the table of contents. Chapters are
 * rendered through the existing `MarkdownPreview` renderer in its read-only
 * mode — react-markdown escapes raw HTML, so no chapter text is ever injected
 * as markup (`dangerouslySetInnerHTML` is not used anywhere here).
 *
 * Accessibility baseline: the TOC is a labelled `<nav>`, every chapter is a
 * `<section aria-labelledby>` with an `h2`/`h3` (the page already owns the single
 * `h1`), and the anchors come from the backend (`chapter.anchor`), so a deep
 * link survives a reload.
 */

import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";

import { MarkdownPreview } from "../RequirementEditors/MarkdownPreview";
import type { ReadingChapter } from "../../types";
import styles from "./Documents.module.css";

/** Stable DOM id of one chapter section, shared by TOC link and section. */
export function chapterDomId(anchor: string): string {
  return `chapter-${anchor}`;
}

export interface DocumentReadingChaptersProps {
  chapters: ReadingChapter[];
  /** Visible label for chapters that carry no heading (preamble/empty body). */
  documentTitle: string;
  /** Optional content rendered under the table of contents (document fields). */
  metadata?: ReactNode;
}

/** No-op change handler: the read-only renderer never emits a change. */
const ignoreChange = (): void => {};

export function DocumentReadingChapters({
  chapters,
  documentTitle,
  metadata,
}: DocumentReadingChaptersProps): JSX.Element | null {
  const { t } = useTranslation();
  if (chapters.length === 0) return null;

  return (
    <div className={styles.readingLayout}>
      <nav
        className={styles.readingToc}
        aria-label={t("documents.tableOfContents")}
        data-testid="document-reading-toc"
      >
        <p className={styles.sectionLabel}>{t("documents.tableOfContents")}</p>
        <ol className={styles.tocList}>
          {chapters.map((chapter) => (
            <li key={chapter.anchor} className={styles.tocItem}>
              <a
                className={styles.tocLink}
                href={`#${chapterDomId(chapter.anchor)}`}
              >
                {chapter.number && (
                  <span className={styles.tocNumber}>{chapter.number}</span>
                )}
                <span>{chapter.title || documentTitle}</span>
              </a>
            </li>
          ))}
        </ol>
        {metadata}
      </nav>

      <div className={styles.chapters}>
        {chapters.map((chapter) => (
          <ReadingChapterSection
            key={chapter.anchor}
            chapter={chapter}
          />
        ))}
      </div>
    </div>
  );
}

interface ReadingChapterSectionProps {
  chapter: ReadingChapter;
}

function ReadingChapterSection({
  chapter,
}: ReadingChapterSectionProps): JSX.Element {
  const { t } = useTranslation();
  const headingId = `${chapterDomId(chapter.anchor)}-heading`;
  const isPreamble = chapter.level === 0 && chapter.title.length === 0;
  const headingClass = isPreamble
    ? "visually-hidden"
    : chapter.level >= 2
      ? styles.chapterHeadingMinor
      : styles.chapterHeading;

  return (
    <section
      id={chapterDomId(chapter.anchor)}
      className={styles.chapter}
      aria-labelledby={headingId}
      data-testid={`document-reading-chapter-${chapter.anchor}`}
    >
      {chapter.level >= 2 ? (
        <h3 id={headingId} className={headingClass}>
          {chapter.number && (
            <span className={styles.chapterNumber}>{chapter.number}</span>
          )}
          {chapter.title}
        </h3>
      ) : (
        <h2 id={headingId} className={headingClass}>
          {isPreamble ? (
            t("documents.readingPreamble")
          ) : (
            <>
              {chapter.number && (
                <span className={styles.chapterNumber}>{chapter.number}</span>
              )}
              {chapter.title}
            </>
          )}
        </h2>
      )}

      <div className={styles.chapterBody}>
        {chapter.body.trim().length > 0 ? (
          <MarkdownPreview
            value={chapter.body}
            onChange={ignoreChange}
            readOnly
          />
        ) : (
          <p className={styles.chapterEmpty}>{t("documents.bodyEmpty")}</p>
        )}
      </div>
    </section>
  );
}

DocumentReadingChapters.displayName = "DocumentReadingChapters";
