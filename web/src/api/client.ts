import type { ActivityFee, BusinessRow, CouponSummary, ImportResult, Issue, Overview, Page, Release, Roi, UnlinkedCoupon } from "./types";

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export interface ApiClient {
  upload(standard: File, sources?: File, calcDate?: string): Promise<ImportResult>;
  overview(runId?: number): Promise<Overview>;
  activities(runId?: number, limit?: number, offset?: number): Promise<Page<ActivityFee>>;
  coupons(runId?: number, limit?: number, offset?: number): Promise<Page<CouponSummary>>;
  unlinkedCoupons(runId?: number, limit?: number, offset?: number): Promise<Page<UnlinkedCoupon>>;
  business(resource: string, query?: string): Promise<Page<BusinessRow>>;
  release(batchId: number, candidate?: boolean): Promise<Page<Release>>;
  issues(runId?: number): Promise<Page<Issue>>;
  roi(runId?: number): Promise<{ items: Roi[] }>;
}

function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined) params.set(key, String(value)); });
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function createApiClient(baseUrl = import.meta.env.VITE_API_BASE_URL || "", fetcher: Fetcher = fetch): ApiClient {
  const base = baseUrl.replace(/\/$/, "");
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetcher(`${base}${path}`, init);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
    return payload as T;
  }
  return {
    async upload(standard, sources, calcDate) {
      const body = new FormData(); body.set("standard", standard); if (sources) body.set("sources", sources);
      if (calcDate) body.set("calcDate", calcDate);
      return request<ImportResult>("/api/imports", { method: "POST", body });
    },
    overview: (runId) => request(`/api/fee-tpm/overview${query({ calculationRunId: runId })}`),
    activities: (runId, limit = 100, offset = 0) => request(`/api/fee-tpm/activities${query({ calculationRunId: runId, limit, offset })}`),
    coupons: (runId, limit = 100, offset = 0) => request(`/api/fee-tpm/coupons${query({ calculationRunId: runId, limit, offset })}`),
    unlinkedCoupons: (runId, limit = 100, offset = 0) => request(`/api/fee-tpm/coupons/unlinked${query({ calculationRunId: runId, limit, offset })}`),
    business: (resource, value = "") => request(`/api/business/${resource}${query({ query: value })}`),
    release: (batchId, candidate) => request(`/api/imports/${batchId}/release${query({ candidate: candidate === undefined ? undefined : String(candidate) })}`),
    issues: (runId) => request(`/api/fee-tpm/issues${query({ calculationRunId: runId })}`),
    roi: (runId) => request(`/api/roi${query({ calculationRunId: runId })}`),
  };
}
