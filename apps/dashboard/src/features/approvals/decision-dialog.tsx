import { CheckCircle2, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { MoneyText } from "@/components/system/data-display";
import { FormAlert, FormField } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { ApiError } from "@/lib/api-client";
import { isMonetary, useDecide, type ApprovalDetail } from "./api";

/** Approve / reject with a comment (required to reject). Names the document and amount (UI_UX_DESIGN.md § 6). */
export function DecisionDialog({ approval, decision, onClose }: { approval: ApprovalDetail; decision: "approve" | "reject"; onClose: () => void }) {
  const decide = useDecide();
  const [comment, setComment] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const step = approval.steps.find((s) => s.step_order === approval.current_step);
  const isLast = approval.steps.filter((s) => s.status === "waiting").length === 0;
  const reject = decision === "reject";
  const money = isMonetary(approval);
  const commits = approval.entity_type === "purchase_request";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (reject && comment.trim().length < 3) {
      setError("Explain why the request is rejected (at least 3 characters).");
      return;
    }
    setError(null);
    try {
      await decide.mutateAsync({ id: approval.id, decision, comment });
      toast.success(reject ? `${approval.entity_code} rejected` : isLast ? `${approval.entity_code} approved` : `${approval.entity_code} approved — moved to the next step`,
        { description: reject ? "The requester has been notified." : isLast && commits ? "The budget commitment has been recorded." : undefined });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The decision couldn't be saved. Try again.");
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader
          title={`${reject ? "Reject" : "Approve"} ${approval.entity_code}?`}
          description={<>
            <span className="block">{approval.title}</span>
            <span className="mt-1 block">{money && <><MoneyText value={approval.amount} decimals={2} className="font-medium text-fg" /> · </>}{step?.label} approval</span>
          </>}
        />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={error} />
          {!reject && isLast && commits && (
            <p className="rounded-[var(--radius-control)] bg-surface-subtle px-3 py-2 text-small text-fg-secondary">
              This is the final approval. The amount will be committed against the budget.
            </p>
          )}
          <FormField label={reject ? "Reason for rejection" : "Comment (optional)"} htmlFor="decision-comment" required={reject}>
            <Textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} placeholder={reject ? "Tell the requester what to change…" : "Add context for the record…"} autoFocus />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose} disabled={decide.isPending}>Cancel</Button>
            <Button type="submit" variant={reject ? "danger" : "primary"} loading={decide.isPending}>
              {reject ? <><XCircle /> Reject request</> : <><CheckCircle2 /> Approve</>}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
