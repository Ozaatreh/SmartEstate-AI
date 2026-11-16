import { Ban } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { FormField } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { ApiError } from "@/lib/api-client";
import { useReservationMutations } from "./api";

/** Cancelling releases the unit back to available; a reason is required (and audited). */
export function CancelReservationDialog({ reservation, onClose }: { reservation: { id: string; code: string; unit: { code: string } }; onClose: () => void }) {
  const { cancel } = useReservationMutations();
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | undefined>();
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (reason.trim().length < 3) return setError("Give a reason (at least 3 characters).");
    cancel.mutate({ id: reservation.id, reason: reason.trim() }, {
      onSuccess: () => { toast.success(`${reservation.code} cancelled; ${reservation.unit.code} is available`); onClose(); },
      onError: (err) => setError(err instanceof ApiError ? err.message : "Couldn't cancel the reservation"),
    });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader title={`Cancel ${reservation.code}?`} description={`Unit ${reservation.unit.code} becomes available again. This can't be undone.`} />
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormField label="Reason" htmlFor="cancel-reservation-reason" error={error} required>
            <Textarea rows={3} maxLength={500} value={reason} onChange={(e) => { setReason(e.target.value); setError(undefined); }} autoFocus />
          </FormField>
          <DialogFooter>
            <Button type="button" onClick={onClose}>Keep reservation</Button>
            <Button type="submit" variant="danger" loading={cancel.isPending}><Ban /> Cancel reservation</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
