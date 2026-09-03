import { useEffect, useState } from "react";
import { PartyPopper, Inbox } from "lucide-react";
import { listPendingReviews, resolveReview, ApiError } from "../lib/api";
import type { DonationItem } from "../lib/types";
import { ReviewItemCard } from "../components/review/ReviewItemCard";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/Toast";

const LEAVE_ANIMATION_MS = 380;

export function ReviewQueuePage({ onQueueChange }: { onQueueChange: () => void }) {
  const [items, setItems] = useState<DonationItem[] | null>(null);
  const [resolvingIds, setResolvingIds] = useState<Set<string>>(new Set());
  const [leavingIds, setLeavingIds] = useState<Set<string>>(new Set());
  const { show } = useToast();

  const load = () => {
    listPendingReviews()
      .then(setItems)
      .catch((err) => show(err instanceof ApiError ? err.message : "Couldn't load the review queue.", "error"));
  };

  useEffect(load, []);

  const resolve = async (item: DonationItem, approved: boolean, correctedDate: string | null, notes: string | null) => {
    setResolvingIds((prev) => new Set(prev).add(item.item_id));
    try {
      await resolveReview(item.item_id, { approved, corrected_date: correctedDate, notes });
      show(
        approved ? `${item.product_name} approved and added to inventory.` : `${item.product_name} discarded.`,
        "success"
      );
      setLeavingIds((prev) => new Set(prev).add(item.item_id));
      window.setTimeout(() => {
        setItems((prev) => (prev ? prev.filter((i) => i.item_id !== item.item_id) : prev));
        setLeavingIds((prev) => {
          const next = new Set(prev);
          next.delete(item.item_id);
          return next;
        });
        onQueueChange();
      }, LEAVE_ANIMATION_MS);
    } catch (err) {
      show(err instanceof ApiError ? err.message : "Couldn't resolve this item.", "error");
    } finally {
      setResolvingIds((prev) => {
        const next = new Set(prev);
        next.delete(item.item_id);
        return next;
      });
    }
  };

  return (
    <div className="space-y-6">
      <div className="animate-fade-up">
        <p className="text-sm font-semibold uppercase tracking-wide text-terracotta-600">Review queue</p>
        <h1 className="mt-1 text-3xl font-semibold sm:text-4xl">Clear the queue</h1>
        <p className="mt-2 text-ink-700/70">
          {items && items.length > 0
            ? `${items.length} item${items.length === 1 ? "" : "s"} waiting on a second look.`
            : "Items the agent couldn't confidently auto-commit land here."}
        </p>
      </div>

      {items === null && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton h-40 rounded-2xl" />
          ))}
        </div>
      )}

      {items !== null && items.length === 0 && (
        <EmptyState
          icon={<PartyPopper size={24} />}
          title="Inbox zero"
          description="Nothing needs a human look right now — nice work."
        />
      )}

      {items !== null && items.length > 0 && (
        <div className="space-y-4">
          {items.map((item) => (
            <ReviewItemCard
              key={item.item_id}
              item={item}
              isResolving={resolvingIds.has(item.item_id)}
              isLeaving={leavingIds.has(item.item_id)}
              onApprove={(correctedDate, notes) => resolve(item, true, correctedDate, notes)}
              onReject={(notes) => resolve(item, false, null, notes)}
              onImageRetry={load}
            />
          ))}
        </div>
      )}

      {items !== null && items.length === 0 && (
        <div className="flex items-center justify-center gap-2 pt-4 text-xs text-ink-700/40">
          <Inbox size={13} />
          New flags will show up here automatically.
        </div>
      )}
    </div>
  );
}
