import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import clsx from "clsx";

export function Spinner({ size = 16, className }: { size?: number; className?: string }) {
  return <Loader2 size={size} className={clsx("animate-spin", className)} />;
}

/** Rotating status line used during long-running scans — keeps the user informed rather than guessing. */
export function ScanProgress({ messages }: { messages: string[] }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setIndex((i) => (i + 1) % messages.length);
    }, 1800);
    return () => window.clearInterval(id);
  }, [messages.length]);

  return (
    <div className="flex flex-col items-center gap-4 py-10 text-center">
      <div className="relative flex h-16 w-16 items-center justify-center">
        <span className="absolute inset-0 rounded-full bg-terracotta-400/30 animate-ring-pulse" />
        <Spinner size={28} className="text-terracotta-500" />
      </div>
      <div>
        <p className="font-medium text-ink-800">{messages[index]}</p>
        <p className="mt-1 text-xs text-ink-700/60">
          This can take up to 15–20 seconds — the vision model is reading the label closely.
        </p>
      </div>
    </div>
  );
}
