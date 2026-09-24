import { describe, expect, it } from "vitest";

import config from "../vite.config";

describe("desktop development API routing", () => {
  it("proxies every explicitly versioned API surface to loopback FastAPI", () => {
    expect(typeof config).toBe("object");
    const proxy = (config as { server?: { proxy?: Record<string, unknown> } }).server
      ?.proxy;

    expect(proxy).toMatchObject({
      "/v1": "http://127.0.0.1:8765",
      "/v7": "http://127.0.0.1:8765",
      "/v8": "http://127.0.0.1:8765",
    });
  });
});
