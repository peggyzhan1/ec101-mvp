import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CouponFeesView } from "./CouponFeesView";

describe("CouponFeesView", () => {
  it("makes unlinked coupons and their non-releasable status explicit", async () => {
    render(<CouponFeesView api={{
      coupons: vi.fn().mockResolvedValue({ items: [{ calculationRunId: 1, couponConfigId: null, usedCount: 3, usedAmount: 45, linkedCount: 2, linkedAmount: 30, releasableCount: 1, releasableAmount: 15, unlinkedCount: 1, unlinkedAmount: 15 }], total: 1 }),
      unlinkedCoupons: vi.fn().mockResolvedValue({ items: [{ couponRedemptionId: 9, couponNo: "C-9", customerNo: "U-1", customerName: "王五", status: "used", discountAmount: 15 }], total: 1 }),
    } as never} />);

    expect(await screen.findByText("未关联订单，不可释放")).toBeInTheDocument();
    expect(screen.getByText("总核销 3 / ¥45")).toBeInTheDocument();
    expect(screen.getByText("已关联 2 / ¥30")).toBeInTheDocument();
    expect(screen.getByText("可释放 1 / ¥15")).toBeInTheDocument();
    expect(screen.getByText("未关联 1 / ¥15")).toBeInTheDocument();
    expect(screen.getByText("C-9")).toBeInTheDocument();
    expect(screen.getByText("¥15")).toBeInTheDocument();
  });
});
