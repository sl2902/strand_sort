import { useEffect, useMemo, useState } from "react";
import {
  Play,
  Pause,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  Camera,
  ScanLine,
  CalendarClock,
  Leaf,
  AlertTriangle,
  Clock,
} from "lucide-react";
import clsx from "clsx";
import { InventoryItemCard } from "../components/InventoryItemCard";
import { ReviewItemCard } from "../components/review/ReviewItemCard";
import { expiryBadgeContent } from "../lib/format";
import type { DonationItem } from "../lib/types";

interface Manifest {
  fixtures: string[];
}

const noop = () => {};

type StepId = "pipeline" | "inventory" | "review" | "expiry";

interface StepDef {
  id: StepId;
  title: string;
  narrationCue: string;
  durationMs: number;
}

const PIPELINE_PHASES = [
  { icon: Camera, label: "Photo or video in" },
  { icon: ScanLine, label: "Reading the label" },
  { icon: CalendarClock, label: "Cross-checking the expiry date" },
  { icon: Leaf, label: "Checking dietary & nutrition symbols" },
];

/** Self-contained: cycles its own phase index on a timer sized to fit
 * durationMs, independent of the outer step timer. Holds on the last phase
 * once reached rather than looping, so it doesn't visibly reset right
 * before the outer sequence advances away from it. */
function PipelineStageVisual({ durationMs }: { durationMs: number }) {
  const [phaseIndex, setPhaseIndex] = useState(0);

  useEffect(() => {
    setPhaseIndex(0);
    const perPhase = durationMs / PIPELINE_PHASES.length;
    const id = window.setInterval(() => {
      setPhaseIndex((i) => Math.min(i + 1, PIPELINE_PHASES.length - 1));
    }, perPhase);
    return () => window.clearInterval(id);
  }, [durationMs]);

  return (
    <div className="mx-auto max-w-md space-y-3">
      {PIPELINE_PHASES.map((phase, i) => {
        const Icon = phase.icon;
        const state = i < phaseIndex ? "done" : i === phaseIndex ? "active" : "pending";
        return (
          <div
            key={phase.label}
            className={clsx(
              "flex items-center gap-3 rounded-2xl border px-4 py-3 shadow-soft transition-all duration-300",
              state === "active" && "border-terracotta-400/60 bg-terracotta-100/60 scale-[1.02]",
              state === "done" && "border-success-400/40 bg-success-100/50",
              state === "pending" && "border-cream-300 bg-cream-50 opacity-50"
            )}
          >
            <Icon
              size={18}
              className={clsx(
                state === "active" && "text-terracotta-600",
                state === "done" && "text-success-600",
                state === "pending" && "text-ink-700/40"
              )}
            />
            <span className="text-sm font-medium text-ink-800">{phase.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function StepCaption({ children }: { children: string }) {
  return <p className="mx-auto max-w-lg text-center text-sm text-ink-700/70">{children}</p>;
}

/**
 * Sequenced walkthrough for recording the demo video's pipeline-explainer
 * segment — for recording without depending on live Bedrock/Gemini
 * extraction. Reads whatever fixture names are listed in
 * /demo/manifest.json (public/demo/), so dropping in a new fixture (e.g.
 * via scripts/capture_demo_fixture.py) never requires a code change here.
 * Zero calls to the real API at any step: fixture JSON and images are all
 * served as static files from this app's own origin, and
 * image_urls/thumbnail_urls are rewritten to that same origin so
 * resolveImageUrl's absolute-URL passthrough kicks in instead of pointing
 * them at the backend. Header/nav come from the shared NavBar in App.tsx,
 * present for every step of the sequence, not just on initial load.
 *
 * Step order (pipeline -> inventory -> review -> optional expiry)
 * deliberately matches the demo video plan's narration beats.
 */
export function DemoPage() {
  const [items, setItems] = useState<DonationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const manifestRes = await fetch("/demo/manifest.json");
        if (!manifestRes.ok) throw new Error(`manifest.json: ${manifestRes.status}`);
        const manifest: Manifest = await manifestRes.json();

        const loaded = await Promise.all(
          manifest.fixtures.map(async (name) => {
            const res = await fetch(`/demo/${name}.json`);
            if (!res.ok) throw new Error(`${name}.json: ${res.status}`);
            const item: DonationItem = await res.json();
            // Absolute-ify so resolveImageUrl's ^https?:// check treats
            // these as already-final URLs instead of rewriting them onto
            // the API origin. Everything else is left exactly as authored
            // in the fixture — no aggregation, no recomputation — so
            // quantity/expiry_status/etc. always match the JSON verbatim.
            item.image_urls = item.image_urls.map((u) => `${window.location.origin}${u}`);
            item.thumbnail_urls = item.thumbnail_urls.map((u) => `${window.location.origin}${u}`);
            return item;
          })
        );

        if (!cancelled) setItems(loaded);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Couldn't load demo fixtures.");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const { steps, inventoryItem, reviewItem, expiryItem } = useMemo(() => {
    const committed = items?.filter((i) => !i.requires_human_review) ?? [];
    const flagged = items?.filter((i) => i.requires_human_review) ?? [];

    // Prefer a genuinely "fine" item for the Inventory beat, so it stays
    // honest with the "clean items go straight to inventory" narration —
    // falls back to whatever's first if none happen to be fine right now.
    const inventoryItem = committed.find((i) => i.expiry_status === "fine") ?? committed[0] ?? null;
    const reviewItem = flagged[0] ?? null;
    // A different committed item that's genuinely near/at expiry right
    // now — expiry_status is recomputed fresh server-side on every real
    // read, so which fixture qualifies can change day to day (run
    // scripts/refresh_demo_fixture_expiry.py before recording to keep
    // these fixture values current).
    const expiryItem =
      committed.find(
        (i) => i.item_id !== inventoryItem?.item_id && (i.expiry_status === "near_expiry" || i.expiry_status === "expired")
      ) ?? null;

    const steps: StepDef[] = [
      {
        id: "pipeline",
        title: "How it works",
        narrationCue:
          "A photo or video goes in — strand_sort reads the label, cross-checks the expiry date, and pulls dietary and nutrition details straight from the packaging.",
        durationMs: 15000,
      },
      {
        id: "inventory",
        title: "Clean items go straight to inventory",
        narrationCue: "Clean items go straight to inventory.",
        durationMs: 15000,
      },
      {
        id: "review",
        title: "Anything uncertain gets flagged",
        narrationCue:
          "Anything uncertain — a low-confidence date, a damaged label — gets flagged for a quick human check instead of a risky guess.",
        durationMs: 20000,
      },
    ];
    if (expiryItem) {
      steps.push({
        id: "expiry",
        title: "Expiry status, recalculated fresh",
        narrationCue: "Expiry status is never stale — it's recalculated fresh every time an item is viewed.",
        durationMs: 8000,
      });
    }

    return { steps, inventoryItem, reviewItem, expiryItem };
  }, [items]);

  useEffect(() => {
    if (!isPlaying || steps.length === 0) return;
    if (stepIndex >= steps.length - 1) {
      setIsPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setStepIndex((i) => i + 1), steps[stepIndex].durationMs);
    return () => window.clearTimeout(timer);
  }, [isPlaying, stepIndex, steps]);

  if (error) {
    return <p className="text-sm text-danger-600">Demo fixtures failed to load: {error}</p>;
  }

  if (!items || steps.length === 0) {
    return <p className="text-sm text-ink-700/60">Loading demo fixtures…</p>;
  }

  const currentStep = steps[stepIndex];
  const atEnd = stepIndex === steps.length - 1;

  const togglePlay = () => {
    if (!isPlaying) {
      if (atEnd) setStepIndex(0);
      setIsPlaying(true);
    } else {
      setIsPlaying(false);
    }
  };

  const goTo = (i: number) => {
    setStepIndex(Math.max(0, Math.min(steps.length - 1, i)));
  };

  return (
    <div className="space-y-8">
      <div className="animate-fade-up flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-terracotta-400/40 bg-terracotta-100/50 px-4 py-3 text-sm text-terracotta-700">
        <span>Demo mode — static fixtures, no live scans or API calls.</span>
        <div className="flex items-center gap-1">
          {steps.map((step, i) => (
            <button
              key={step.id}
              onClick={() => goTo(i)}
              aria-label={`Go to ${step.title}`}
              className={clsx(
                "h-2 rounded-full transition-all",
                i === stepIndex ? "w-6 bg-terracotta-500" : "w-2 bg-terracotta-300/60 hover:bg-terracotta-400"
              )}
            />
          ))}
        </div>
      </div>

      <div key={currentStep.id} className="animate-fade-up space-y-4">
        <div className="text-center">
          <h2 className="font-display text-xl font-semibold text-ink-900 sm:text-2xl">{currentStep.title}</h2>
        </div>

        {currentStep.id === "pipeline" && (
          <div className="space-y-4">
            <PipelineStageVisual durationMs={currentStep.durationMs} />
            <StepCaption>{currentStep.narrationCue}</StepCaption>
          </div>
        )}

        {currentStep.id === "inventory" && (
          <div className="space-y-4">
            {inventoryItem ? (
              <div className="mx-auto max-w-md">
                <InventoryItemCard item={inventoryItem} onImageRetry={noop} onDelete={undefined} />
              </div>
            ) : (
              <StepCaption>No committed fixture available.</StepCaption>
            )}
            <StepCaption>{currentStep.narrationCue}</StepCaption>
          </div>
        )}

        {currentStep.id === "review" && (
          <div className="space-y-4">
            {reviewItem ? (
              <div className="mx-auto max-w-md">
                <ReviewItemCard
                  item={reviewItem}
                  isResolving={false}
                  isLeaving={false}
                  onApprove={noop}
                  onReject={noop}
                  onImageRetry={noop}
                />
              </div>
            ) : (
              <div className="mx-auto flex max-w-md items-start gap-2 rounded-2xl border border-dashed border-cream-300 bg-cream-50 px-4 py-3.5 text-sm text-ink-700/70">
                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-ink-700/40" />
                <p>
                  No flagged example captured yet. Run{" "}
                  <code className="rounded bg-cream-200 px-1 py-0.5 text-xs">
                    scripts/capture_demo_fixture.py
                  </code>{" "}
                  against a real flagged photo to add one — it'll show up here automatically.
                </p>
              </div>
            )}
            <StepCaption>{currentStep.narrationCue}</StepCaption>
          </div>
        )}

        {currentStep.id === "expiry" && expiryItem && (
          <div className="space-y-4">
            <div className="mx-auto max-w-md space-y-2">
              <InventoryItemCard item={expiryItem} onImageRetry={noop} onDelete={undefined} />
              <div className="flex items-center justify-center gap-1.5 text-xs text-ink-700/60">
                <Clock size={13} />
                <span>{expiryBadgeContent(expiryItem.expiry_status, expiryItem.expiration_date).label}</span>
              </div>
            </div>
            <StepCaption>{currentStep.narrationCue}</StepCaption>
          </div>
        )}
      </div>

      <div className="flex items-center justify-center gap-3">
        <button
          onClick={() => goTo(stepIndex - 1)}
          disabled={stepIndex === 0}
          aria-label="Previous step"
          className="rounded-full border border-cream-300 bg-cream-50 p-2.5 text-ink-700 shadow-soft transition-colors hover:border-terracotta-300 disabled:opacity-40"
        >
          <ChevronLeft size={16} />
        </button>

        <button
          onClick={togglePlay}
          className="inline-flex items-center gap-2 rounded-full bg-terracotta-500 px-5 py-2.5 text-sm font-semibold text-cream-50 shadow-soft transition-colors hover:bg-terracotta-600"
        >
          {isPlaying ? (
            <>
              <Pause size={15} />
              Pause
            </>
          ) : atEnd ? (
            <>
              <RotateCcw size={15} />
              Replay
            </>
          ) : (
            <>
              <Play size={15} />
              Play
            </>
          )}
        </button>

        <button
          onClick={() => goTo(stepIndex + 1)}
          disabled={atEnd}
          aria-label="Next step"
          className="rounded-full border border-cream-300 bg-cream-50 p-2.5 text-ink-700 shadow-soft transition-colors hover:border-terracotta-300 disabled:opacity-40"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
