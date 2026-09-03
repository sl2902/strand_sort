"""Frame-sampling layer for video donation scans.

Volunteers panning a phone camera around an item produce a short video rather
than a handful of stills. This module samples a small number of frames spread
evenly across the clip (preferring the sharpest frame in each window, so
motion blur doesn't get sent to the vision model) and hands them back as
JPEG bytes — ready to feed into the same `get_extractor()` multi-image
pipeline that the still-image intake flow already uses. No changes to
`vision/extract.py` are needed.
"""

import cv2
import numpy as np
from loguru import logger


def _even_windows(total_frames: int, num_windows: int) -> list[tuple[int, int]]:
    """Splits [0, total_frames) into up to `num_windows` contiguous, evenly sized windows."""
    num_windows = max(1, min(num_windows, total_frames))
    edges = np.linspace(0, total_frames, num_windows + 1, dtype=int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(num_windows)]


def _window_for_index(frame_idx: int, windows: list[tuple[int, int]]) -> int | None:
    for i, (start, end) in enumerate(windows):
        if start <= frame_idx < end:
            return i
    # The final window's upper edge is exclusive elsewhere, but the very last
    # frame in the video legitimately belongs to the last window.
    if windows and frame_idx == windows[-1][1]:
        return len(windows) - 1
    return None


def _blur_score(frame: np.ndarray) -> float:
    """Variance of the Laplacian — higher means sharper/more in-focus."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _encode_jpeg(frame: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("Failed to JPEG-encode a sampled video frame")
    return buf.tobytes()


def extract_frames(video_path: str, max_frames: int = 4) -> list[bytes]:
    """
    Samples up to `max_frames` frames evenly spaced across a video's duration
    and returns them as JPEG-encoded bytes, ready for base64-encoding and
    handing to `get_extractor()`.

    Within each evenly-spaced sampling window, the sharpest frame (by
    Laplacian variance) is kept so a volunteer's panning motion blur doesn't
    get sent to the vision model.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")

    try:
        # CAP_PROP_FRAME_COUNT is only a hint for many codecs (esp. browser-recorded
        # webm/mp4), so we do a single sequential read pass rather than seeking —
        # random-access seeks are unreliable across containers/codecs.
        reported_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        windows = _even_windows(reported_total, max_frames) if reported_total > 0 else None

        best_by_window: list[tuple[float, np.ndarray | None]] = (
            [(-1.0, None)] * len(windows) if windows else []
        )
        buffered_frames: list[np.ndarray] = []  # used only when frame count is unknown upfront

        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if windows is not None:
                window_i = _window_for_index(frame_idx, windows)
                if window_i is not None:
                    score = _blur_score(frame)
                    if score > best_by_window[window_i][0]:
                        best_by_window[window_i] = (score, frame)
            else:
                buffered_frames.append(frame)

            frame_idx += 1

        if windows is None:
            if not buffered_frames:
                raise ValueError(f"No frames found in video: {video_path}")
            windows = _even_windows(len(buffered_frames), max_frames)
            best_by_window = [(-1.0, None)] * len(windows)
            for i, frame in enumerate(buffered_frames):
                window_i = _window_for_index(i, windows)
                if window_i is not None:
                    score = _blur_score(frame)
                    if score > best_by_window[window_i][0]:
                        best_by_window[window_i] = (score, frame)

        sampled_frames = [frame for _, frame in best_by_window if frame is not None]
        if not sampled_frames:
            raise ValueError(f"Could not extract any usable frames from video: {video_path}")

        logger.info(
            f"extract_frames: sampled {len(sampled_frames)}/{max_frames} frames "
            f"from {frame_idx} total frames in {video_path}"
        )
        return [_encode_jpeg(frame) for frame in sampled_frames]
    finally:
        cap.release()
