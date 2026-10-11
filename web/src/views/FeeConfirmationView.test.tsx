import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FeeConfirmationView } from "./FeeConfirmationView";

afterEach(cleanup);

describe("FeeConfirmationView", () => {
  it("loads customer-cycle confirmation metrics, reconciliation, and exceptions on demand", async () => {
    const api = {
      confirmationOverview: vi.fn().mockResolvedValue({
        feeCycleCode: "2026-09",
        recipient: { customerCount: 5, expectedAmount: 1500 },
        submitted: { customerCount: 4, expectedAmount: 1300 },
        notSubmitted: { customerCount: 1, expectedAmount: 200 },
        received: { customerCount: 2, expectedAmount: 700 },
        notReceived: { customerCount: 1, expectedAmount: 500 },
        conflict: { customerCount: 1, expectedAmount: 100 },
        outsideListResponseCount: 1,
        unmatchedMapping: { customerCount: 1, expectedAmount: 200 },
        ambiguousMapping: { customerCount: 1, expectedAmount: 300 },
      }),
      confirmationRecipients: vi.fn().mockResolvedValue({
        items: [{
          feeRecipientId: 2, feeCycleCode: "2026-09", sapCustomerCode: "B",
          sapCustomerName: "客户B", expectedAmount: 200, mappingStatus: "unmatched",
          surveyResponseId: null, receivedAnswer: null, hasConflict: false,
          confirmationStatus: "未提交",
        }], total: 1,
      }),
      confirmationExceptions: vi.fn().mockResolvedValue({
        items: [
          { kind: "outside_list", sapCustomerCode: "X", sapCustomerName: "客户X", matchReason: "名单外" },
          { kind: "unmatched_mapping", sapCustomerCode: "B", sapCustomerName: "客户B", matchReason: "未匹配" },
          { kind: "ambiguous_mapping", sapCustomerCode: "C", sapCustomerName: "客户C", matchReason: "多义" },
          { kind: "conflict", sapCustomerCode: "A", sapCustomerName: "客户A", matchReason: "冲突" },
        ], total: 4,
      }),
      uploadRecipients: vi.fn(),
      uploadSurveys: vi.fn(),
    };
    render(<FeeConfirmationView api={api as never} />);

    expect(screen.getByText("本月全部协议费用是否收到")).toBeInTheDocument();
    expect(screen.queryByText(/订单确认|逐项确认/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("费用周期")).toBeInTheDocument();
    expect(screen.getByLabelText("应发名单")).toBeInTheDocument();
    expect(screen.getByLabelText("问卷答卷")).toBeInTheDocument();
    expect(screen.getByLabelText("确认状态")).toBeInTheDocument();
    expect(api.confirmationOverview).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    expect(await screen.findByText("5 / ¥1500.00")).toBeInTheDocument();
    expect(screen.getByText("4 / ¥1300.00")).toBeInTheDocument();
    expect(screen.getByText("1 / ¥200.00")).toBeInTheDocument();
    expect(screen.getByText("2 / ¥700.00")).toBeInTheDocument();
    expect(screen.getByText("1 / ¥500.00")).toBeInTheDocument();
    expect(screen.getByText("1 / ¥100.00")).toBeInTheDocument();
    expect(screen.getAllByText("客户B").length).toBeGreaterThan(0);
    expect(screen.getAllByText("未提交").length).toBeGreaterThan(0);
    expect(screen.getByText("名单外答卷")).toBeInTheDocument();
    expect(screen.getByText("客资未匹配")).toBeInTheDocument();
    expect(screen.getByText("客资多义")).toBeInTheDocument();
    expect(screen.getAllByText("答卷冲突").length).toBeGreaterThan(0);
    expect(screen.queryByText(/手机号/)).not.toBeInTheDocument();
  });

  it("keeps cycle metadata coherent and pages recipient results", async () => {
    const api = {
      confirmationOverview: vi.fn().mockResolvedValue({
        feeCycleCode: "2026-09",
        recipient: { customerCount: 101, expectedAmount: 101 },
        submitted: { customerCount: 0, expectedAmount: 0 },
        notSubmitted: { customerCount: 101, expectedAmount: 101 },
        received: { customerCount: 0, expectedAmount: 0 },
        notReceived: { customerCount: 0, expectedAmount: 0 },
        conflict: { customerCount: 0, expectedAmount: 0 },
        outsideListResponseCount: 0,
        unmatchedMapping: { customerCount: 0, expectedAmount: 0 },
        ambiguousMapping: { customerCount: 0, expectedAmount: 0 },
      }),
      confirmationRecipients: vi.fn()
        .mockResolvedValueOnce({
          items: Array.from({ length: 100 }, (_, index) => ({
            feeRecipientId: index + 1, feeCycleCode: "2026-09", sapCustomerCode: String(index + 1),
            sapCustomerName: `客户${index + 1}`, expectedAmount: 1, mappingStatus: "matched",
            hasConflict: false, confirmationStatus: "未提交",
          })),
          total: 101, limit: 100, offset: 0,
        })
        .mockResolvedValueOnce({
          items: [{
            feeRecipientId: 101, feeCycleCode: "2026-09", sapCustomerCode: "101",
            sapCustomerName: "客户101", expectedAmount: 1, mappingStatus: "matched",
            hasConflict: false, confirmationStatus: "未提交",
          }],
          total: 101, limit: 100, offset: 100,
        }),
      confirmationExceptions: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 }),
      uploadRecipients: vi.fn(), uploadSurveys: vi.fn(),
    };
    render(<FeeConfirmationView api={api as never} />);

    fireEvent.change(screen.getByLabelText("费用周期"), { target: { value: "2026-09" } });
    expect(screen.getByLabelText("周期名称")).toHaveValue("2026-09 协议费用");
    expect(screen.getByLabelText("周期开始")).toHaveValue("2026-09-01");
    expect(screen.getByLabelText("周期结束")).toHaveValue("2026-09-30");
    fireEvent.click(screen.getByRole("button", { name: "查询" }));
    expect(await screen.findByText("1-100 / 101")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页客户" }));

    expect(api.confirmationRecipients).toHaveBeenLastCalledWith("2026-09", undefined, undefined, 100, 100);
    expect(await screen.findByText("101-101 / 101")).toBeInTheDocument();
  });
});
