import { PackageCheck, Sparkles, CircleHelp, CircleSlash } from "lucide-react";
import { Badge } from "./Badge";

/**
 * Distinguishes data read directly off the package (printed symbol / nutrition
 * panel) from data the model inferred from general category knowledge. This
 * is a real trust signal for volunteers, not incidental — keep it visible.
 */
export function SourceTag({ source }: { source: string }) {
  if (source === "printed_symbol" || source === "printed_panel") {
    return (
      <Badge tone="success" icon={<PackageCheck size={12} />} title="Read directly from the package">
        From package
      </Badge>
    );
  }
  if (source === "inferred") {
    return (
      <Badge tone="saffron" icon={<Sparkles size={12} />} title="Inferred from general product knowledge, not printed on the package">
        Inferred
      </Badge>
    );
  }
  if (source === "unavailable") {
    // Deliberately neither the "from package" green nor the "inferred"
    // orange — a panel was found but this specific value wasn't captured,
    // so neither a verified reading nor a category guess actually happened.
    return (
      <Badge tone="neutral" icon={<CircleSlash size={12} />} title="A nutrition panel was found, but this value wasn't captured">
        Unavailable
      </Badge>
    );
  }
  return (
    <Badge tone="neutral" icon={<CircleHelp size={12} />} title="Not found on the package">
      Not found
    </Badge>
  );
}

/** Same distinction, compact form (a small dot) for dense list rows. */
export function SourceDot({ source }: { source: string }) {
  const isPrinted = source === "printed_symbol" || source === "printed_panel";
  const isInferred = source === "inferred";
  return (
    <span
      title={isPrinted ? "Read from package" : isInferred ? "Inferred" : source === "unavailable" ? "Unavailable" : "Not found"}
      className={`inline-block h-2 w-2 rounded-full ${
        isPrinted ? "bg-success-500" : isInferred ? "bg-saffron-400" : "bg-cream-300"
      }`}
    />
  );
}
