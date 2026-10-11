from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"
HOST = os.environ.get("SHORTS_STUDIO_HOST", "127.0.0.1")
PORT = int(os.environ.get("SHORTS_STUDIO_PORT", "8765"))
WIDTH, HEIGHT = 720, 1280
MAX_PROMPT_LENGTH = 600
MAX_SCENES = 8
STYLE_LABELS = {"pov": "POV", "story": "AI Story", "cartoon": "AI Cartoon", "satisfying": "Satisfying", "cinematic": "Cinematic"}

def clean_text(value: object, limit: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:limit]

def make_storyboard(prompt: str, style: str = "story", duration: int = 30) -> dict:
    prompt = clean_text(prompt, MAX_PROMPT_LENGTH)
    if not prompt:
        raise ValueError("Please enter a video idea or prompt.")
    if style not in STYLE_LABELS:
        raise ValueError("Choose a supported video style.")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 10 <= duration <= 60:
        raise ValueError("Duration must be between 10 and 60 seconds.")
    subject = prompt.rstrip(".!? ")
    short_subject = subject[:100]
    beats = {
        "pov": [("THE HOOK", f"You wake up and realize: {short_subject}"), ("THE TWIST", "One small detail changes everything."), ("THE CHOICE", "You have seconds to decide what happens next."), ("THE PAYOFF", "Would you make the same choice?")],
        "story": [("THE HOOK", f"What if {short_subject.lower()}?"), ("THE SETUP", "At first, everything seems normal."), ("THE TURN", "Then an unexpected clue changes the story."), ("THE PAYOFF", "The final detail makes the beginning mean something new.")],
        "cartoon": [("MEET THE HERO", f"Our hero faces a problem: {short_subject}"), ("THE PLAN", "A clever idea sounds perfect on paper."), ("CHAOS", "The plan goes hilariously off track."), ("THE END", "A tiny surprise saves the day.")],
        "satisfying": [("THE TEASE", f"Watch this: {short_subject}"), ("THE BUILD", "Everything lines up, one precise move at a time."), ("THE MOMENT", "A clean, close-up transformation."), ("THE LOOP", "A final frame that makes you want to watch again.")],
        "cinematic": [("OPENING IMAGE", f"In a world shaped by {short_subject.lower()}..."), ("THE CONFLICT", "A quiet warning arrives too late."), ("THE REVEAL", "The camera finds the detail nobody noticed."), ("THE LAST SHOT", "The scene ends on a question, not an answer.")],
    }
    base, remainder = divmod(duration, 4)
    scenes = [{"id": i + 1, "heading": heading, "text": line, "duration": base + (1 if i < remainder else 0)} for i, (heading, line) in enumerate(beats[style])]
    return {"title": subject[:68] or "Untitled Short", "style": style, "style_label": STYLE_LABELS[style], "duration": duration, "aspect_ratio": "9:16", "scenes": scenes, "notice": "Starter storyboard: review and edit every scene before publishing."}

def safe_project_title(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", clean_text(title, 60)).strip("-_")[:50] or "short"

def find_font(size: int, bold: bool = False):
    windir = os.environ.get("WINDIR")
    candidates = []
    if windir:
        candidates += [str(Path(windir) / "Fonts" / ("arialbd.ttf" if bold else "arial.ttf")), str(Path(windir) / "Fonts" / ("segoeuib.ttf" if bold else "segoeui.ttf"))]
    candidates.append("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    for candidate in candidates:
        try:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()

def wrap_words(draw, text: str, font, max_width: int):
    lines, current = [], ""
    for word in clean_text(text, 240).split():
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:7]

def draw_scene(scene: dict, style_label: str, scene_count: int, destination: Path):
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    top, bottom = (12, 19, 39), (53, 28, 86)
    for y in range(HEIGHT):
        t = y / max(1, HEIGHT - 1)
        rgb = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(WIDTH):
            pixels[x, y] = rgb
    draw = ImageDraw.Draw(image)
    margin = 56
    draw.rounded_rectangle((margin, 52, WIDTH-margin, 110), radius=24, fill=(33, 54, 87))
    draw.text((margin+20, 66), f"SHORTS STUDIO / {style_label.upper()}", font=find_font(24, True), fill=(174, 226, 255))
    draw.rounded_rectangle((margin, 150, margin+7, 240), radius=4, fill=(79, 214, 190))
    draw.text((margin+26, 168), clean_text(scene.get("heading", "SCENE"), 70).upper(), font=find_font(31, True), fill=(124, 239, 216))
    lines = wrap_words(draw, str(scene.get("text", "")), find_font(44, True), WIDTH-2*margin)
    y = max(310, (HEIGHT-len(lines)*62)//2)
    for line in lines:
        draw.text((margin, y), line, font=find_font(44, True), fill=(249, 250, 255))
        y += 62
    draw.line((margin, HEIGHT-132, WIDTH-margin, HEIGHT-132), fill=(86, 104, 139), width=2)
    draw.text((margin, HEIGHT-105), f"SCENE {scene['id']:02d} / {scene_count:02d}", font=find_font(22), fill=(176, 190, 216))
    draw.text((WIDTH-margin-145, HEIGHT-105), "9:16  •  720p", font=find_font(22), fill=(176, 190, 216))
    image.save(destination, format="PNG", optimize=True)

def render_video(project: dict) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg was not found. Install FFmpeg, add it to PATH, and restart PowerShell.")
    scenes = project.get("scenes")
    if not isinstance(scenes, list) or not scenes or len(scenes) > MAX_SCENES:
        raise ValueError(f"Project must contain 1 to {MAX_SCENES} scenes.")
    total, normalized = 0, []
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ValueError("Each scene must be an object.")
        heading, text = clean_text(scene.get("heading"), 70), clean_text(scene.get("text"), 240)
        duration = scene.get("duration", 5)
        if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 20:
            raise ValueError("Each scene duration must be an integer from 1 to 20 seconds.")
        if not text:
            raise ValueError("Every scene needs text.")
        total += duration
        normalized.append({"id": i+1, "heading": heading or f"SCENE {i+1}", "text": text, "duration": duration})
    if total > 60:
        raise ValueError("Total video duration cannot exceed 60 seconds.")
    style = project.get("style", "story")
    if style not in STYLE_LABELS:
        style = "story"
    title = safe_project_title(str(project.get("title", "short")))
    job_id = uuid.uuid4().hex[:10]
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    concat_file = job_dir / "concat.txt"
    for i, scene in enumerate(normalized):
        draw_scene(scene, STYLE_LABELS[style], len(normalized), job_dir / f"scene-{i:02d}.png")
    lines = []
    for i, scene in enumerate(normalized):
        filename = (job_dir / f"scene-{i:02d}.png").as_posix().replace("'", r"\'\''")
        lines += [f"file '{filename}'", f"duration {scene['duration']}"]
    last = (job_dir / f"scene-{len(normalized)-1:02d}.png").as_posix().replace("'", r"\'\''")
    lines.append(f"file '{last}'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output_path = OUTPUT_DIR / f"{title}-{job_id}.mp4"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", str(output_path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=240, check=False)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg render failed: " + (result.stderr[-1200:] or "unknown error"))
        if not output_path.exists() or output_path.stat().st_size < 1024:
            raise RuntimeError("Render finished but the output MP4 is missing or unexpectedly small.")
        return output_path
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

class Handler(BaseHTTPRequestHandler):
    server_version = "ShortsStudio/0.1"
    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
    def _json(self, status: int, data: dict):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._json(200, {"ok": True, "app": "Shorts Studio", "version": "0.1.0"})
        if path == "/":
            return self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path.startswith("/output/"):
            name = Path(path).name
            if not name.endswith(".mp4") or name != path.removeprefix("/output/"):
                return self._json(404, {"error": "Not found"})
            file_path = OUTPUT_DIR / name
            if not file_path.is_file():
                return self._json(404, {"error": "Video not found"})
            return self._send(200, file_path.read_bytes(), "video/mp4")
        return self._json(404, {"error": "Not found"})
    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/storyboard", "/api/render"):
            return self._json(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 24000:
                return self._json(413, {"error": "Request body must be between 2 bytes and 24 KB."})
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                return self._json(400, {"error": "Expected a JSON object."})
            if path == "/api/storyboard":
                duration = data.get("duration", 30)
                if isinstance(duration, str) and duration.isdigit():
                    duration = int(duration)
                return self._json(200, make_storyboard(data.get("prompt", ""), data.get("style", "story"), duration))
            output = render_video(data)
            return self._json(200, {"ok": True, "filename": output.name, "url": "/output/" + output.name, "bytes": output.stat().st_size})
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._json(400, {"error": "Invalid JSON request."})
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})
        except (RuntimeError, subprocess.SubprocessError) as exc:
            return self._json(500, {"error": str(exc)})
        except Exception:
            return self._json(500, {"error": "Unexpected server error. Check the PowerShell window for details."})
    def log_message(self, fmt, *args):
        if args and len(args) >= 2 and str(args[1]).startswith("5"):
            super().log_message(fmt, *args)

def main():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Shorts Studio is running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop. Local-only by default; do not expose this server to the internet.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Shorts Studio...")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
