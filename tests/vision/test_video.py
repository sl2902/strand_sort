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
