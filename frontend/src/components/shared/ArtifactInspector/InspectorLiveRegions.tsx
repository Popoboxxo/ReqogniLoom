/**
 * ArtifactInspector — the two live regions and their plumbing (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-093 (accessibility baseline), REQ-L0-062
 *
 * Spec §5.3: the inspector has **exactly two** live regions, both at the end
 * of the surface — one polite (`aria-live="polite"`), one assertive
 * (`role="alert"`). The panels do not own an announcement any more; they
 * report through the announcer context below, and the shell decides what is
 * said.
 *
 * The rule that shapes this module (spec §5.3, S6):
 *
 *  1. exactly one announcement per interaction — a delete says `linkDeleted`,
 *     not `linkDeleted` **and** `linksLoaded`; a retry says `retrySucceeded`,
 *     not `retrySucceeded` **and** `versionLoaded`;
 *  2. a `xxxLoaded` message supersedes the generic `tabChanged` message of the
 *     same task, because the loaded count is the more useful half.
 *
 * (2) is implemented by *deferring* `tabChanged` by one task and cancelling
 * it as soon as a panel reports a load or an error. A tab switch therefore
 * produces one spoken sentence no matter whether the panel answers from cache
 * or from the network.
 *
 * The counter reporter lives here too: the rail needs the same numbers the
 * active tab already loaded, and this is the only channel from a tab to the
 * shell.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { InspectorTabKey } from "./inspectorContract";

export const POLITE_REGION_TEST_ID = "inspector-live";
export const ALERT_REGION_TEST_ID = "inspector-alert";

export interface InspectorAnnouncer {
  /** Polite message; cancels a pending `tabChanged` of the same task. */
  polite: (message: string) => void;
  /** Assertive message. Only errors belong here (spec §5.3 rule 3). */
  alert: (message: string) => void;
  /** Deferred "area changed" message, superseded by a load in the same task. */
  tabChanged: (message: string) => void;
}

export interface InspectorCounts {
  /** Current counter per tab; `undefined` while the tab never loaded. */
  counts: Partial<Record<InspectorTabKey, number>>;
  reportCount: (tab: InspectorTabKey, count: number) => void;
}

const AnnouncerContext = createContext<InspectorAnnouncer | null>(null);
const CountsContext = createContext<InspectorCounts | null>(null);

/** The shell's announcer, or `null` when the panel renders outside a shell. */
export function useInspectorAnnouncer(): InspectorAnnouncer | null {
  return useContext(AnnouncerContext);
}

/** The shell's counter channel, or `null` when the panel renders outside a shell. */
export function useInspectorCounts(): InspectorCounts | null {
  return useContext(CountsContext);
}

interface InspectorAnnounceProviderProps {
  children: ReactNode;
}

/**
 * Provides the announcer + counter channel to the shell body and renders the
 * two live regions **after** its children, i.e. at the end of the inspector
 * surface (spec §5.3). Mount it inside the `<aside>`, wrap the shell body.
 */
export function InspectorAnnounceProvider({
  children,
}: InspectorAnnounceProviderProps): JSX.Element {
  const [politeText, setPoliteText] = useState("");
  const [alertText, setAlertText] = useState("");
  const [counts, setCounts] = useState<Partial<Record<InspectorTabKey, number>>>({});

  const pendingTabChangeRef = useRef<number | null>(null);

  const clearPending = useCallback((): void => {
    if (pendingTabChangeRef.current !== null) {
      window.clearTimeout(pendingTabChangeRef.current);
      pendingTabChangeRef.current = null;
    }
  }, []);

  const polite = useCallback(
    (message: string): void => {
      clearPending();
      setPoliteText(message);
    },
    [clearPending],
  );

  const alert = useCallback(
    (message: string): void => {
      clearPending();
      setAlertText(message);
    },
    [clearPending],
  );

  const tabChanged = useCallback(
    (message: string): void => {
      clearPending();
      pendingTabChangeRef.current = window.setTimeout(() => {
        pendingTabChangeRef.current = null;
        setPoliteText(message);
        // A stale alert from the previous tab must not read as this tab's
        // state — the regions are shared by all four areas.
        setAlertText("");
      }, 0);
    },
    [clearPending],
  );

  useEffect(() => clearPending, [clearPending]);

  const reportCount = useCallback((tab: InspectorTabKey, count: number): void => {
    setCounts((prev) => (prev[tab] === count ? prev : { ...prev, [tab]: count }));
  }, []);

  const announcer = useMemo<InspectorAnnouncer>(
    () => ({ polite, alert, tabChanged }),
    [polite, alert, tabChanged],
  );
  const countsValue = useMemo<InspectorCounts>(
    () => ({ counts, reportCount }),
    [counts, reportCount],
  );

  return (
    <AnnouncerContext.Provider value={announcer}>
      <CountsContext.Provider value={countsValue}>
        {children}
        <div
          className="visually-hidden"
          aria-live="polite"
          aria-atomic="true"
          data-testid={POLITE_REGION_TEST_ID}
        >
          {politeText}
        </div>
        <div
          className="visually-hidden"
          role="alert"
          aria-atomic="true"
          data-testid={ALERT_REGION_TEST_ID}
        >
          {alertText}
        </div>
      </CountsContext.Provider>
    </AnnouncerContext.Provider>
  );
}
