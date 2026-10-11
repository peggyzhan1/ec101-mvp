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

export interface ConfirmationMetric { customerCount: number; expectedAmount: number }
export interface ConfirmationOverview {
  feeCycleCode: string;
  recipient: ConfirmationMetric; submitted: ConfirmationMetric; notSubmitted: ConfirmationMetric;
  received: ConfirmationMetric; notReceived: ConfirmationMetric; conflict: ConfirmationMetric;
  outsideListResponseCount: number; unmatchedMapping: ConfirmationMetric; ambiguousMapping: ConfirmationMetric;
}
export interface ConfirmationRecipient {
  feeRecipientId: number; feeCycleCode: string; sapCustomerCode: string; sapCustomerName: string;
  expectedAmount: number; mappingStatus: string; mappingReason?: string | null;
  platformCustomerNo?: string | null; surveyResponseId?: number | null;
  receivedAnswer?: string | null; notReceivedReason?: string | null; customerComment?: string | null;
  submittedAt?: string | null; hasConflict: boolean; confirmationStatus: string; rawSequenceNo?: string | null;
}
export interface ConfirmationException {
  kind: string; sapCustomerCode?: string | null; sapCustomerName?: string | null;
  expectedAmount?: number | null; receivedAnswer?: string | null; submittedAt?: string | null;
  rawSequenceNo?: string | null; matchReason?: string | null;
}
export interface RecipientUploadInput {
  feeCycle: string; cycleName: string; periodStart: string; periodEnd: string; masterSyncBatchId: number;
}
export interface RecipientImportResult {
  feeCycleId: number; inputRowCount: number; recipientCount: number;
  matchedCount: number; unmatchedCount: number; ambiguousCount: number;
}
export interface SurveyImportResult {
  surveyImportBatchId: number; rowCount: number; matchedCount: number;
  unmatchedCount: number; invalidCount: number;
}
