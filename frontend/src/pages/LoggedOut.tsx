/** Where the provider returns the browser after sign-out. */

import { useAuth } from "../auth/AuthProvider";

export default function LoggedOut() {
  const { signIn } = useAuth();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Signed out</h1>
          <p className="muted">
            Your Humisense session has ended and the stored token has been
            cleared from this tab.
          </p>
        </div>
      </div>
      <div className="card" style={{ maxWidth: 460 }}>
        <button className="btn btn-primary" onClick={signIn}>
          Sign in again
        </button>
      </div>
    </div>
  );
}
