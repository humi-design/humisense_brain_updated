/**
 * Shown when the token is valid but the subject holds no membership anywhere.
 *
 * This is deliberately not an error and deliberately not a login loop: signing
 * in again would produce the same result.  The user needs an administrator to
 * add them to an organization.
 */

import { useAuth } from "../auth/AuthProvider";

export default function NoMembership() {
  const { identity, signOut } = useAuth();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>No organization access</h1>
          <p className="muted">
            You signed in successfully, but your account is not a member of any
            organization in Humisense.
          </p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 520 }}>
        {identity && (
          <dl className="kv">
            <dt>Signed in as</dt>
            <dd>{identity.subject}</dd>
          </dl>
        )}
        <p className="muted" style={{ marginTop: 12 }}>
          Ask an administrator to add you to an organization, then sign in again.
        </p>
        <button className="btn btn-primary" onClick={signOut} style={{ marginTop: 14 }}>
          Sign out
        </button>
      </div>
    </div>
  );
}
