export interface Page<T> { items: T[]; total: number; limit?: number; offset?: number }

export interface Overview {
  calculationRunIds: number[]; activityBenefit: number; couponBenefit: number; totalBenefit: number;
  releasedActivityBenefit: number; releasedCouponBenefit: number; participatingOrders: number; releasedOrders: number;
}
export interface CouponSummary {
  calculationRunId: number; couponConfigId: number | null; usedCount: number; usedAmount: number;
  linkedCount: number; linkedAmount: number; releasableCount: number; releasableAmount: number;
  unlinkedCount: number; unlinkedAmount: number; settleStatus?: string | null;
}
export interface UnlinkedCoupon {
  couponRedemptionId: number; couponNo: string; customerNo: string | null; customerName: string | null;
  status: string; discountAmount: number;
}
export interface ActivityFee {
  calculationRunId: number; activityNo: string; activityName: string; activityType: string;
  actualDiscountTotal: number; participatingOrders: number; releasedOrders: number; releasedAmount: number;
  pendingOrders: number; pendingAmount: number; settleStatus: string | null;
}
export interface Release { orderNo: string; customerNo: string | null; customerName: string | null; isCandidate: boolean; reason: string; activityBenefit: number; couponBenefit: number }
export interface Issue { orderNo: string | null; issueType: string; level: string; reason: string }
export interface Roi { activityNo: string; activityName: string; roi: number | null; [key: string]: unknown }
export interface ImportResult { importBatchId: number; calculationRunId: number; status: string }
export interface BusinessRow { [key: string]: string | number | null }
