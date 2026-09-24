import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // The workspace autosaves a debounced checkpoint (400 ms) and restores it on
  // mount: a slow test could otherwise leak its session into the next one.
  window.localStorage.clear();
  window.sessionStorage.clear();
});
