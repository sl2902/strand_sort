import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import type { DonationItem } from "../lib/types";
import { DemoItemDetail } from "../components/DemoItemDetail";
import { Spinner } from "../components/Spinner";

/**
 * Standalone /demo/item/:itemId route — reached by manually clicking a
 * card in the /demo sequence outside of Play mode. Loaded straight from
 * the same static fixture JSON (item_id is always "demo-{fixture name}",
 * so the name is recovered by stripping that prefix), never from the live
 * GET /inventory/:id route. Actual detail rendering lives in
 * DemoItemDetail, shared with DemoPage's own inline "inventory-detail"
 * step (which renders the same component directly from the fixture data
 * already in memory, no navigation, during Play's auto-advance).
 */
export function DemoItemPage() {
  const { itemId } = useParams<{ itemId: string }>();
  const [item, setItem] = useState<DonationItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  // React Router doesn't reset scroll position on navigation — landing
  // here from partway down the /demo sequence would otherwise show
  // whatever section happened to be at that scroll offset instead of the
  // top of this item's detail view.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [itemId]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!itemId) return;
      const name = itemId.replace(/^demo-/, "");
      try {
        const res = await fetch(`/demo/${name}.json`);
        if (!res.ok) throw new Error(`${name}.json: ${res.status}`);
        const data: DonationItem = await res.json();
        data.image_urls = data.image_urls.map((u) => `${window.location.origin}${u}`);
        data.thumbnail_urls = data.thumbnail_urls.map((u) => `${window.location.origin}${u}`);
        if (!cancelled) setItem(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Couldn't load this demo item.");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [itemId]);

  if (error) {
    return (
      <div className="space-y-4">
        <BackLink />
        <div className="rounded-2xl border border-danger-400/40 bg-danger-100/60 px-5 py-4 text-sm text-danger-600">
          {error}
        </div>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="space-y-4">
        <BackLink />
        <div className="flex items-center gap-2 text-ink-700/60">
          <Spinner /> Loading item…
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <BackLink />
      <DemoItemDetail item={item} />
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/demo" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-700/70 hover:text-ink-900">
      <ArrowLeft size={15} />
      Back to demo
    </Link>
  );
}
