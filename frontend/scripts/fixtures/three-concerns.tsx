/**
 * Three-concerns fixture for `analyze-component-hotspots.mjs`.
 *
 * Three responsibilities that share no identifier:
 *   1. data loading (`users` + its effect),
 *   2. dialog state (`dialogOpen` + open/close callbacks),
 *   3. timer toast (`toast` + its effect).
 *
 * The analysis must report exactly three clusters.
 */

import { useCallback, useEffect, useState } from "react";

type Toast = { text: string } | null;

export default function MixedPanel(): JSX.Element {
  const [users, setUsers] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchUsers().then((rows) => {
      if (!cancelled) setUsers(rows);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const [dialogOpen, setDialogOpen] = useState(false);
  const openDialog = useCallback(() => setDialogOpen(true), []);
  const closeDialog = useCallback(() => setDialogOpen(false), []);

  const [toast, setToast] = useState<Toast>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setToast({ text: "saved" }), 2000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <section>
      <button type="button" onClick={openDialog}>
        {users.length} users
      </button>
      <button type="button" onClick={closeDialog}>
        close
      </button>
      {dialogOpen && <dialog open>…</dialog>}
      {toast && <p>{toast.text}</p>}
    </section>
  );
}
