import type { ReactNode } from "react";
import { Leaf, Sprout, WheatOff, Droplets, Candy, Beef } from "lucide-react";
import type { DietaryFlags, FssaiSymbol } from "../lib/types";
import { Badge } from "./Badge";
import { SourceDot } from "./SourceTag";
import { FssaiMark } from "./FssaiMark";

/** Compact at-a-glance row of dietary badges — used in list/card views. */
export function DietaryBadgeRow({ flags, fssaiSymbol }: { flags: DietaryFlags; fssaiSymbol?: FssaiSymbol }) {
  const badges: { key: string; node: ReactNode }[] = [];

  if (flags.is_vegetarian === true) {
    badges.push({
      key: "veg",
      node: (
        <Badge key="veg" tone="success" icon={<Leaf size={12} />} title="Vegetarian">
          Veg
        </Badge>
      ),
    });
  } else if (flags.is_vegetarian === false) {
    badges.push({
      key: "nonveg",
      node: (
        <Badge key="nonveg" tone="danger" icon={<Beef size={12} />} title="Non-vegetarian">
          Non-Veg
        </Badge>
      ),
    });
  }
  if (flags.is_vegan) {
    badges.push({
      key: "vegan",
      node: (
        <Badge key="vegan" tone="success" icon={<Sprout size={12} />} title="Vegan">
          Vegan
        </Badge>
      ),
    });
  }
  if (flags.is_gluten_free) {
    badges.push({
      key: "gf",
      node: (
        <Badge key="gf" tone="saffron" icon={<WheatOff size={12} />} title="Gluten-free">
          GF
        </Badge>
      ),
    });
  }
  if (flags.is_low_sugar) {
    badges.push({
      key: "sugar",
      node: (
        <Badge key="sugar" tone="plum" icon={<Candy size={12} />} title="Low sugar">
          Low Sugar
        </Badge>
      ),
    });
  }
  if (flags.is_low_sodium) {
    badges.push({
      key: "sodium",
      node: (
        <Badge key="sodium" tone="terracotta" icon={<Droplets size={12} />} title="Low sodium">
          Low Sodium
        </Badge>
      ),
    });
  }

  const hasMark = !!fssaiSymbol && fssaiSymbol !== "none";

  if (badges.length === 0 && !hasMark) {
    return <span className="text-xs text-ink-700/50 italic">No dietary info</span>;
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {hasMark && <FssaiMark symbol={fssaiSymbol!} size={18} />}
      {badges.map((b) => b.node)}
    </div>
  );
}

/** Full dietary breakdown for the item detail view, each row tagged with its source. */
export function DietaryDetailList({ flags, fssaiSymbol }: { flags: DietaryFlags; fssaiSymbol?: FssaiSymbol }) {
  const rows: { label: string; value: string; source: string; positive: boolean }[] = [
    {
      label: "Vegetarian",
      value: flags.is_vegetarian === null ? "Unknown" : flags.is_vegetarian ? "Yes" : "No",
      source: flags.is_vegetarian_source,
      positive: flags.is_vegetarian === true,
    },
    {
      label: "Vegan",
      value: flags.is_vegan ? "Yes" : "No",
      source: flags.other_flags_source,
      positive: flags.is_vegan,
    },
    {
      label: "Gluten-free",
      value: flags.is_gluten_free ? "Yes" : "No",
      source: flags.other_flags_source,
      positive: flags.is_gluten_free,
    },
    {
      label: "Low sugar",
      value: flags.is_low_sugar ? "Yes" : "No",
      source: flags.is_low_sugar_source,
      positive: flags.is_low_sugar,
    },
    {
      label: "Low sodium",
      value: flags.is_low_sodium ? "Yes" : "No",
      source: flags.is_low_sodium_source,
      positive: flags.is_low_sodium,
    },
  ];

  return (
    <dl className="divide-y divide-cream-200">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center justify-between gap-3 py-2.5">
          <dt className="text-sm text-ink-700">{row.label}</dt>
          <dd className="flex items-center gap-2">
            {row.label === "Vegetarian" && fssaiSymbol && fssaiSymbol !== "none" && (
              <FssaiMark symbol={fssaiSymbol} size={20} />
            )}
            <span className={`text-sm font-medium ${row.positive ? "text-success-600" : "text-ink-800"}`}>
              {row.value}
            </span>
            <SourceDot source={row.source} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
