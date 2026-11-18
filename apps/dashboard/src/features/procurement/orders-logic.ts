import type { PurchaseOrderDetail } from "./api";

export const CANCEL_OPTIONS = [
  {
    value: "release",
    title: "Release the budget and close the request",
    body: "Returns the committed amount to the budget once. The request is closed and takes no further orders.",
  },
  {
    value: "keep",
    title: "Keep the budget for a replacement order",
    body: "The commitment stays on the request so procurement can create a replacement order from it.",
  },
] as const;

/** What the order means for the request's single budget commitment. */
export function budgetNote(o: Pick<PurchaseOrderDetail, "status" | "budget_released" | "request_status">): { tone: "success" | "neutral" | "info"; text: string } {
  if (o.status === "cancelled" && o.budget_released) return { tone: "neutral", text: "Released when this order was cancelled. The request is closed." };
  if (o.status === "cancelled") return { tone: "info", text: "Kept on the request for a replacement order." };
  return { tone: "success", text: "Committed once, at the request's final approval. This order adds no second commitment." };
}
