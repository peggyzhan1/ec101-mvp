import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "./client";

describe("API client", () => {
  it("uses the configured base URL and pagination parameters", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }));
    const client = createApiClient("http://localhost:8000/", fetcher);

    await client.coupons(7, 20, 40);

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/fee-tpm/coupons?calculationRunId=7&limit=20&offset=40",
      undefined,
    );
  });

  it("uploads both files and calculation date", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ importBatchId: 1 }), { status: 201 }));
    const client = createApiClient("", fetcher);
    const standard = new File(["standard"], "standard.xlsx");
    const sources = new File(["sources"], "sources.zip");

    await client.upload(standard, sources, "2026-10-08");

    const [, options] = fetcher.mock.calls[0];
    expect(fetcher.mock.calls[0][0]).toBe("/api/imports");
    expect(options.method).toBe("POST");
    expect(options.body.get("standard")).toBe(standard);
    expect(options.body.get("sources")).toBe(sources);
    expect(options.body.get("calcDate")).toBe("2026-10-08");
  });

  it("surfaces API error messages", async () => {
    const client = createApiClient("", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "接口不存在" }), { status: 404 })));

    await expect(client.overview()).rejects.toThrow("接口不存在");
  });

  it("parses coupon summaries and unlinked coupon details", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ calculationRunId: 1, couponConfigId: null, usedCount: 3, usedAmount: 45, linkedCount: 2, linkedAmount: 30, releasableCount: 1, releasableAmount: 15, unlinkedCount: 1, unlinkedAmount: 15 }], total: 1 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ couponRedemptionId: 9, couponNo: "C-9", customerNo: "U-1", customerName: "王五", status: "used", discountAmount: 15 }], total: 1 }), { status: 200 }));
    const client = createApiClient("", fetcher);

    const summaries = await client.coupons();
    const unlinked = await client.unlinkedCoupons();

    expect(summaries.items[0].unlinkedAmount).toBe(15);
    expect(summaries.items[0].couponConfigId).toBeNull();
    expect(unlinked.items[0]).toMatchObject({ couponNo: "C-9", discountAmount: 15 });
  });
});
