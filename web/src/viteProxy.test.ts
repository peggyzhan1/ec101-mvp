// @vitest-environment node
import { describe, expect, it } from "vitest";

import config from "../vite.config";

describe("Vite development proxy", () => {
  it("forwards API and health requests to the local API service", () => {
    const proxy = config.server?.proxy;

    expect(proxy?.["/api"]).toMatchObject({ target: "http://127.0.0.1:8000", changeOrigin: true });
    expect(proxy?.["/health"]).toMatchObject({ target: "http://127.0.0.1:8000", changeOrigin: true });
  });
});
