import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="animate-fade-up flex flex-col items-center gap-3 rounded-2xl border border-dashed border-cream-300 bg-cream-50/60 px-6 py-14 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-cream-200 text-terracotta-500">
        {icon}
      </div>
      <h3 className="font-display text-lg font-semibold text-ink-900">{title}</h3>
      {description && <p className="max-w-sm text-sm text-ink-700/70">{description}</p>}
      {action}
    </div>
  );
}
