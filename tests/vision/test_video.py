import cv2
import numpy as np
import pytest

from strand_sort.vision.video import extract_frames


def _make_video(path: str, num_frames: int = 20, size: tuple[int, int] = (64, 64), fps: int = 10) -> None:
    """Writes a synthetic video where every 5th frame is 'sharp' (random noise,
    high Laplacian variance) and the rest are flat/blurry (low variance), so
    tests can assert the sharp frames get picked."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, size)
    rng = np.random.default_rng(42)
    for i in range(num_frames):
        if i % 5 == 0:
            frame = rng.integers(0, 255, (*size, 3), dtype=np.uint8)
        else:
            frame = np.full((*size, 3), 128, dtype=np.uint8)
        writer.write(frame)
    writer.release()


@pytest.fixture
def sample_video(tmp_path):
    video_path = str(tmp_path / "sample.mp4")
    _make_video(video_path)
    return video_path


def test_extract_frames_returns_requested_count(sample_video):
    frames = extract_frames(sample_video, max_frames=4)
    assert len(frames) == 4


def test_extract_frames_returns_valid_jpeg_bytes(sample_video):
    frames = extract_frames(sample_video, max_frames=3)
    for frame_bytes in frames:
        assert isinstance(frame_bytes, bytes)
        decoded = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded is not None
        assert decoded.shape[:2] == (64, 64)


def test_extract_frames_prefers_sharper_frame_per_window(sample_video):
    # 20 frames, max_frames=4 -> windows of 5 frames each, sharp frame (noise)
    # is frame index 0 of each window -> every window should pick it over the flat frames.
    frames = extract_frames(sample_video, max_frames=4)
    for frame_bytes in frames:
        decoded = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        assert variance > 10  # flat/gray frames have ~0 variance; noisy ones are much higher


def test_extract_frames_missing_file_raises():
    with pytest.raises(ValueError):
        extract_frames("/nonexistent/path/video.mp4", max_frames=4)


def test_extract_frames_max_frames_capped_by_video_length(tmp_path):
    video_path = str(tmp_path / "short.mp4")
    _make_video(video_path, num_frames=2)
    frames = extract_frames(video_path, max_frames=4)
    assert 1 <= len(frames) <= 2


_real_video_capture = cv2.VideoCapture  # captured before any monkeypatching below


class _LyingFrameCountCapture:
    """Wraps a real cv2.VideoCapture but misreports CAP_PROP_FRAME_COUNT —
    simulates what browser-recorded webm/mp4 does in production (the bug
    this class exists to catch): the hint underclaims the real frame count
    by a wide margin, everything else behaves normally."""

    def __init__(self, path: str, lie_as: int):
        self._real = _real_video_capture(path)  # not cv2.VideoCapture — that's the patched name
        self._lie_as = lie_as

    def isOpened(self):
        return self._real.isOpened()

    def get(self, prop_id):
        if prop_id == cv2.CAP_PROP_FRAME_COUNT:
            return self._lie_as
        return self._real.get(prop_id)

    def read(self):
        return self._real.read()

    def release(self):
        self._real.release()


def test_extract_frames_survives_unreliable_frame_count_hint(sample_video, monkeypatch):
    """The reported bug: only one distinct angle was ever captured despite
    filming a multi-angle pan. CAP_PROP_FRAME_COUNT reporting far fewer
    frames than actually exist (observed for browser-recorded webm/mp4)
    used to collapse every sampling window down to the video's first
    fraction of a second. 20 real frames, hint lies and says there's only
    1 — sampling must still span the whole clip, not just frame 0-1."""
    monkeypatch.setattr(
        "strand_sort.vision.video.cv2.VideoCapture",
        lambda path: _LyingFrameCountCapture(path, lie_as=1),
    )
    frames = extract_frames(sample_video, max_frames=4)
    assert len(frames) == 4
