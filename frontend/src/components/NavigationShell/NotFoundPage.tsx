/**
 * 404 page for authenticated routes.
 *
 * Previously every unknown path silently redirected to `/` (the `*` route),
 * which made a mistyped deep-link look like the app had lost the page. This
 * keeps the navigation shell and names the path, with one clear way back.
 */
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageHeader } from "../shared/PageHeader";
import styles from "./NotFoundPage.module.css";

export function NotFoundPage(): JSX.Element {
  const { t } = useTranslation();
  const { pathname } = useLocation();

  return (
    <section data-testid="not-found-page" className={styles.page}>
      <PageHeader
        title={t("notFound.heading")}
        summary={t("notFound.summary")}
      />
      <p className={styles.path}>
        <code>{pathname}</code>
      </p>
      <div className={styles.actions}>
        <Link to="/" className="btn-primary" data-testid="not-found-home">
          {t("notFound.backToDashboard")}
        </Link>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => window.history.back()}
          data-testid="not-found-back"
        >
          {t("actions.back")}
        </button>
      </div>
    </section>
  );
}
