import { useCallback } from "react";
import type { ApiClient } from "../api/client";
import { currency, State, useLoad } from "./shared";

export function OverviewView({ api }: { api: ApiClient }) {
  const load = useCallback(() => api.overview(), [api]); const state = useLoad(load);
  return <section><h2>费用总览</h2><State {...state} empty={false}>{state.data && <div className="metrics">
    <div><small>实际费用合计</small><strong>{currency(state.data.totalBenefit)}</strong></div>
    <div><small>活动费用</small><strong>{currency(state.data.activityBenefit)}</strong></div>
    <div><small>优惠券费用</small><strong>{currency(state.data.couponBenefit)}</strong></div>
    <div><small>已释放订单</small><strong>{state.data.releasedOrders} / {state.data.participatingOrders}</strong></div>
  </div>}</State></section>;
}
