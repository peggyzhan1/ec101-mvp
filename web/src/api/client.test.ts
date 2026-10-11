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

  it("uploads a standard workbook without a source archive", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ importBatchId: 1 }), { status: 201 }));
    const client = createApiClient("", fetcher);
    const standard = new File(["standard"], "standard.xlsx");

    await client.upload(standard);

    const [, options] = fetcher.mock.calls[0];
    expect(options.body.get("standard")).toBe(standard);
    expect(options.body.get("sources")).toBeNull();
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

  it("uploads recipient and survey workbooks with the confirmation contract", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ rowCount: 1 }), { status: 201 }));
    const client = createApiClient("", fetcher);
    const recipients = new File(["recipients"], "recipients.xlsx");
    const survey = new File(["survey"], "survey.xlsx");

    await client.uploadRecipients(recipients, {
      feeCycle: "2026-09", cycleName: "2026年9月", periodStart: "2026-09-01",
      periodEnd: "2026-09-30", masterSyncBatchId: 12,
    });
    await client.uploadSurveys(survey, "2026-09");

    expect(fetcher.mock.calls[0][0]).toBe("/api/fee-confirmation/recipients");
    const recipientBody = fetcher.mock.calls[0][1].body as FormData;
    expect(recipientBody.get("recipients")).toBe(recipients);
    expect(recipientBody.get("feeCycle")).toBe("2026-09");
    expect(recipientBody.get("cycleName")).toBe("2026年9月");
    expect(recipientBody.get("periodStart")).toBe("2026-09-01");
    expect(recipientBody.get("periodEnd")).toBe("2026-09-30");
    expect(recipientBody.get("masterSyncBatchId")).toBe("12");
    expect(fetcher.mock.calls[1][0]).toBe("/api/fee-confirmation/surveys");
    const surveyBody = fetcher.mock.calls[1][1].body as FormData;
    expect(surveyBody.get("survey")).toBe(survey);
    expect(surveyBody.get("feeCycle")).toBe("2026-09");
  });

  it("encodes confirmation cycle filters and pagination", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }));
    const client = createApiClient("", fetcher);

    await client.confirmationOverview("2026-09");
    await client.confirmationRecipients("2026-09", "已确认收到", "佳源", 20, 40);
    await client.confirmationExceptions("2026-09", "outside_list", 10, 30);

    expect(fetcher.mock.calls[0][0]).toBe("/api/fee-confirmation/overview?feeCycle=2026-09");
    expect(fetcher.mock.calls[1][0]).toBe(
      "/api/fee-confirmation/recipients?feeCycle=2026-09&status=%E5%B7%B2%E7%A1%AE%E8%AE%A4%E6%94%B6%E5%88%B0&query=%E4%BD%B3%E6%BA%90&limit=20&offset=40",
    );
    expect(fetcher.mock.calls[2][0]).toBe(
      "/api/fee-confirmation/exceptions?feeCycle=2026-09&kind=outside_list&limit=10&offset=30",
    );
  });
});
