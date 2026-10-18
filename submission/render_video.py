"""Build an honestly labeled narrated draft from real UI captures and the deck."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pymupdf
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
MEDIA = HERE / "media"


def main():
    MEDIA.mkdir(exist_ok=True)
    document = pymupdf.open(HERE / "Kairos-AI-Proposal.pdf")
    for index in range(6):
        document[index].get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0)).save(MEDIA / f"slide-{index + 1}.png")
    document.close()
    scenes = [
        ("slide-1.png", "Agentic reliability on Google Cloud | Synthetic data | No real equipment control", 16),
        ("slide-2.png", "The problem: diagnosis is the bottleneck, not detection", 20),
        ("slide-3.png", "Onboard, learn (RAG), ask the device, analyze live or historic", 36),
        ("slide-4.png", "Cloud Run + Gemini on Vertex AI + Vertex embeddings + Firestore + BigQuery", 30),
        ("slide-5.png", "Datasheet-driven monitoring | One engine, live and historic | Honest by design", 30),
        ("slide-6.png", "No production savings claimed | 121 tests | Next: engineer-validated pilot", 18),
    ]
    font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 28)
    frames = []
    for index, (filename, caption, seconds) in enumerate(scenes):
        source = MEDIA / filename
        if not source.exists():
            raise FileNotFoundError(f"Missing real screenshot: {source}")
        image = Image.open(source).convert("RGB")
        image.thumbnail((1440, 830))
        frame = Image.new("RGB", (1440, 900), "#102338")
        frame.paste(image, ((1440 - image.width) // 2, 0))
        draw = ImageDraw.Draw(frame)
        draw.text((30, 850), caption, fill="#42dcc4", font=font)
        path = MEDIA / f"frame-{index:02d}.png"
        frame.save(path)
        frames.append((path, seconds))
    manifest = MEDIA / "frames.txt"
    text = "".join(f"file '{path.name}'\nduration {seconds}\n" for path, seconds in frames)
    text += f"file '{frames[-1][0].name}'\n"
    manifest.write_text(text, encoding="utf-8")
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg and ffprobe are required to render the draft.")
    narration = MEDIA / "narration.wav"
    if not narration.exists():
        raise FileNotFoundError("Generate narration.wav with Windows System.Speech first.")
    duration = float(subprocess.check_output(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(narration)],
        text=True,
    ))
    # Keep the complete narration in a 165-second draft rather than truncating it.
    tempo = max(duration / 164, 1)
    if tempo > 2:
        raise ValueError("Narration is too long; shorten the script.")
    output = HERE / "Kairos-AI-Demo.mp4"
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(manifest), "-i", str(narration), "-af", f"atempo={tempo:.5f},apad",
        "-c:v", "libx264", "-preset", "fast", "-crf", "24", "-r", "24",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-t", "165", "-movflags", "+faststart", str(output),
    ], check=True, timeout=180)
    info = json.loads(subprocess.check_output(
        [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output)], text=True,
    ))
    if not 0 < float(info["format"]["duration"]) < 180:
        raise RuntimeError("Video does not meet the strictly-under-three-minute requirement.")
    print(f"Generated {output} | duration={info['format']['duration']} | narration originally {duration:.1f}s")


if __name__ == "__main__":
    main()
