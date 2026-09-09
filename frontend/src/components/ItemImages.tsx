import { useEffect, useRef, useState, type MouseEvent } from "react";
import { ImageOff, RefreshCw, Image as ImageIcon } from "lucide-react";
import clsx from "clsx";
import { resolveImageUrl } from "../lib/api";
import { ImageLightbox } from "./ImageLightbox";

/**
 * A single photo tile that knows how to fail gracefully. Presigned S3 URLs
 * expire — if an item's detail was fetched a while ago and the image 404s
 * now, we don't want a broken-image icon; we want a placeholder with a way
 * to fetch a freshly generated URL (the backend regenerates one on every
 * read, so re-fetching the item is all `onRetry` needs to do).
 */
function Thumb({
  url,
  alt,
  onRetry,
  onClick,
  className,
}: {
  url: string;
  alt: string;
  onRetry?: () => void;
  onClick?: (e: MouseEvent) => void;
  className?: string;
}) {
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const imgRef = useRef<HTMLImageElement>(null);

  // The browser can have already fully loaded this exact URL before this
  // <img> even mounts — e.g. the same thumbnail_urls[0] shown moments
  // earlier as a compact card preview, now rendering again here. A cached
  // image can finish loading synchronously with the <img> being created,
  // so the onLoad/onError handlers below can end up attached AFTER the
  // browser already fired (and will never fire again) — leaving isLoading
  // stuck true forever (a permanent skeleton shimmer, not a broken-image
  // fallback). Checking .complete right after mount/url-change catches
  // that case; naturalWidth distinguishes an already-succeeded load from
  // an already-failed one (both leave .complete true).
  useEffect(() => {
    const img = imgRef.current;
    if (img?.complete) {
      setIsLoading(false);
      setHasError(img.naturalWidth === 0);
    } else {
      setIsLoading(true);
      setHasError(false);
    }
  }, [url]);

  if (hasError) {
    return (
      <div
        className={clsx(
          "flex flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-cream-300 bg-cream-100 px-2 text-center text-ink-700/50",
          className
        )}
      >
        <ImageOff size={18} />
        <span className="text-[10px] leading-tight">Photo unavailable</span>
        {onRetry && (
          <button
            onClick={onRetry}
            className="flex items-center gap-1 text-[11px] font-medium text-terracotta-600 hover:text-terracotta-700"
          >
            <RefreshCw size={10} />
            Refresh
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={clsx(
        "relative overflow-hidden rounded-xl border border-cream-300 bg-cream-100",
        onClick && !isLoading && "cursor-pointer",
        className
      )}
    >
      {isLoading && <div className="skeleton absolute inset-0" />}
      <img
        ref={imgRef}
        src={resolveImageUrl(url)}
        alt={alt}
        onClick={!isLoading ? onClick : undefined}
        className={clsx("h-full w-full object-cover transition-opacity", isLoading ? "opacity-0" : "opacity-100")}
        onLoad={() => setIsLoading(false)}
        onError={() => {
          setIsLoading(false);
          setHasError(true);
        }}
      />
    </div>
  );
}

/** Small square thumbnail — inventory list rows, scan result cards. */
export function ImageThumbnail({
  url,
  alt,
  onRetry,
  size = "h-16 w-16",
  images,
}: {
  url: string | undefined;
  alt: string;
  onRetry?: () => void;
  size?: string;
  /** Full set to step through in the lightbox, if the caller has it (e.g. a
   * list card showing only the first image but with the whole item on
   * hand). Falls back to just `url` alone when omitted. */
  images?: string[];
}) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  if (!url) {
    return (
      <div className={clsx("flex shrink-0 items-center justify-center rounded-xl border border-cream-300 bg-cream-100 text-ink-700/30", size)}>
        <ImageIcon size={18} />
      </div>
    );
  }

  const gallery = images && images.length > 0 ? images : [url];

  return (
    <>
      <Thumb
        url={url}
        alt={alt}
        onRetry={onRetry}
        className={clsx("shrink-0", size)}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setLightboxIndex(0);
        }}
      />
      {lightboxIndex !== null && (
        <ImageLightbox
          images={gallery}
          index={lightboxIndex}
          alt={alt}
          onIndexChange={setLightboxIndex}
          onClose={() => setLightboxIndex(null)}
        />
      )}
    </>
  );
}

/** Horizontal strip of larger photos — item detail, review queue cards. */
export function ImageGallery({
  urls,
  thumbnailUrls,
  alt,
  onRetry,
}: {
  /** Full-resolution originals — always what the lightbox opens, regardless
   * of what the strip itself is displaying. */
  urls: string[];
  /** Smaller variants for the strip display itself. Falls back to `urls`
   * when omitted or empty (e.g. items scanned before thumbnails existed,
   * or callers like the item detail page that intentionally always show
   * full originals in the strip). */
  thumbnailUrls?: string[];
  alt: string;
  onRetry?: () => void;
}) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const displayUrls = thumbnailUrls && thumbnailUrls.length > 0 ? thumbnailUrls : urls;

  if (urls.length === 0) {
    return (
      <div className="flex h-28 items-center justify-center gap-2 rounded-xl border border-dashed border-cream-300 bg-cream-100 text-xs text-ink-700/50">
        <ImageIcon size={16} />
        No photo captured
      </div>
    );
  }

  return (
    <>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {displayUrls.map((url, i) => (
          <Thumb
            key={`${url}-${i}`}
            url={url}
            alt={`${alt} ${i + 1}`}
            onRetry={onRetry}
            className="h-28 w-28 shrink-0 sm:h-36 sm:w-36"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setLightboxIndex(i);
            }}
          />
        ))}
      </div>
      {lightboxIndex !== null && (
        <ImageLightbox
          images={urls}
          index={lightboxIndex}
          alt={alt}
          onIndexChange={setLightboxIndex}
          onClose={() => setLightboxIndex(null)}
        />
      )}
    </>
  );
}
