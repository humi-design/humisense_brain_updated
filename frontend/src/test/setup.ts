import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";
import { clearApiAuth } from "../auth/apiAuth";

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
  clearApiAuth();
});

afterEach(() => {
  cleanup();
});
