// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 3 — Medications (danh mục dược phẩm)

export interface MedicationDetail {
  id: string;
  name: string;
  composition: string | null;
  manufacturer: string | null;
  uses: string | null;
  side_effects: string | null;
  image_url: string | null;
  source_name: string;
  is_active: boolean;
}
