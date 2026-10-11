import { useState } from "react";
import { createApiClient } from "./api/client";
import { ActivityFeesView } from "./views/ActivityFeesView"; import { BusinessDataView } from "./views/BusinessDataView"; import { CouponFeesView } from "./views/CouponFeesView"; import { FeeConfirmationView } from "./views/FeeConfirmationView"; import { ImportView } from "./views/ImportView"; import { IssuesView } from "./views/IssuesView"; import { OverviewView } from "./views/OverviewView"; import { ReleaseView } from "./views/ReleaseView"; import { RoiView } from "./views/RoiView";

const api = createApiClient();
const views = { overview: ["费用总览", OverviewView], import: ["导入", ImportView], confirmation: ["客户确认", FeeConfirmationView], business: ["业务数据", BusinessDataView], activities: ["活动费用", ActivityFeesView], coupons: ["优惠券费用", CouponFeesView], release: ["释放候选", ReleaseView], issues: ["核算提示", IssuesView], roi: ["ROI", RoiView] } as const;
export function App() { const [active, setActive] = useState<keyof typeof views>("overview"); const View = views[active][1]; return <main><header><h1>EC101 费用运营台</h1><p>实际费用结果展示与运营处理</p></header><nav>{(Object.keys(views) as Array<keyof typeof views>).map((key) => <button className={active === key ? "active" : ""} onClick={() => setActive(key)} key={key}>{views[key][0]}</button>)}</nav><View api={api} /></main>; }
