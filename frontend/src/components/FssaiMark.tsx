import type { FssaiSymbol } from "../lib/types";

/**
 * India's official FSSAI packaging mark: a square outline containing either
 * a filled green circle (vegetarian) or a filled brown/maroon triangle
 * (non-vegetarian). Rendered faithfully — dot/triangle filling most of the
 * square's interior with even margins — rather than as a small generic icon,
 * since volunteers may recognize the real mark on sight.
 */
export function FssaiMark({ symbol, size = 20 }: { symbol: FssaiSymbol; size?: number }) {
  if (symbol === "none") return null;

  const isNonVeg = symbol === "brown_dot" || symbol === "red_triangle";
  const markColor = isNonVeg ? "#7B3F00" : "#00693E"; // brown/maroon vs. green

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      role="img"
      aria-label={isNonVeg ? "FSSAI non-vegetarian mark" : "FSSAI vegetarian mark"}
    >
      <rect x="2" y="2" width="20" height="20" fill="none" stroke={markColor} strokeWidth="2" />
      {isNonVeg ? (
        <polygon points="12,4 20,20 4,20" fill={markColor} />
      ) : (
        <circle cx="12" cy="12" r="8" fill={markColor} />
      )}
    </svg>
  );
}
