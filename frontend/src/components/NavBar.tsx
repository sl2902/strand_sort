import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Camera, Boxes, ListChecks, AlarmClock } from "lucide-react";
import clsx from "clsx";

function NavItem({
  to,
  icon,
  label,
  badge,
}: {
  to: string;
  icon: ReactNode;
  label: string;
  badge?: number;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        clsx(
          "relative flex flex-col items-center gap-1 rounded-2xl px-4 py-2 text-xs font-medium transition-colors sm:flex-row sm:gap-2 sm:px-4 sm:py-2.5 sm:text-sm",
          isActive
            ? "bg-terracotta-500 text-cream-50 shadow-soft"
            : "text-ink-700 hover:bg-cream-200/70"
        )
      }
    >
      {icon}
      <span>{label}</span>
      {!!badge && (
        <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-plum-600 px-1 text-[10px] font-bold text-cream-50 sm:static sm:ml-1">
          {badge}
        </span>
      )}
    </NavLink>
  );
}

export function NavBar({
  pendingReviewCount,
  expiringCount,
}: {
  pendingReviewCount: number;
  expiringCount: number;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-cream-300/70 bg-cream-100/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-terracotta-500 text-lg shadow-soft">
            🧺
          </div>
          <div className="leading-tight">
            <p className="font-display text-lg font-semibold text-ink-900">Strand Sort</p>
            <p className="hidden text-[11px] text-ink-700/70 sm:block">Donation intake &amp; sorting</p>
          </div>
        </div>
        <nav className="flex items-center gap-1.5 sm:gap-2">
          <NavItem to="/" icon={<Camera size={16} />} label="Scan" />
          <NavItem to="/inventory" icon={<Boxes size={16} />} label="Inventory" />
          <NavItem
            to="/expiring"
            icon={<AlarmClock size={16} />}
            label="Expiring"
            badge={expiringCount}
          />
          <NavItem
            to="/review"
            icon={<ListChecks size={16} />}
            label="Review"
            badge={pendingReviewCount}
          />
        </nav>
      </div>
    </header>
  );
}
