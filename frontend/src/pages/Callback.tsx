/**
 * Landing route for the provider redirect.
 *
 * The OIDC library processes the authorization response itself, so this screen
 * exists to render something honest while that happens, then hand the user on.
 *
 * Two things it must do that are easy to get wrong:
 *
 *   1. Leave. Once the session resolves, navigate into the app. A callback
 *      screen that only ever shows a spinner strands the user on a URL that
 *      still carries `?code=...&state=...`; refreshing it would replay a spent
 *      authorization code. The redirect uses `replace` so the code is gone from
 *      history rather than one Back press away.
 *   2. Explain a refusal. "Signed in but not a member of any organization" and
 *      "the backend rejected the token" are different problems with different
 *      fixes, so each terminal state says which one happened.
 */

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { Button, Loading } from "../components/ui";

/** Where a freshly authenticated session lands. */
const POST_SIGN_IN_ROUTE = "/today";

export default function Callback() {
  const { state, error, signIn } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (state === "ready") {
      navigate(POST_SIGN_IN_ROUTE, { replace: true });
    }
  }, [state, navigate]);

  // Already resolved and on the way out; render nothing to avoid a flash.
  if (state === "ready") return null;

  const problem = describeProblem(state, error);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{problem ? "Sign-in could not be completed" : "Completing sign-in"}</h1>
          <p className="muted">
            {problem ? "Humisense could not establish a usable session." : "Verifying your session with Humisense."}
          </p>
        </div>
      </div>
      <div className="card" style={{ maxWidth: 560 }}>
        {problem ? (
          <div className="stack">
            <p style={{ margin: 0 }}>{problem}</p>
            <div className="row">
              <Button variant="primary" onClick={signIn}>
                Try again
              </Button>
            </div>
          </div>
        ) : (
          <Loading rows={3} />
        )}
      </div>
    </div>
  );
}

/**
 * A plain-language explanation for a terminal session state, or `null` while
 * the session is still being resolved.
 */
function describeProblem(
  state: ReturnType<typeof useAuth>["state"],
  error: string | null,
): string | null {
  switch (state) {
    case "no_membership":
      return "Your sign-in succeeded, but this account is not a member of any Humisense organization. Ask an administrator to add you, then try again.";
    case "unauthorized":
      return error ?? "The backend rejected the access token. Sign in again to get a fresh one.";
    case "unavailable":
      return error ?? "Humisense could not reach the authentication service or the API. Check that the service is running, then try again.";
    case "unconfigured":
      return "Authentication is not configured for this deployment.";
    case "anonymous":
      // Reached when the provider returns without issuing a usable token.
      return "The provider did not return a usable session. Try signing in again.";
    default:
      return null;
  }
}
