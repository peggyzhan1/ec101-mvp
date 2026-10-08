import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OverviewView } from "./OverviewView";

describe("OverviewView", () => {
  it("renders API values and does not expose theoretical fields", async () => {
    render(<OverviewView api={{ overview: vi.fn().mockResolvedValue({ calculationRunIds: [1], activityBenefit: 100, couponBenefit: 20, totalBenefit: 120, releasedActivityBenefit: 70, releasedCouponBenefit: 10, participatingOrders: 3, releasedOrders: 2 }) } as never} />);

    expect(await screen.findByText("¥120")).toBeInTheDocument();
    expect(screen.queryByText(/理论|权益核对|一致性/)).not.toBeInTheDocument();
  });
});
