/**
 * Application providers.
 *
 * Order matters: theme is outermost because it affects everything rendered
 * inside, including the sign-in and error screens. Authentication sits inside
 * the router because the OIDC callback needs routing.
 */

import type { ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "../design-system/themes/ThemeProvider";
import { AppAuthProvider } from "../auth/OidcAuthProvider";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <AppAuthProvider>
        <BrowserRouter>{children}</BrowserRouter>
      </AppAuthProvider>
    </ThemeProvider>
  );
}
