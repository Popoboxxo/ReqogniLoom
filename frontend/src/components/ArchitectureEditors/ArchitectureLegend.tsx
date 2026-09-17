/**
 * ARCH-L1-001 ReactFrontend — <ArchitectureLegend>.
 *
 * Explains the visual vocabulary of the architecture view. Added after a
 * live test: the page shows five distinct badge families (status, level,
 * identifier, version, trace spine) and nothing on screen says which of
 * them carries the colour.
 *
 * The one sentence this legend has to get across is the rule of UI concept
 * ch. 8.1: **colour encodes the workflow status and nothing else.** Type,
 * level and version are told apart by text and position (ch. 8.3), which is
 * exactly why they render neutral here and in the page itself.
 *
 * The samples are rendered with the same components the page uses
 * (<StatusBadge>, <LevelBadge>, <ArtifactId>, <VersionBadge>) rather than
 * with copies — a legend that drifts from the thing it describes is worse
 * than none.
 */

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { StatusBadge } from "../shared/StatusBadge";
import { LevelBadge } from "../shared/LevelBadge";
import { ArtifactId } from "../shared/ArtifactId";
import { VersionBadge } from "../shared/VersionBadge";
import type { BadgeVariant } from "../../utils/statusBadge";

interface LegendSectionProps {
  title: string;
  hint?: string;
  children: ReactNode;
}

function LegendSection({ title, hint, children }: LegendSectionProps): JSX.Element {
  return (
    <section style={{ marginBottom: "var(--space-5)" }}>
      <h3
        style={{
          margin: "0 0 var(--space-2)",
          fontSize: "var(--font-size-sm)",
          fontWeight: "var(--weight-semibold)",
          letterSpacing: "var(--tracking-wide)",
          textTransform: "uppercase",
          color: "var(--color-text-muted)",
        }}
      >
        {title}
      </h3>
      {hint && (
        <p
          style={{
            margin: "0 0 var(--space-3)",
            fontSize: "var(--font-size-sm)",
            lineHeight: "var(--leading-normal)",
            color: "var(--color-text-muted)",
          }}
        >
          {hint}
        </p>
      )}
      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(96px, max-content) 1fr",
          gap: "var(--space-2) var(--space-4)",
          margin: 0,
          alignItems: "baseline",
        }}
      >
        {children}
      </dl>
    </section>
  );
}

interface LegendRowProps {
  sample: ReactNode;
  meaning: string;
  testId?: string;
}

function LegendRow({ sample, meaning, testId }: LegendRowProps): JSX.Element {
  return (
    <>
      <dt style={{ margin: 0 }} data-testid={testId}>
        {sample}
      </dt>
      <dd
        style={{
          margin: 0,
          fontSize: "var(--font-size-sm)",
          lineHeight: "var(--leading-normal)",
          color: "var(--color-text)",
        }}
      >
        {meaning}
      </dd>
    </>
  );
}

/** The five semantic status variants of UI concept ch. 8.2, in order. */
const STATUS_SAMPLES: ReadonlyArray<{
  variant: BadgeVariant;
  labelKey: string;
  labelDefault: string;
  meaningKey: string;
  meaningDefault: string;
}> = [
  {
    variant: "neutral",
    labelKey: "archLegend.statusDraft",
    labelDefault: "Entwurf",
    meaningKey: "archLegend.statusDraftMeaning",
    meaningDefault: "In Arbeit, noch nicht geprüft.",
  },
  {
    variant: "info",
    labelKey: "archLegend.statusReview",
    labelDefault: "In Prüfung",
    meaningKey: "archLegend.statusReviewMeaning",
    meaningDefault: "Eingereicht, wartet auf Freigabe.",
  },
  {
    variant: "success",
    labelKey: "archLegend.statusApproved",
    labelDefault: "Freigegeben",
    meaningKey: "archLegend.statusApprovedMeaning",
    meaningDefault: "Verbindlich und baseline-fähig.",
  },
  {
    variant: "warning",
    labelKey: "archLegend.statusOutdated",
    labelDefault: "Veraltet",
    meaningKey: "archLegend.statusOutdatedMeaning",
    meaningDefault: "Ersetzt oder zurückgezogen, noch nachvollziehbar.",
  },
  {
    variant: "danger",
    labelKey: "archLegend.statusRejected",
    labelDefault: "Abgelehnt",
    meaningKey: "archLegend.statusRejectedMeaning",
    meaningDefault: "Geprüft und verworfen.",
  },
];

export interface ArchitectureLegendProps {
  testId?: string;
}

export function ArchitectureLegend({
  testId = "arch-legend",
}: ArchitectureLegendProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div data-testid={testId}>
      <p
        style={{
          margin: "0 0 var(--space-5)",
          fontSize: "var(--font-size-sm)",
          lineHeight: "var(--leading-normal)",
          color: "var(--color-text)",
        }}
      >
        {t(
          "archLegend.intro",
          "Farbe steht auf dieser Seite ausschließlich für den Status. Artefakttyp, Ebene und Version werden über Text und Position unterschieden — sie bleiben bewusst neutral.",
        )}
      </p>

      <LegendSection
        title={t("archLegend.statusTitle", "Status (farbig)")}
        hint={t(
          "archLegend.statusHint",
          "Der Status wird im Kopf des Elements gesetzt und ist die einzige farbcodierte Information.",
        )}
      >
        {STATUS_SAMPLES.map((sample) => (
          <LegendRow
            key={sample.variant}
            testId={`${testId}-status-${sample.variant}`}
            sample={
              <StatusBadge
                status={t(sample.labelKey, sample.labelDefault)}
                badgeVariant={sample.variant}
                testId={`${testId}-status-badge-${sample.variant}`}
              />
            }
            meaning={t(sample.meaningKey, sample.meaningDefault)}
          />
        ))}
      </LegendSection>

      <LegendSection
        title={t("archLegend.lifecycleTitle", "Lebenszyklus des Elements")}
        hint={t(
          "archLegend.lifecycleHint",
          "Unabhängig vom Freigabestatus. Der Filter über der Liste greift auf dieses Feld zu; gelöschte Elemente werden gar nicht angezeigt.",
        )}
      >
        <LegendRow
          testId={`${testId}-lifecycle-active`}
          sample={<strong>{t("arch.lifecycleStatus.active", "Aktiv")}</strong>}
          meaning={t(
            "archLegend.lifecycleActive",
            "Gültiger Teil der aktuellen Architektur.",
          )}
        />
        <LegendRow
          testId={`${testId}-lifecycle-outdated`}
          sample={<strong>{t("arch.lifecycleStatus.outdated", "Veraltet")}</strong>}
          meaning={t(
            "archLegend.lifecycleOutdated",
            "Noch vorhanden, aber überholt — für Traceability weiter sichtbar.",
          )}
        />
        <LegendRow
          testId={`${testId}-lifecycle-deprecated`}
          sample={
            <strong>{t("arch.lifecycleStatus.deprecated", "Abgekündigt")}</strong>
          }
          meaning={t(
            "archLegend.lifecycleDeprecated",
            "Wird nicht mehr verwendet, bleibt für bestehende Verknüpfungen erhalten.",
          )}
        />
      </LegendSection>

      <LegendSection
        title={t("archLegend.levelTitle", "Ebene")}
        hint={t(
          "archLegend.levelHint",
          "Die Ebene ist die tatsächliche Tiefe im Architekturbaum, keine feste Liste — sie wächst mit der Zerlegung. Eine Ebene ist kein Status, deshalb ist das Kennzeichen im Kopf neutral. Im Navigationsbaum links ist dieselbe Marke zusätzlich nach Tiefe eingefärbt; diese Farbe ist eine Altdarstellung und bedeutet keinen Status.",
        )}
      >
        <LegendRow
          testId={`${testId}-level-0`}
          sample={<LevelBadge level={0} testId={`${testId}-level-badge-0`} />}
          meaning={t("archLegend.level0", "Wurzel — das System selbst.")}
        />
        <LegendRow
          testId={`${testId}-level-1`}
          sample={<LevelBadge level={1} testId={`${testId}-level-badge-1`} />}
          meaning={t("archLegend.level1", "Direkte Zerlegung der Wurzel, z. B. Subsysteme.")}
        />
        <LegendRow
          testId={`${testId}-level-n`}
          sample={
            <LevelBadge label="L n" testId={`${testId}-level-badge-n`} />
          }
          meaning={t(
            "archLegend.levelN",
            "Jede weitere Zerlegungsstufe, z. B. Komponenten und deren Teile.",
          )}
        />
      </LegendSection>

      <LegendSection
        title={t("archLegend.roleVsTypeTitle", "Rolle vs. Element-Typ")}
        hint={t(
          "archLegend.roleVsTypeHint",
          "Zwei unabhängige Felder, die absichtlich nicht synchronisiert werden — ein Root-Element mit der Rolle „System” kann fachlich trotzdem als „component” klassifiziert sein.",
        )}
      >
        <LegendRow
          testId={`${testId}-role-sample`}
          sample={<strong>{t("arch.role", "Rolle")}</strong>}
          meaning={t(
            "archLegend.roleMeaning",
            "Automatisch aus der Baumposition abgeleitet (Wurzel = System, innerer Knoten = Subsystem, Blatt = Komponente). Nicht editierbar, ändert sich beim Verschieben.",
          )}
        />
        <LegendRow
          testId={`${testId}-elementtype-sample`}
          sample={<strong>{t("arch.elementType", "Element-Typ")}</strong>}
          meaning={t(
            "archLegend.elementTypeMeaning",
            "Frei wählbare fachliche Klassifikation, von Hand gepflegt. Kann von der Rolle abweichen und wird nicht automatisch angepasst.",
          )}
        />
      </LegendSection>

      <LegendSection title={t("archLegend.identityTitle", "Kopfzeile des Elements")}>
        <LegendRow
          testId={`${testId}-identifier`}
          sample={
            <ArtifactId
              value="SYS-ARCH-001"
              readOnly
              testId={`${testId}-artifact-id`}
            />
          }
          meaning={t(
            "archLegend.identifier",
            "Bezeichner des Elements, immer in Festbreitenschrift. Ein Klick auf den Bezeichner in der Kopfzeile kopiert ihn.",
          )}
        />
        <LegendRow
          testId={`${testId}-version`}
          sample={<VersionBadge version={2} />}
          meaning={t(
            "archLegend.version",
            "Aktuelle Fassung. Neutral gehalten — eine Version ist kein Status. Ältere Fassungen erscheinen blasser und ohne Rahmen.",
          )}
        />
      </LegendSection>

      <LegendSection
        title={t("archLegend.spineTitle", "Ableitungskette")}
        hint={t(
          "archLegend.spineHint",
          "Der Streifen über dem Formular zeigt, woher das Element abgeleitet ist und was daraus folgt.",
        )}
      >
        <LegendRow
          testId={`${testId}-spine-here`}
          sample={<span aria-hidden="true">◀ {t("traceSpine.here", "hier")}</span>}
          meaning={t(
            "archLegend.spineHere",
            "Die Station, auf der das gerade geöffnete Element sitzt.",
          )}
        />
        <LegendRow
          testId={`${testId}-spine-count`}
          sample={<span aria-hidden="true">·3</span>}
          meaning={t(
            "archLegend.spineCount",
            "Anzahl der Artefakte auf dieser Station beziehungsweise der verknüpften Testfälle. Anklicken öffnet die Liste.",
          )}
        />
        <LegendRow
          testId={`${testId}-spine-empty`}
          sample={<span>{t("traceSpine.noCoverage", "Keine Abdeckung")}</span>}
          meaning={t(
            "archLegend.spineEmpty",
            "Auf dieser Station fehlt eine Verknüpfung — eine Lücke in der Nachverfolgbarkeit.",
          )}
        />
      </LegendSection>
    </div>
  );
}
