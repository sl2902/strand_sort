import { useCallback, useRef, useState } from "react";
import { ImagePlus, X, ScanLine } from "lucide-react";
import clsx from "clsx";

interface StagedPhoto {
  file: File;
  previewUrl: string;
}

export function PhotoScanPanel({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (files: File[]) => void;
}) {
  const [staged, setStaged] = useState<StagedPhoto[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((fileList: FileList | File[]) => {
    const files = Array.from(fileList).filter((f) => f.type.startsWith("image/"));
    if (files.length === 0) return;
    setStaged((prev) => [...prev, ...files.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }))]);
  }, []);

  const removeAt = (index: number) => {
    setStaged((prev) => {
      const target = prev[index];
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  };

  const handleSubmit = () => {
    if (staged.length === 0) return;
    onSubmit(staged.map((s) => s.file));
    setStaged([]);
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        className={clsx(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          isDragOver ? "border-terracotta-500 bg-terracotta-50" : "border-cream-300 bg-cream-50/60 hover:border-terracotta-300"
        )}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-terracotta-100 text-terracotta-600">
          <ImagePlus size={22} />
        </div>
        <p className="text-sm font-medium text-ink-800">Drop photos here, or tap to browse</p>
        <p className="text-xs text-ink-700/60">Each photo is scanned as its own item — batch as many as you like</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {staged.length > 0 && (
        <div className="animate-fade-up">
          <div className="flex flex-wrap gap-3">
            {staged.map((s, i) => (
              <div key={s.previewUrl} className="group relative h-20 w-20 shrink-0">
                <img
                  src={s.previewUrl}
                  alt={s.file.name}
                  className="h-full w-full rounded-xl border border-cream-300 object-cover"
                />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeAt(i);
                  }}
                  className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-ink-900 text-cream-50 shadow-soft"
                  aria-label={`Remove ${s.file.name}`}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>

          <button
            onClick={handleSubmit}
            disabled={disabled}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-terracotta-500 px-5 py-3 text-sm font-semibold text-cream-50 shadow-soft transition-colors hover:bg-terracotta-600 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
          >
            <ScanLine size={16} />
            Scan {staged.length} item{staged.length === 1 ? "" : "s"}
          </button>
        </div>
      )}
    </div>
  );
}
