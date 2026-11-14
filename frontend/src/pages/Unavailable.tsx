/**
 * Shown when the identity provider or the backend cannot be reached.
 *
 * Retrying is meaningful here, unlike the no-membership case, so this screen
 * offers it.
 */

import { useAuth } from "../auth/AuthProvider";

export default function Unavailable({ message }: { message?: string }) {
  const { refresh, signOut } = useAuth();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Cannot reach the service</h1>
          <p className="muted">
            Humisense could not verify your session. This is usually temporary.
          </p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 560 }}>
        {message && <div className="banner banner-danger">{message}</div>}
        <div className="row" style={{ gap: 10, marginTop: 14 }}>
          <button className="btn btn-primary" onClick={refresh}>
            Try again
          </button>
          <button className="btn btn-ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
