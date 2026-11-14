/** Sign-in screen. */

import { useAuth } from "../auth/AuthProvider";

export default function Login({ message }: { message?: string }) {
  const { signIn } = useAuth();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Sign in to Humisense</h1>
          <p className="muted">
            Your organization signs you in through its own identity provider.
            Humisense never sees your password.
          </p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 460 }}>
        {message && <div className="banner banner-warning">{message}</div>}
        <p className="muted" style={{ marginTop: message ? 12 : 0 }}>
          You will be redirected to your organization's login page and returned
          here once you have signed in.
        </p>
        <button className="btn btn-primary" onClick={signIn} style={{ marginTop: 14 }}>
          Continue to sign in
        </button>
      </div>
    </div>
  );
}
