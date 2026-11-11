/**
 * Cohesive fixture for `analyze-component-hotspots.mjs`.
 *
 * One responsibility: a counter. Every hook declaration is reachable from
 * every other through a shared identifier, so the analysis must report exactly
 * one cluster.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

export default function Counter(): JSX.Element {
  const [count, setCount] = useState(0);
  const [step, setStep] = useState(1);
  const increment = useCallback(
    () => setCount((current) => current + step),
    [step],
  );
  const doubled = useMemo(() => count * 2, [count]);

  useEffect(() => {
    document.title = `count: ${count} / doubled: ${doubled}`;
  }, [count, doubled]);

  return (
    <button type="button" onClick={increment}>
      {count} ({doubled}) +{step}
    </button>
  );
}
