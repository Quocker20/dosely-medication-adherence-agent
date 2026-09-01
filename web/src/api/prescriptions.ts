// Slice 5: Prescriptions
import { request, requestBlob } from "./client";
import type {
  CreatePrescriptionRequest,
  CreatePrescriptionResponse,
  PageResponse,
  PrescriptionDetail,
  PrescriptionItemDetail,
  PrescriptionItemIn,
} from "../types";

export const prescriptionsApi = {
  /** Bệnh nhân được xác định bằng số điện thoại (find-or-create), không phải patient_id. */
  createPrescription: (payload: CreatePrescriptionRequest) =>
    request<CreatePrescriptionResponse>("/prescriptions", { method: "POST", body: payload }),

  prescription: (prescriptionId: string) =>
    request<PrescriptionDetail>(`/prescriptions/${prescriptionId}`),

  patientPrescriptions: (patientId: string, params: { status?: string; page?: number; size?: number } = {}) =>
    request<PageResponse<PrescriptionDetail>>(`/patients/${patientId}/prescriptions`, {
      query: { status: params.status, page: params.page ?? 1, size: params.size ?? 20 },
    }),

  updatePrescription: (prescriptionId: string, diagnosisNote: string | null) =>
    request<PrescriptionDetail>(`/prescriptions/${prescriptionId}`, {
      method: "PUT",
      body: { diagnosis_note: diagnosisNote },
    }),

  approvePrescription: (prescriptionId: string) =>
    request<PrescriptionDetail>(`/prescriptions/${prescriptionId}/approve`, { method: "POST" }),

  /** Endpoint duy nhất trả binary thay vì envelope JSON — chỉ dùng được khi
   * đơn đã APPROVED (422 nếu chưa/đã huỷ). Không có giới hạn tải backend;
   * nút "chỉ hiện một lần" là hành vi UI, xem PrescriptionView.tsx. */
  downloadPrescriptionPdf: (prescriptionId: string) =>
    requestBlob(`/prescriptions/${prescriptionId}/pdf`),

  cancelPrescription: (prescriptionId: string, cancelReason: string) =>
    request<PrescriptionDetail>(`/prescriptions/${prescriptionId}/cancel`, {
      method: "POST",
      body: { cancel_reason: cancelReason },
    }),

  addPrescriptionItem: (prescriptionId: string, item: PrescriptionItemIn) =>
    request<PrescriptionItemDetail>(`/prescriptions/${prescriptionId}/items`, {
      method: "POST",
      body: item,
    }),

  updatePrescriptionItem: (prescriptionId: string, itemId: string, item: PrescriptionItemIn) =>
    request<PrescriptionItemDetail>(`/prescriptions/${prescriptionId}/items/${itemId}`, {
      method: "PUT",
      body: item,
    }),

  deletePrescriptionItem: (prescriptionId: string, itemId: string) =>
    request<null>(`/prescriptions/${prescriptionId}/items/${itemId}`, { method: "DELETE" }),
};
