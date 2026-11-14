/**
 * Shown when authentication is not configured at build time.
 *
 * This is a deployment problem, not a user problem, so it names the missing
 * settings rather than offering a button that cannot work.  There is no
 * fallback to an unauthenticated mode: that would be a security hole dressed
 * up as convenience.
 */

export default function Unconfigured({ problems }: { problems: string[] }) {
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Authentication is not configured</h1>
          <p className="muted">
            This deployment cannot sign users in. The following settings are
            required at build time.
          </p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 620 }}>
        <div className="banner banner-danger">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </div>
        <p className="muted" style={{ marginTop: 12 }}>
          See <code>docs/FRONTEND_AUTH.md</code> for the full list of
          environment variables and the local development setup.
        </p>
      </div>
    </div>
  );
}
