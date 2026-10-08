import { useCallback } from "react";
import type { ApiClient } from "../api/client";
import { currency, State, useLoad } from "./shared";

export function CouponFeesView({ api }: { api: ApiClient }) {
  const summaries = useLoad(useCallback(() => api.coupons(), [api]));
  const unlinked = useLoad(useCallback(() => api.unlinkedCoupons(), [api]));
  return <section><h2>优惠券费用</h2><State {...summaries} empty={!summaries.data?.items.length}>{summaries.data?.items.map((row, index) => <article className="card" key={`${row.calculationRunId}-${row.couponConfigId}-${index}`}>
    <h3>券配置：{row.couponConfigId ?? "未匹配配置"}</h3>
    <p>总核销 {row.usedCount} / {currency(row.usedAmount)}</p><p>已关联 {row.linkedCount} / {currency(row.linkedAmount)}</p><p>可释放 {row.releasableCount} / {currency(row.releasableAmount)}</p><p>未关联 {row.unlinkedCount} / {currency(row.unlinkedAmount)}</p>
  </article>)}</State>
  <h3>未关联券</h3><p className="warning">未关联订单，不可释放</p><State {...unlinked} empty={!unlinked.data?.items.length}>{unlinked.data?.items.map((row) => <div className="row" key={row.couponRedemptionId}><span>{row.couponNo}</span><span>{row.customerName || row.customerNo || "—"}</span><strong>{currency(row.discountAmount)}</strong></div>)}</State>
  </section>;
}
