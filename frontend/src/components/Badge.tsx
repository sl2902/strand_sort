import clsx from "clsx";
import type { ReactNode } from "react";

type BadgeTone = "neutral" | "terracotta" | "plum" | "saffron" | "success" | "danger";

const toneClasses: Record<BadgeTone, string> = {
  neutral: "bg-cream-200 text-ink-700 border-cream-300",
  terracotta: "bg-terracotta-100 text-terracotta-700 border-terracotta-300/60",
  plum: "bg-plum-100 text-plum-700 border-plum-300/60",
  saffron: "bg-saffron-100 text-saffron-600 border-saffron-300/60",
  success: "bg-success-100 text-success-600 border-success-400/40",
  danger: "bg-danger-100 text-danger-600 border-danger-400/40",
};

export function Badge({
  children,
  tone = "neutral",
  icon,
  className,
  title,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  icon?: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium leading-none",
        toneClasses[tone],
        className
      )}
    >
      {icon}
      {children}
    </span>
  );
}
