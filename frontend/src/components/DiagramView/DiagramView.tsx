/**
 * ARCH-L1-001 ReactFrontend — DiagramView (COMP-RF-005) — Container.
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L0-016 (Interaktive Diagramme und Grafiken),
 *          REQ-L2-DS-001 (DiagramService REST API),
 *          REQ-002 (Split-View Layout),
 *          REQ-L1-095 (ArtifactInspector adoption),
 *          REQ-050 (Container/Presenter decomposition)
 *
 * Split-View container (list left, create form / detail right). Data-fetching
 * lives in useDiagramList (TanStack Query); the create form and detail view
 * are the DiagramCreateForm / DiagramDetailView presenters.
 */

import { useCallback, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SplitView } from "../SplitView/SplitView";
import { DiagramCreateForm } from "./DiagramCreateForm";
import { DiagramDetailView } from "./DiagramDetailView";
import { useDiagramList } from "./useDiagramData";
import { formPrimaryButtonStyle } from "./diagram-view-shared";

export default function DiagramView(): JSX.Element {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { items, isLoading, refresh, deleteDiagram } = useDiagramList();
  const [showCreate, setShowCreate] = useState(false);

  const handleDelete = useCallback(
    async (diagramId: string): Promise<void> => {
      if (!window.confirm(t("diagrams.deleteConfirm", "Really delete this diagram?"))) {
        return;
      }
      try {
        await deleteDiagram(diagramId);
        if (diagramId === id) navigate("/diagrams");
      } catch (err) {
        console.error("Failed to delete diagram", err);
      }
    },
    [id, deleteDiagram, navigate, t],
  );

  if (isLoading) {
    return <p role="status">{t("loading", "Loading...")}</p>;
  }

  return (
    <div
      style={{
        height: "100%",
        fontFamily: "var(--font-sans)",
        color: "var(--color-text)",
      }}
    >
      <SplitView
        moduleType="diagrams"
        leftMinWidth={280}
        leftPanel={
          <>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--space-4)",
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: "var(--font-size-lg)",
              fontWeight: 700,
              color: "var(--color-text)",
            }}
          >
            {t("diagrams.title", "Diagrams")} ({items.length})
          </h3>
          <button
            type="button"
            data-testid="create-diagram-btn"
            onClick={() => setShowCreate((v) => !v)}
            style={formPrimaryButtonStyle}
          >
            + {t("actions.new", "New")}
          </button>
        </div>

        {items.length === 0 ? (
          <p
            data-testid="diagrams-empty"
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {t("diagrams.noItems", "No diagrams yet. Create one to get started.")}
          </p>
        ) : (
          <ul
            data-testid="diagrams-list"
            style={{ listStyle: "none", padding: 0, margin: 0 }}
          >
            {items.map((item) => {
              const isSelected = item.id === id && !showCreate;
              return (
                <li
                  key={item.id}
                  data-testid={`diagram-item-${item.id}`}
                  onClick={() => {
                    setShowCreate(false);
                    navigate(`/diagrams/${item.id}`);
                  }}
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    marginBottom: "var(--space-2)",
                    background: isSelected
                      ? "var(--color-surface-raised)"
                      : "var(--color-surface)",
                    borderRadius: "var(--radius-md)",
                    border: isSelected
                      ? "1px solid var(--color-primary)"
                      : "1px solid var(--color-border)",
                    cursor: "pointer",
                    transition: "var(--transition-fast)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "var(--space-3)",
                  }}
                >
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span
                      style={{
                        display: "block",
                        fontWeight: 600,
                        fontSize: "var(--font-size-base)",
                        color: "var(--color-text)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {item.name}
                    </span>
                    <span
                      style={{
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {item.diagram_type}
                      {item.version_count !== undefined
                        ? ` · v${item.version_count}`
                        : ""}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleDelete(item.id);
                    }}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--color-text-muted)",
                      cursor: "pointer",
                      fontSize: "1.1rem",
                      lineHeight: 1,
                      fontFamily: "inherit",
                      flexShrink: 0,
                    }}
                    title={t("diagrams.delete", "Delete")}
                    aria-label={t("diagrams.delete", "Delete")}
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
          </>
        }
        rightPanel={
          showCreate ? (
          <DiagramCreateForm
            onCreated={async (newId) => {
              setShowCreate(false);
              await refresh();
              navigate(`/diagrams/${newId}`);
            }}
            onCancel={() => setShowCreate(false)}
          />
        ) : id ? (
          <DiagramDetailView
            diagramId={id}
            onBack={() => navigate("/diagrams")}
            onChanged={refresh}
          />
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            {t("diagrams.selectDiagram", "Select a diagram from the list")}
          </p>
          )
        }
      />
    </div>
  );
}
