// Mirror của schema backend hiện tại — đổi model backend thì sửa cả thư mục này.
// Nguồn: src/core/response.py, src/common/schemas.py, src/modules/*/schemas.py
// và bảng endpoint trong docs/api-contract.md.
//
// Mỗi file con = đúng một slice backend. Import ở nơi khác luôn trỏ vào barrel
// này (`from "../types"`), không trỏ thẳng vào file slice — đổi ranh giới slice
// sau này sẽ không phải sửa call site.

export * from "./envelope";
export * from "./auth";
export * from "./patients";
export * from "./medications";
export * from "./routine";
export * from "./prescriptions";
export * from "./schedules";
export * from "./alerts";
export * from "./dashboard";
export * from "./admin";
export * from "./healthSurveys";
export * from "./adherence";
export * from "./adverseEvents";
export * from "./chat";
