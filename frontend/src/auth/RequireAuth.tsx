/**
 * Route guard.
 *
 * Every integration screen sits behind this.  It routes on the session state
 * rather than on `isAuthenticated`, so a user whose token the backend refuses
 * never reaches a screen that would fail to load its data.
 */

import type { ReactNode } from "react";
import { useAuth } from "./AuthProvider";
import Unconfigured from "../pages/Unconfigured";
import Login from "../pages/Login";
import NoMembership from "../pages/NoMembership";
import Unavailable from "../pages/Unavailable";
import { Loading } from "../components/ui";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { state, error, configProblems } = useAuth();

  switch (state) {
    case "unconfigured":
      return <Unconfigured problems={configProblems} />;
    case "initializing":
      return (
        <div className="page">
          <Loading rows={4} />
        </div>
      );
    case "anonymous":
      return <Login />;
    case "signing_in":
      return (
        <div className="page">
          <Loading rows={3} />
        </div>
      );
    case "unauthorized":
      return <Login message={error ?? undefined} />;
    case "no_membership":
      return <NoMembership />;
    case "unavailable":
      return <Unavailable message={error ?? undefined} />;
    case "ready":
      return <>{children}</>;
  }
}
