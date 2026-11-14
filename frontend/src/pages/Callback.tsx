/**
 * Landing route for the provider redirect.
 *
 * The OIDC library processes the authorization response itself, so this screen
 * exists to render something honest while that happens and, if the provider
 * returned an error, to say so rather than leave a blank page.
 */

import { useAuth } from "../auth/AuthProvider";
import { Loading, Banner } from "../components/ui";

export default function Callback() {
  const { state, error } = useAuth();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Completing sign-in</h1>
          <p className="muted">
            {state === "unavailable"
              ? "The sign-in could not be completed."
              : "Verifying your session with Humisense."}
          </p>
        </div>
      </div>
      <div className="card" style={{ maxWidth: 560 }}>
        {error ? <Banner tone="danger">{error}</Banner> : <Loading rows={3} />}
      </div>
    </div>
  );
}
