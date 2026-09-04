import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X, ChevronLeft, ChevronRight } from "lucide-react";
import { resolveImageUrl } from "../lib/api";

/**
 * Full-size image viewer, shared by every place a thumbnail appears (Scan
 * result cards, Inventory list/detail, Review queue). Portaled to
 * document.body so it always sits above whatever scroll/overflow/transform
 * context its trigger happens to live inside.
 */
export function ImageLightbox({
  images,
  index,
  alt,
  onClose,
  onIndexChange,
}: {
  images: string[];
  index: number;
  alt: string;
  onClose: () => void;
  onIndexChange: (index: number) => void;
}) {
  const hasMultiple = images.length > 1;
  const goPrev = () => onIndexChange((index - 1 + images.length) % images.length);
  const goNext = () => onIndexChange((index + 1) % images.length);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && hasMultiple) goPrev();
      if (e.key === "ArrowRight" && hasMultiple) goNext();
    };
    window.addEventListener("keydown", onKeyDown);

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, hasMultiple]);

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-ink-900/80 p-4 backdrop-blur-sm animate-fade-up"
      onClick={(e) => {
        // This backdrop is the root of the portaled subtree — unlike every
        // button below (shielded by the inner div's own stopPropagation), a
        // click here has no DOM ancestor within the portal to catch it, so
        // an unstopped click would cross the portal boundary and reach
        // whatever this component is logically nested inside in the React
        // tree (e.g. a card wrapped in a <Link>), triggering navigation
        // just from dismissing the lightbox.
        e.stopPropagation();
        onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={alt}
    >
      <div className="relative max-h-full max-w-3xl" onClick={(e) => e.stopPropagation()}>
        <img
          src={resolveImageUrl(images[index])}
          alt={alt}
          className="max-h-[80vh] w-auto rounded-2xl object-contain shadow-lift"
        />

        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute -right-3 -top-3 flex h-9 w-9 items-center justify-center rounded-full bg-cream-50 text-ink-900 shadow-lift transition-colors hover:bg-cream-100"
        >
          <X size={18} />
        </button>

        {hasMultiple && (
          <>
            <button
              onClick={goPrev}
              aria-label="Previous image"
              className="absolute left-2 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-cream-50/90 text-ink-900 shadow-lift transition-colors hover:bg-cream-50"
            >
              <ChevronLeft size={20} />
            </button>
            <button
              onClick={goNext}
              aria-label="Next image"
              className="absolute right-2 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-cream-50/90 text-ink-900 shadow-lift transition-colors hover:bg-cream-50"
            >
              <ChevronRight size={20} />
            </button>
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-ink-900/70 px-3 py-1 text-xs font-medium text-cream-50">
              {index + 1} / {images.length}
            </div>
          </>
        )}
      </div>
    </div>,
    document.body
  );
}
