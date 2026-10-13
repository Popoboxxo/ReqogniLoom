/**
 * ARCH-L1-001 ReactFrontend — IcdLinkedElements (Presenter).
 *
 * leaf_id: COMP-RF-001 (IcdView)
 * req_id:  REQ-L2-ICD-001 (ICD CRUD), REQ-L2-RF-006 (Traceability-Anzeige),
 *          #1268 (ICD ↔ architecture anchoring)
 *
 * Shows the artifacts linked to an ICD in **both** directions:
 *   - incoming: links whose *target* is the ICD (e.g. an ArchitectureElement or
 *     Requirement that references the interface), and
 *   - outgoing: links whose *source* is the ICD.
 *
 * Data comes from the existing trace-link surface
 * (`GET /tracelinks/?workspace_id=&artifact_id=`), which returns upstream +
 * downstream rows for one artifact and enriches both endpoints with
 * title/type. The queried id is the ICD's entity id; the API echoes it on the
 * ICD side, so a row is classified by comparing that echo against `icdId`.
 */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { tracelinksApi } from "../../api/tracelinks";
import type { TraceLink, UUID } from "../../types";
import styles from "./IcdLinkedElements.module.css";

export interface IcdLinkedElementsProps {
  icdId: UUID;
  workspaceId: UUID;
}

interface Counterpart {
  id: UUID;
  title?: string;
  type?: string;
  linkType: string;
}

/** Resolve the *other* end of a link relative to the queried ICD id. */
function counterpart(link: TraceLink, icdId: UUID): Counterpart {
  if (link.target_id === icdId) {
    return {
      id: link.source_id,
      title: link.source_title,
      type: link.source_type,
      linkType: link.link_type,
    };
  }
  return {
    id: link.target_id,
    title: link.target_title,
    type: link.target_type,
    linkType: link.link_type,
  };
}

function shortId(id: string): string {
  return `${id.slice(0, 8)}…`;
}

export function IcdLinkedElements({
  icdId,
  workspaceId,
}: IcdLinkedElementsProps): JSX.Element {
  const { t } = useTranslation();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["icds", "links", icdId],
    queryFn: () => tracelinksApi.listForArtifact(workspaceId, icdId),
    enabled: !!icdId && !!workspaceId,
  });

  const links = data?.results ?? [];
  // A link can echo the ICD on either side; classify by the counterpart.
  const incoming = links
    .filter((l) => l.target_id === icdId)
    .map((l) => counterpart(l, icdId));
  const outgoing = links
    .filter((l) => l.source_id === icdId && l.target_id !== icdId)
    .map((l) => counterpart(l, icdId));

  const renderList = (items: Counterpart[], testId: string): JSX.Element => {
    if (items.length === 0) {
      return (
        <p data-testid={`${testId}-empty`} className={styles.empty}>
          {t("icds.linkedElements.none")}
        </p>
      );
    }
    return (
      <ul data-testid={testId} className={styles.list}>
        {items.map((item, idx) => (
          <li
            key={`${item.id}-${item.linkType}-${idx}`}
            data-testid={`${testId}-item-${item.id}`}
            className={styles.item}
          >
            <span className={styles.linkType}>{item.linkType}</span>
            <span className={styles.title}>
              {item.title || shortId(item.id)}
            </span>
            {item.type && <span className={styles.type}>{item.type}</span>}
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div
      data-testid="icd-linked-elements"
      className={styles.section}
    >
      <h3 className={styles.heading}>
        {t("icds.linkedElements.title")}
      </h3>
      {isLoading ? (
        <p data-testid="icd-linked-elements-loading" className={styles.state}>
          {t("loading")}
        </p>
      ) : isError ? (
        <p
          role="alert"
          data-testid="icd-linked-elements-error"
          className={styles.state}
        >
          {t("icds.linkedElements.error")}
        </p>
      ) : (
        <>
          <h4 className={styles.subheading}>
            {t("icds.linkedElements.incoming")}
          </h4>
          {renderList(incoming, "icd-linked-incoming")}
          <h4 className={styles.subheading}>
            {t("icds.linkedElements.outgoing")}
          </h4>
          {renderList(outgoing, "icd-linked-outgoing")}
        </>
      )}
    </div>
  );
}
