import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, Circle, Square, RotateCcw, Upload, ScanLine, FileVideo } from "lucide-react";
import clsx from "clsx";

const MAX_RECORD_SECONDS = 8;

function pickSupportedMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = [
    "video/webm;codecs=vp9,opus",
    "video/webm;codecs=vp8,opus",
    "video/webm",
    "video/mp4",
  ];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t));
}

function extensionForMimeType(mimeType: string): string {
  if (mimeType.includes("mp4")) return "mp4";
  return "webm";
}

export function VideoScanPanel({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (blob: Blob, filename: string) => void;
}) {
  const [subMode, setSubMode] = useState<"record" | "upload">("record");

  // --- Record sub-mode state ---
  const liveVideoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [cameraState, setCameraState] = useState<"idle" | "starting" | "live" | "error">("idle");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [recordedClip, setRecordedClip] = useState<{ blob: Blob; url: string } | null>(null);

  // --- Upload sub-mode state ---
  const [uploadedFile, setUploadedFile] = useState<{ file: File; previewUrl: string } | null>(null);

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraState("idle");
  };

  useEffect(() => stopCamera, []);

  useEffect(() => {
    if (subMode !== "record") stopCamera();
  }, [subMode]);

  useEffect(() => {
    if (!isRecording) return;
    setElapsed(0);
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [isRecording]);

  useEffect(() => {
    if (isRecording && elapsed >= MAX_RECORD_SECONDS) {
      recorderRef.current?.stop();
    }
  }, [elapsed, isRecording]);

  const startCamera = async () => {
    setCameraState("starting");
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      streamRef.current = stream;
      if (liveVideoRef.current) {
        liveVideoRef.current.srcObject = stream;
        await liveVideoRef.current.play();
      }
      setCameraState("live");
    } catch (err) {
      setCameraState("error");
      setCameraError(
        err instanceof Error ? err.message : "Couldn't access the camera. Check browser permissions."
      );
    }
  };

  const startRecording = () => {
    if (!streamRef.current) return;
    const mimeType = pickSupportedMimeType();
    const recorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : undefined);
    chunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mimeType ?? "video/webm" });
      setRecordedClip({ blob, url: URL.createObjectURL(blob) });
      setIsRecording(false);
      stopCamera();
    };
    recorderRef.current = recorder;
    recorder.start();
    setIsRecording(true);
  };

  const retake = () => {
    if (recordedClip) URL.revokeObjectURL(recordedClip.url);
    setRecordedClip(null);
    startCamera();
  };

  const submitRecorded = () => {
    if (!recordedClip) return;
    const ext = extensionForMimeType(recordedClip.blob.type);
    onSubmit(recordedClip.blob, `scan.${ext}`);
    URL.revokeObjectURL(recordedClip.url);
    setRecordedClip(null);
  };

  const submitUploaded = () => {
    if (!uploadedFile) return;
    onSubmit(uploadedFile.file, uploadedFile.file.name);
    URL.revokeObjectURL(uploadedFile.previewUrl);
    setUploadedFile(null);
  };

  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-xl bg-cream-200/70 p-1 text-sm">
        {(["record", "upload"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setSubMode(m)}
            className={clsx(
              "rounded-lg px-3.5 py-1.5 font-medium capitalize transition-colors",
              subMode === m ? "bg-cream-50 text-ink-900 shadow-soft" : "text-ink-700/70 hover:text-ink-900"
            )}
          >
            {m === "record" ? "Record" : "Upload file"}
          </button>
        ))}
      </div>

      {subMode === "record" && (
        <div className="space-y-3">
          <div className="relative aspect-video w-full overflow-hidden rounded-2xl border border-cream-300 bg-ink-900">
            {recordedClip ? (
              <video src={recordedClip.url} controls className="h-full w-full object-contain" />
            ) : (
              <video ref={liveVideoRef} muted playsInline className="h-full w-full object-cover" />
            )}

            {cameraState !== "live" && !recordedClip && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-cream-100">
                {cameraState === "error" ? (
                  <>
                    <CameraOff size={28} />
                    <p className="max-w-xs px-4 text-center text-sm text-cream-200/80">{cameraError}</p>
                  </>
                ) : (
                  <Camera size={28} className={cameraState === "starting" ? "animate-pulse" : ""} />
                )}
                <button
                  onClick={startCamera}
                  disabled={cameraState === "starting"}
                  className="rounded-xl bg-terracotta-500 px-4 py-2 text-sm font-semibold text-cream-50 shadow-soft hover:bg-terracotta-600 disabled:opacity-60"
                >
                  {cameraState === "starting" ? "Starting camera…" : "Start camera"}
                </button>
              </div>
            )}

            {isRecording && (
              <div className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-ink-900/70 px-2.5 py-1 text-xs font-semibold text-cream-50">
                <Circle size={8} className="fill-danger-500 text-danger-500 animate-pulse" />
                {elapsed}s / {MAX_RECORD_SECONDS}s
              </div>
            )}
          </div>

          {cameraState === "live" && !recordedClip && (
            <div className="flex justify-center gap-3">
              {!isRecording ? (
                <button
                  onClick={startRecording}
                  className="inline-flex items-center gap-2 rounded-xl bg-danger-500 px-5 py-2.5 text-sm font-semibold text-cream-50 shadow-soft hover:bg-danger-600"
                >
                  <Circle size={14} className="fill-current" />
                  Start recording
                </button>
              ) : (
                <button
                  onClick={() => recorderRef.current?.stop()}
                  className="inline-flex items-center gap-2 rounded-xl bg-ink-900 px-5 py-2.5 text-sm font-semibold text-cream-50 shadow-soft"
                >
                  <Square size={14} className="fill-current" />
                  Stop
                </button>
              )}
            </div>
          )}

          {recordedClip && (
            <div className="flex flex-wrap justify-center gap-3">
              <button
                onClick={retake}
                className="inline-flex items-center gap-2 rounded-xl border border-cream-300 bg-cream-50 px-4 py-2.5 text-sm font-medium text-ink-800 hover:bg-cream-100"
              >
                <RotateCcw size={15} />
                Retake
              </button>
              <button
                onClick={submitRecorded}
                disabled={disabled}
                className="inline-flex items-center gap-2 rounded-xl bg-terracotta-500 px-5 py-2.5 text-sm font-semibold text-cream-50 shadow-soft hover:bg-terracotta-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ScanLine size={16} />
                Scan this clip
              </button>
            </div>
          )}

          <p className="text-center text-xs text-ink-700/60">
            Pan slowly around the item — a few sharp angles beat a long shaky clip. Recording auto-stops after{" "}
            {MAX_RECORD_SECONDS}s.
          </p>
        </div>
      )}

      {subMode === "upload" && (
        <div className="space-y-3">
          {uploadedFile ? (
            <div className="aspect-video w-full overflow-hidden rounded-2xl border border-cream-300 bg-ink-900">
              <video src={uploadedFile.previewUrl} controls className="h-full w-full object-contain" />
            </div>
          ) : (
            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-cream-300 bg-cream-50/60 px-6 py-10 text-center hover:border-terracotta-300">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-terracotta-100 text-terracotta-600">
                <Upload size={22} />
              </div>
              <p className="text-sm font-medium text-ink-800">Choose a video file</p>
              <p className="text-xs text-ink-700/60">A short pan around the item works best</p>
              <input
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) setUploadedFile({ file, previewUrl: URL.createObjectURL(file) });
                }}
              />
            </label>
          )}

          {uploadedFile && (
            <div className="flex flex-wrap items-center justify-center gap-3">
              <p className="flex items-center gap-1.5 text-sm text-ink-700/70">
                <FileVideo size={15} />
                {uploadedFile.file.name}
              </p>
              <button
                onClick={() => {
                  URL.revokeObjectURL(uploadedFile.previewUrl);
                  setUploadedFile(null);
                }}
                className="text-sm font-medium text-ink-700/70 underline decoration-dotted hover:text-ink-900"
              >
                Choose different file
              </button>
              <button
                onClick={submitUploaded}
                disabled={disabled}
                className="inline-flex items-center gap-2 rounded-xl bg-terracotta-500 px-5 py-2.5 text-sm font-semibold text-cream-50 shadow-soft hover:bg-terracotta-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ScanLine size={16} />
                Scan this video
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
