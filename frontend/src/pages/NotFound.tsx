/** Not found. Rendered for an authenticated user hitting an unknown route. */

import { Link, useLocation } from "react-router-dom";
import { PageHeader } from "../components/layout/PageHeader";
import { EmptyState } from "../components/feedback/States";

export default function NotFound() {
  const location = useLocation();

  return (
    <>
      <PageHeader
        title="Page not found"
        description="That address does not match anything in Humisense."
      />
      <EmptyState
        title={`No page at ${location.pathname}`}
        description="Check the address, or use the command palette to find what you were looking for."
        action={undefined}
      />
      <p style={{ marginTop: 14 }}>
        <Link to="/today" className="hs-btn hs-btn-secondary hs-btn-sm">
          Back to Today
        </Link>
      </p>
    </>
  );
}
