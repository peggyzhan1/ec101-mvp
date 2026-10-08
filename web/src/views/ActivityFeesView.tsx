import { useCallback } from "react";
import type { ApiClient } from "../api/client";
import { currency, State, useLoad } from "./shared";
export function ActivityFeesView({ api }: { api: ApiClient }) { const state = useLoad(useCallback(() => api.activities(), [api])); return <section><h2>活动费用</h2><State {...state} empty={!state.data?.items.length}>{state.data?.items.map((row) => <div className="row" key={`${row.calculationRunId}-${row.activityNo}`}><span>{row.activityNo} {row.activityName}</span><span>实际 {currency(row.actualDiscountTotal)}</span><span>待释放 {currency(row.pendingAmount)}</span></div>)}</State></section>; }
