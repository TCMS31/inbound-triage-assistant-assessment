import type { Category, Priority } from "../types";

export const CATEGORY_LABELS: Record<Category, string> = {
  prospect: "Prospect",
  existing_client: "Existing client",
  vendor_partner: "Vendor / partner",
  noise_other: "Noise / other",
  needs_review: "Needs review",
};

export const PRIORITY_LABELS: Record<Priority, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};
