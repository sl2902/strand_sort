"""
Generates the demo video's narration audio via Gemini TTS (Vertex AI) —
reuses the same Vertex client setup as GeminiExtractor
(strand_sort/vision/extract.py): vertexai=True, project/location from
Settings, local ADC only (this script only ever runs locally, never on
Lambda, so the Secrets-Manager credential branch GeminiExtractor needs for
Lambda doesn't apply here).

Narration text is duplicated here from demo_video_plan.md and
frontend/src/pages/DemoPage.tsx's per-step narrationCue strings — Python
can't import TS source directly, so if either changes, update the other
to match.

Output is WAV (Gemini TTS returns raw PCM; this wraps it in a standard
24kHz/16-bit/mono WAV container), written to frontend/public/demo/audio/.
Re-running overwrites cleanly — safe to tweak narration text and re-run.

Usage:
    uv run scripts/generate_demo_narration.py
"""
import wave
from pathlib import Path

from google import genai
from google.genai import types
from loguru import logger

from strand_sort.config import settings

TTS_MODEL = "gemini-3.1-flash-tts-preview"
VOICE_NAME = "Kore"
SAMPLE_RATE = 24000
SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "frontend" / "public" / "demo" / "audio"

# Keep in sync with demo_video_plan.md's script and DemoPage.tsx's
# per-step narrationCue strings. Split per /demo sequence step rather than
# one long pipeline-explainer clip — each step already auto-advances on
# its own timer (see DemoPage.tsx's STEPS), so a matching per-step clip is
# what actually lets the sequence be timed against real narration length,
# not a rough guess.
NARRATION: dict[str, str] = {
    "opening-pitch": (
        "Every day, food banks receive donations they can't move fast enough. "
        "Volunteers manually check expiry dates, decode nutrition labels, and "
        "guess at dietary categories — one item at a time. It's slow, "
        "error-prone, and it takes hours away from the work that actually "
        "matters: getting food to the people who need it. "
        "strand_sort is an autonomous AI agent, built on AWS Strands, that "
        "does this instantly. Point a camera at a donation, and the agent "
        "reads the label, verifies the expiry date, checks dietary and "
        "nutrition symbols straight off the packaging, and either adds it to "
        "inventory or flags it for a human to double-check — without a "
        "volunteer typing a single field. "
        "This matters because food banks run on volunteer hours, not "
        "headcount. Every minute saved sorting donations is a minute spent "
        "serving the community they exist for."
    ),
    "pipeline-intro": (
        "A photo or video goes in — strand_sort reads the label, "
        "cross-checks the expiry date, and pulls dietary and nutrition "
        "details straight from the packaging."
    ),
    "pipeline-inventory": "Clean items go straight to inventory.",
    "inventory-detail": (
        "Every item's full record is one tap away — the expiry date and "
        "how confident the read is, dietary and nutrition flags that show "
        "whether they came straight off the package or were inferred, and "
        "a distribute panel to track stock as it goes out the door."
    ),
    "pipeline-review": (
        "Anything uncertain — a low-confidence date, a damaged label — "
        "gets flagged for a quick human check instead of a risky guess."
    ),
    "pipeline-expiry": (
        "Expiry status is never stale — it's recalculated fresh every time "
        "an item is viewed."
    ),
    "handoff": "Now over to an actual demo.",
}


def get_client() -> genai.Client:
    logger.info("Using local ADC for GCP credentials")
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gemini_location or settings.gcp_location,
    )


def synthesize_and_save(client: genai.Client, script: str, output_path: Path) -> None:
    response = client.models.generate_content(
        model=TTS_MODEL,
        contents=script,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
                )
            ),
        ),
    )
    audio_data = response.candidates[0].content.parts[0].inline_data.data
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH_BYTES)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = get_client()

    for name, script in NARRATION.items():
        output_path = OUTPUT_DIR / f"{name}.wav"
        logger.info(f"Synthesizing {name!r} ({len(script)} chars)…")
        synthesize_and_save(client, script, output_path)
        size_kb = output_path.stat().st_size / 1024
        logger.info(f"Wrote {output_path.relative_to(REPO_ROOT)} ({size_kb:.0f} KB)")

    logger.info(f"Done — {len(NARRATION)} narration file(s) in {OUTPUT_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
