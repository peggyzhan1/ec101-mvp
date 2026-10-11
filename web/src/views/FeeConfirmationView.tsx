import { useState } from "react";
import type { ApiClient } from "../api/client";
import type { ConfirmationException, ConfirmationOverview, ConfirmationRecipient } from "../api/types";


const exceptionLabels: Record<string, string> = {
  outside_list: "名单外答卷",
  conflict: "答卷冲突",
  unmatched_mapping: "客资未匹配",
  ambiguous_mapping: "客资多义",
  invalid_response: "无效答卷",
};

function currentCycle() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function cycleDates(cycle: string) {
  const [year, month] = cycle.split("-").map(Number);
  if (!year || !month) return { start: "", end: "" };
  return {
    start: `${cycle}-01`,
    end: `${year}-${String(month).padStart(2, "0")}-${String(new Date(year, month, 0).getDate()).padStart(2, "0")}`,
  };
}

const metricItems: Array<[keyof ConfirmationOverview, string]> = [
  ["recipient", "应发"], ["submitted", "已提交"], ["notSubmitted", "未提交"],
  ["received", "已确认收到"], ["notReceived", "确认未收到"], ["conflict", "答卷冲突"],
];

export function FeeConfirmationView({ api }: { api: ApiClient }) {
  const initialCycle = currentCycle();
  const initialDates = cycleDates(initialCycle);
  const [feeCycle, setFeeCycle] = useState(initialCycle);
  const [cycleName, setCycleName] = useState(`${initialCycle} 协议费用`);
  const [periodStart, setPeriodStart] = useState(initialDates.start);
  const [periodEnd, setPeriodEnd] = useState(initialDates.end);
  const [masterSyncBatchId, setMasterSyncBatchId] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [recipientFile, setRecipientFile] = useState<File>();
  const [surveyFile, setSurveyFile] = useState<File>();
  const [overview, setOverview] = useState<ConfirmationOverview>();
  const [recipients, setRecipients] = useState<ConfirmationRecipient[]>([]);
  const [exceptions, setExceptions] = useState<ConfirmationException[]>([]);
  const [message, setMessage] = useState("");

  async function refresh() {
    setMessage("加载中…");
    try {
      const [nextOverview, nextRecipients, nextExceptions] = await Promise.all([
        api.confirmationOverview(feeCycle),
        api.confirmationRecipients(feeCycle, status || undefined, search || undefined),
        api.confirmationExceptions(feeCycle),
      ]);
      setOverview(nextOverview); setRecipients(nextRecipients.items); setExceptions(nextExceptions.items);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "查询失败");
    }
  }

  async function uploadRecipients() {
    if (!recipientFile || !masterSyncBatchId) return setMessage("请选择应发名单并填写客资同步批次");
    try {
      const result = await api.uploadRecipients(recipientFile, {
        feeCycle, cycleName, periodStart, periodEnd, masterSyncBatchId: Number(masterSyncBatchId),
      });
      setMessage(`应发名单导入完成：${result.recipientCount} 个客户`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "应发名单导入失败");
    }
  }

  async function uploadSurvey() {
    if (!surveyFile) return setMessage("请选择问卷答卷");
    try {
      const result = await api.uploadSurveys(surveyFile, feeCycle);
      setMessage(`问卷导入完成：${result.rowCount} 份答卷`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "问卷导入失败");
    }
  }

  return <section>
    <h2>客户确认</h2>
    <p>本月全部协议费用是否收到</p>
    <div className="confirmation-controls">
      <label>费用周期<input value={feeCycle} onChange={(event) => setFeeCycle(event.target.value)} placeholder="YYYY-MM" /></label>
      <label>确认状态<select value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">全部</option><option>未提交</option><option>已确认收到</option>
        <option>确认未收到</option><option>答卷冲突</option>
      </select></label>
      <label>客户搜索<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="编号或名称" /></label>
      <button type="button" onClick={refresh}>查询</button>
    </div>
    <div className="confirmation-upload-grid">
      <div className="card">
        <h3>应发名单</h3>
        <label>应发名单<input type="file" accept=".xlsx" onChange={(event) => setRecipientFile(event.target.files?.[0])} /></label>
        <label>周期名称<input value={cycleName} onChange={(event) => setCycleName(event.target.value)} /></label>
        <label>周期开始<input type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} /></label>
        <label>周期结束<input type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} /></label>
        <label>客资同步批次<input inputMode="numeric" value={masterSyncBatchId} onChange={(event) => setMasterSyncBatchId(event.target.value)} /></label>
        <button type="button" onClick={uploadRecipients}>导入应发名单</button>
      </div>
      <div className="card">
        <h3>问卷答卷</h3>
        <label>问卷答卷<input type="file" accept=".xlsx" onChange={(event) => setSurveyFile(event.target.files?.[0])} /></label>
        <button type="button" onClick={uploadSurvey}>导入问卷答卷</button>
      </div>
    </div>
    {message && <p role="status">{message}</p>}
    {overview && <div className="metrics confirmation-metrics">{metricItems.map(([key, label]) => {
      const value = overview[key] as { customerCount: number; expectedAmount: number };
      return <div key={key}><small>{label}</small><strong>{value.customerCount} / ¥{value.expectedAmount}</strong></div>;
    })}</div>}
    {overview && <div className="card"><h3>对账结果</h3><div className="table-wrap"><table><thead><tr>
      <th>太古客户编号</th><th>客户名称</th><th>应发金额</th><th>映射状态</th><th>确认状态</th><th>提交时间</th>
    </tr></thead><tbody>{recipients.map((item) => <tr key={item.feeRecipientId}>
      <td>{item.sapCustomerCode}</td><td>{item.sapCustomerName}</td><td>¥{item.expectedAmount}</td>
      <td>{item.mappingStatus}</td><td>{item.confirmationStatus}</td><td>{item.submittedAt || "—"}</td>
    </tr>)}</tbody></table></div></div>}
    {overview && <div className="card"><h3>异常核查</h3>{exceptions.length === 0 ? <p>暂无异常</p> : exceptions.map((item, index) =>
      <div className="row" key={`${item.kind}-${item.sapCustomerCode}-${index}`}>
        <strong>{exceptionLabels[item.kind] || item.kind}</strong>
        <span>{item.sapCustomerCode || "—"} · {item.sapCustomerName || "—"}</span>
        <span>{item.matchReason || "待人工核查"}</span>
      </div>)}</div>}
  </section>;
}
