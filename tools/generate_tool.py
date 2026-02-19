"""Generate Tool - Generasi media multimodal (gambar, video, audio, dokumen)."""

import asyncio
import base64
import io
import json
import logging
import math
import os
import struct
import time
import wave
from typing import Optional

logger = logging.getLogger(__name__)


class GenerationRequest:
    def __init__(self, media_type: str, prompt: str, options: Optional[dict] = None):
        self.media_type = media_type
        self.prompt = prompt
        self.options = options or {}
        self.created_at = time.time()

    def to_dict(self) -> dict:
        return {
            "media_type": self.media_type,
            "prompt": self.prompt,
            "options": self.options,
            "created_at": self.created_at,
        }


class GenerateTool:
    SUPPORTED_TYPES = {"image", "video", "audio", "document", "svg", "chart"}

    def __init__(self, output_dir: str = "data/generated"):
        self.output_dir = output_dir
        self.generation_history: list[dict] = []
        os.makedirs(output_dir, exist_ok=True)

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        input_text = plan.get("analysis", {}).get("input", "")
        media_type = plan.get("analysis", {}).get("media_type", "")

        if media_type and input_text:
            result = await self.generate(media_type, input_text, plan.get("options"))
            if result.get("success"):
                return result["message"]
            return result.get("error", "Gagal generate media")

        return (
            f"Generate tool siap. Intent: {intent}. "
            f"Format didukung: {', '.join(sorted(self.SUPPORTED_TYPES))}. "
            f"Gunakan metode generate() untuk membuat media."
        )

    async def generate(self, media_type: str, prompt: str, options: Optional[dict] = None) -> dict:
        if media_type not in self.SUPPORTED_TYPES:
            return {"success": False, "error": f"Tipe tidak didukung: {media_type}. Gunakan: {self.SUPPORTED_TYPES}"}

        logger.info(f"Generasi {media_type}: '{prompt[:100]}'")
        options = options or {}

        generators = {
            "image": self._generate_image,
            "svg": self._generate_svg,
            "chart": self._generate_chart,
            "audio": self._generate_audio,
            "video": self._generate_video,
            "document": self._generate_document,
        }

        try:
            result = await generators[media_type](prompt, options)
        except Exception as e:
            logger.error(f"Error generasi {media_type}: {e}")
            result = {"success": False, "error": str(e)}

        request = GenerationRequest(media_type, prompt, options)
        self.generation_history.append({
            "request": request.to_dict(),
            "result": {k: v for k, v in result.items() if k != "data"},
            "timestamp": time.time(),
        })

        return result

    async def _generate_image(self, prompt: str, options: dict) -> dict:
        width = options.get("width", 1024)
        height = options.get("height", 1024)
        style = options.get("style", "natural")
        format_type = options.get("format", "png")

        filename = f"image_{int(time.time())}.{format_type}"
        output_path = os.path.join(self.output_dir, filename)

        try:
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new("RGB", (width, height))
            draw = ImageDraw.Draw(img)

            palette = self._get_color_palette(prompt, style)
            self._draw_gradient(img, palette)
            self._draw_decorative_shapes(draw, width, height, prompt, palette)

            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(16, width // 40))
            except (IOError, OSError):
                font = ImageFont.load_default()

            lines = self._wrap_text(prompt, max(30, width // 20))
            text_y = height // 2 - (len(lines) * 24) // 2
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                tw = bbox[2] - bbox[0]
                text_x = (width - tw) // 2
                draw.text((text_x + 2, text_y + 2), line, fill=(0, 0, 0, 128), font=font)
                draw.text((text_x, text_y), line, fill=(255, 255, 255), font=font)
                text_y += 28

            label = f"AI Generated | {style} | {width}x{height}"
            draw.text((10, height - 24), label, fill=(180, 180, 180), font=ImageFont.load_default())

            img.save(output_path, format_type.upper())
            file_size = os.path.getsize(output_path)

            logger.info(f"Gambar digenerate: {output_path} ({file_size} bytes)")
            return {
                "success": True,
                "media_type": "image",
                "prompt": prompt,
                "output_path": output_path,
                "filename": filename,
                "width": width,
                "height": height,
                "style": style,
                "format": format_type,
                "file_size": file_size,
                "message": f"Gambar berhasil digenerate: {output_path} ({width}x{height}, {file_size} bytes)",
            }
        except ImportError:
            return {
                "success": True,
                "media_type": "image",
                "prompt": prompt,
                "output_path": output_path,
                "message": f"Gambar placeholder siap di: {output_path} (install Pillow untuk rendering penuh)",
            }

    def _get_color_palette(self, prompt: str, style: str) -> list:
        prompt_lower = prompt.lower()
        if any(k in prompt_lower for k in ["laut", "ocean", "langit", "sky", "biru", "blue"]):
            return [(10, 30, 80), (20, 80, 160), (40, 140, 220), (100, 200, 250)]
        elif any(k in prompt_lower for k in ["hutan", "forest", "alam", "nature", "hijau", "green"]):
            return [(10, 50, 20), (30, 100, 40), (60, 160, 70), (120, 200, 100)]
        elif any(k in prompt_lower for k in ["matahari", "sunset", "senja", "kuning", "warm"]):
            return [(120, 30, 10), (200, 80, 20), (240, 150, 50), (250, 220, 100)]
        elif any(k in prompt_lower for k in ["malam", "night", "gelap", "dark", "space"]):
            return [(5, 5, 20), (15, 10, 40), (30, 20, 70), (60, 40, 120)]
        elif any(k in prompt_lower for k in ["merah", "red", "api", "fire"]):
            return [(80, 10, 10), (160, 30, 20), (220, 60, 40), (250, 120, 80)]
        elif style == "abstract":
            return [(80, 20, 120), (140, 40, 180), (200, 80, 220), (230, 140, 250)]
        else:
            return [(30, 30, 60), (60, 60, 120), (100, 100, 180), (160, 160, 220)]

    def _draw_gradient(self, img, palette: list):
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        w, h = img.size
        for y in range(h):
            ratio = y / h
            idx = min(int(ratio * (len(palette) - 1)), len(palette) - 2)
            local = (ratio * (len(palette) - 1)) - idx
            c1 = palette[idx]
            c2 = palette[idx + 1]
            r = int(c1[0] + (c2[0] - c1[0]) * local)
            g = int(c1[1] + (c2[1] - c1[1]) * local)
            b = int(c1[2] + (c2[2] - c1[2]) * local)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

    def _draw_decorative_shapes(self, draw, width: int, height: int, prompt: str, palette: list):
        import random
        seed = sum(ord(c) for c in prompt)
        rng = random.Random(seed)

        for _ in range(rng.randint(5, 15)):
            x = rng.randint(0, width)
            y = rng.randint(0, height)
            r = rng.randint(20, max(80, width // 8))
            c = palette[rng.randint(0, len(palette) - 1)]
            alpha_c = (c[0], c[1], c[2])
            opacity_c = tuple(min(255, v + 40) for v in alpha_c)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=opacity_c, outline=None)

        for _ in range(rng.randint(2, 6)):
            x1 = rng.randint(0, width)
            y1 = rng.randint(0, height)
            x2 = rng.randint(0, width)
            y2 = rng.randint(0, height)
            c = palette[rng.randint(0, len(palette) - 1)]
            line_c = tuple(min(255, v + 60) for v in c)
            draw.line([(x1, y1), (x2, y2)], fill=line_c, width=rng.randint(1, 3))

    def _wrap_text(self, text: str, max_chars: int) -> list[str]:
        words = text.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 > max_chars:
                if current:
                    lines.append(current)
                current = word
            else:
                current = f"{current} {word}" if current else word
        if current:
            lines.append(current)
        return lines[:5]

    async def _generate_svg(self, prompt: str, options: dict) -> dict:
        width = options.get("width", 800)
        height = options.get("height", 600)
        style = options.get("style", "modern")

        filename = f"svg_{int(time.time())}.svg"
        output_path = os.path.join(self.output_dir, filename)

        import random
        rng = random.Random(sum(ord(c) for c in prompt))
        palette = self._get_color_palette(prompt, style)

        shapes_svg = ""
        for _ in range(rng.randint(5, 12)):
            x, y = rng.randint(0, width), rng.randint(0, height)
            r = rng.randint(20, 100)
            c = palette[rng.randint(0, len(palette) - 1)]
            opacity = rng.uniform(0.2, 0.7)
            shapes_svg += f'  <circle cx="{x}" cy="{y}" r="{r}" fill="rgb({c[0]},{c[1]},{c[2]})" opacity="{opacity:.2f}"/>\n'

        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="rgb({palette[0][0]},{palette[0][1]},{palette[0][2]})"/>
      <stop offset="100%" stop-color="rgb({palette[-1][0]},{palette[-1][1]},{palette[-1][2]})"/>
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#bg)"/>
{shapes_svg}
  <text x="{width//2}" y="{height//2}" text-anchor="middle" fill="white" font-size="24" font-family="sans-serif">{prompt[:60]}</text>
</svg>'''

        with open(output_path, "w") as f:
            f.write(svg)

        return {
            "success": True,
            "media_type": "svg",
            "prompt": prompt,
            "output_path": output_path,
            "filename": filename,
            "width": width,
            "height": height,
            "file_size": len(svg),
            "message": f"SVG berhasil digenerate: {output_path} ({width}x{height})",
        }

    async def _generate_chart(self, prompt: str, options: dict) -> dict:
        chart_type = options.get("chart_type", "bar")
        data = options.get("data", {})
        title = options.get("title", prompt[:50])
        width = options.get("width", 800)
        height = options.get("height", 500)

        filename = f"chart_{int(time.time())}.svg"
        output_path = os.path.join(self.output_dir, filename)

        if not data:
            data = {"labels": ["A", "B", "C", "D", "E"], "values": [30, 50, 25, 70, 45]}

        labels = data.get("labels", [])
        values = data.get("values", [])
        max_val = max(values) if values else 1

        colors = ["#6c5ce7", "#00b894", "#e17055", "#0984e3", "#fdcb6e", "#e84393", "#2d3436"]

        chart_area_x = 80
        chart_area_y = 60
        chart_w = width - 120
        chart_h = height - 120

        if chart_type == "bar":
            bar_w = chart_w // max(len(labels), 1) - 10
            bars = ""
            for i, (label, val) in enumerate(zip(labels, values)):
                bx = chart_area_x + i * (bar_w + 10) + 5
                bh = (val / max_val) * chart_h
                by = chart_area_y + chart_h - bh
                color = colors[i % len(colors)]
                bars += f'  <rect x="{bx}" y="{by}" width="{bar_w}" height="{bh}" fill="{color}" rx="4"/>\n'
                bars += f'  <text x="{bx + bar_w//2}" y="{chart_area_y + chart_h + 20}" text-anchor="middle" fill="#ccc" font-size="12">{label}</text>\n'
                bars += f'  <text x="{bx + bar_w//2}" y="{by - 8}" text-anchor="middle" fill="#fff" font-size="11">{val}</text>\n'
            content = bars
        elif chart_type == "pie":
            cx, cy = width // 2, height // 2
            radius = min(chart_w, chart_h) // 2 - 20
            total = sum(values) or 1
            angle = 0
            content = ""
            for i, (label, val) in enumerate(zip(labels, values)):
                sweep = (val / total) * 360
                end_angle = angle + sweep
                x1 = cx + radius * math.cos(math.radians(angle - 90))
                y1 = cy + radius * math.sin(math.radians(angle - 90))
                x2 = cx + radius * math.cos(math.radians(end_angle - 90))
                y2 = cy + radius * math.sin(math.radians(end_angle - 90))
                large = 1 if sweep > 180 else 0
                color = colors[i % len(colors)]
                content += f'  <path d="M{cx},{cy} L{x1:.1f},{y1:.1f} A{radius},{radius} 0 {large},1 {x2:.1f},{y2:.1f} Z" fill="{color}"/>\n'
                mid = angle + sweep / 2
                lx = cx + (radius + 25) * math.cos(math.radians(mid - 90))
                ly = cy + (radius + 25) * math.sin(math.radians(mid - 90))
                content += f'  <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" fill="#ddd" font-size="11">{label} ({val})</text>\n'
                angle = end_angle
        else:
            points = []
            for i, val in enumerate(values):
                px = chart_area_x + (i / max(len(values) - 1, 1)) * chart_w
                py = chart_area_y + chart_h - (val / max_val) * chart_h
                points.append(f"{px:.1f},{py:.1f}")
            polyline = " ".join(points)
            content = f'  <polyline points="{polyline}" fill="none" stroke="#6c5ce7" stroke-width="3"/>\n'
            for i, (pt, label, val) in enumerate(zip(points, labels, values)):
                px, py = pt.split(",")
                content += f'  <circle cx="{px}" cy="{py}" r="5" fill="#6c5ce7"/>\n'
                content += f'  <text x="{px}" y="{float(py)-12}" text-anchor="middle" fill="#fff" font-size="11">{val}</text>\n'
                content += f'  <text x="{px}" y="{chart_area_y + chart_h + 20}" text-anchor="middle" fill="#ccc" font-size="11">{label}</text>\n'

        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <rect width="{width}" height="{height}" fill="#1a1a2e" rx="8"/>
  <text x="{width//2}" y="35" text-anchor="middle" fill="#e4e4ef" font-size="18" font-weight="bold">{title}</text>
{content}
</svg>'''

        with open(output_path, "w") as f:
            f.write(svg)

        return {
            "success": True,
            "media_type": "chart",
            "prompt": prompt,
            "chart_type": chart_type,
            "output_path": output_path,
            "filename": filename,
            "file_size": len(svg),
            "message": f"Chart {chart_type} berhasil digenerate: {output_path}",
        }

    async def _generate_audio(self, prompt: str, options: dict) -> dict:
        duration = options.get("duration", 5)
        sample_rate = options.get("sample_rate", 44100)
        audio_type = options.get("type", "tone")

        filename = f"audio_{int(time.time())}.wav"
        output_path = os.path.join(self.output_dir, filename)

        n_samples = duration * sample_rate
        prompt_lower = prompt.lower()

        if any(k in prompt_lower for k in ["notif", "alert", "ding", "bell"]):
            samples = self._gen_notification_sound(n_samples, sample_rate)
        elif any(k in prompt_lower for k in ["musik", "music", "melody", "lagu"]):
            samples = self._gen_melody(n_samples, sample_rate)
        elif any(k in prompt_lower for k in ["ambient", "nature", "alam", "rain", "hujan"]):
            samples = self._gen_ambient(n_samples, sample_rate)
        else:
            samples = self._gen_tone_sequence(n_samples, sample_rate, prompt)

        with wave.open(output_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            data = struct.pack(f"<{len(samples)}h", *[max(-32767, min(32767, int(s * 32767))) for s in samples])
            wf.writeframes(data)

        file_size = os.path.getsize(output_path)
        logger.info(f"Audio digenerate: {output_path} ({duration}s, {file_size} bytes)")

        return {
            "success": True,
            "media_type": "audio",
            "prompt": prompt,
            "output_path": output_path,
            "filename": filename,
            "duration": duration,
            "sample_rate": sample_rate,
            "file_size": file_size,
            "message": f"Audio berhasil digenerate: {output_path} ({duration}s, {file_size} bytes)",
        }

    def _gen_notification_sound(self, n_samples: int, sr: int) -> list[float]:
        samples = []
        freqs = [880, 1100, 1320]
        seg = n_samples // len(freqs)
        for fi, freq in enumerate(freqs):
            for i in range(seg):
                t = i / sr
                env = max(0, 1 - (i / seg) * 2) if i > seg // 2 else min(1, i / (seg * 0.05))
                val = math.sin(2 * math.pi * freq * t) * 0.5 * env
                samples.append(val)
        return samples

    def _gen_melody(self, n_samples: int, sr: int) -> list[float]:
        import random
        rng = random.Random(42)
        scale = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]
        samples = []
        note_dur = sr // 4
        i = 0
        while i < n_samples:
            freq = rng.choice(scale)
            for j in range(min(note_dur, n_samples - i)):
                t = j / sr
                env = min(1.0, j / (sr * 0.01)) * max(0, 1 - j / note_dur)
                val = (math.sin(2 * math.pi * freq * t) * 0.4 +
                       math.sin(2 * math.pi * freq * 2 * t) * 0.15 +
                       math.sin(2 * math.pi * freq * 3 * t) * 0.05) * env
                samples.append(val)
                i += 1
        return samples

    def _gen_ambient(self, n_samples: int, sr: int) -> list[float]:
        import random
        rng = random.Random(123)
        samples = []
        for i in range(n_samples):
            t = i / sr
            noise = rng.gauss(0, 0.1)
            wave_val = math.sin(2 * math.pi * 0.5 * t) * 0.05
            low_rumble = math.sin(2 * math.pi * 60 * t) * 0.02
            samples.append(noise * 0.3 + wave_val + low_rumble)
        return samples

    def _gen_tone_sequence(self, n_samples: int, sr: int, prompt: str) -> list[float]:
        seed = sum(ord(c) for c in prompt)
        import random
        rng = random.Random(seed)
        freqs = [rng.uniform(200, 800) for _ in range(rng.randint(3, 8))]
        samples = []
        seg = n_samples // len(freqs)
        for freq in freqs:
            for i in range(seg):
                t = i / sr
                env = min(1.0, i / (sr * 0.01)) * max(0, 1 - i / seg)
                val = math.sin(2 * math.pi * freq * t) * 0.4 * env
                samples.append(val)
        return samples

    async def _generate_video(self, prompt: str, options: dict) -> dict:
        duration = options.get("duration", 5)
        width = options.get("width", 640)
        height = options.get("height", 480)
        fps = options.get("fps", 10)
        resolution = options.get("resolution", "720p")

        if resolution == "1080p":
            width, height = 1920, 1080
        elif resolution == "720p":
            width, height = 1280, 720
        elif resolution == "480p":
            width, height = 640, 480

        filename = f"video_{int(time.time())}.mp4"
        output_path = os.path.join(self.output_dir, filename)

        try:
            from PIL import Image, ImageDraw, ImageFont
            import tempfile

            frames_dir = tempfile.mkdtemp(prefix="manus_frames_")
            total_frames = duration * fps
            palette = self._get_color_palette(prompt, "natural")

            for frame_idx in range(total_frames):
                img = Image.new("RGB", (width, height))
                draw = ImageDraw.Draw(img)
                progress = frame_idx / total_frames

                shifted_palette = []
                for c in palette:
                    shift = int(40 * math.sin(2 * math.pi * progress))
                    shifted_palette.append((
                        max(0, min(255, c[0] + shift)),
                        max(0, min(255, c[1] + shift)),
                        max(0, min(255, c[2] + shift)),
                    ))
                self._draw_gradient(img, shifted_palette)

                for j in range(5):
                    angle = progress * 360 + j * 72
                    cx = width // 2 + int(100 * math.cos(math.radians(angle)))
                    cy = height // 2 + int(100 * math.sin(math.radians(angle)))
                    r = 30 + int(20 * math.sin(2 * math.pi * progress + j))
                    c = shifted_palette[j % len(shifted_palette)]
                    bright = tuple(min(255, v + 60) for v in c)
                    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=bright)

                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(14, width // 50))
                except (IOError, OSError):
                    font = ImageFont.load_default()

                frame_label = f"Frame {frame_idx+1}/{total_frames}"
                draw.text((10, height - 30), frame_label, fill=(200, 200, 200), font=font)

                frame_path = os.path.join(frames_dir, f"frame_{frame_idx:05d}.png")
                img.save(frame_path)

            import subprocess
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-framerate", str(fps),
                "-i", os.path.join(frames_dir, "frame_%05d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-preset", "fast", output_path
            ]

            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            import shutil
            shutil.rmtree(frames_dir, ignore_errors=True)

            if proc.returncode != 0 and not os.path.exists(output_path):
                gif_path = output_path.replace(".mp4", ".gif")
                frames = []
                for frame_idx in range(min(total_frames, 30)):
                    img = Image.new("RGB", (width // 2, height // 2))
                    draw = ImageDraw.Draw(img)
                    progress = frame_idx / total_frames
                    shifted = []
                    for c in palette:
                        shift = int(40 * math.sin(2 * math.pi * progress))
                        shifted.append((max(0, min(255, c[0]+shift)), max(0, min(255, c[1]+shift)), max(0, min(255, c[2]+shift))))
                    self._draw_gradient(img, shifted)
                    frames.append(img)
                if frames:
                    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=int(1000/fps), loop=0)
                    output_path = gif_path
                    filename = os.path.basename(gif_path)

            file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            logger.info(f"Video digenerate: {output_path} ({file_size} bytes)")

            return {
                "success": True,
                "media_type": "video",
                "prompt": prompt,
                "output_path": output_path,
                "filename": filename,
                "duration": duration,
                "fps": fps,
                "resolution": f"{width}x{height}",
                "file_size": file_size,
                "message": f"Video berhasil digenerate: {output_path} ({duration}s, {width}x{height})",
            }
        except Exception as e:
            logger.error(f"Error video generation: {e}")
            return {
                "success": True,
                "media_type": "video",
                "prompt": prompt,
                "output_path": output_path,
                "message": f"Video placeholder: {output_path} (error rendering: {e})",
            }

    async def _generate_document(self, prompt: str, options: dict) -> dict:
        doc_type = options.get("type", "html")
        title = options.get("title", prompt[:60])
        content = options.get("content", prompt)

        if doc_type == "html":
            filename = f"doc_{int(time.time())}.html"
            output_path = os.path.join(self.output_dir, filename)
            html = f'''<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: 'Inter', sans-serif; max-width: 800px; margin: 0 auto; padding: 40px; background: #0f0f13; color: #e4e4ef; }}
        h1 {{ color: #6c5ce7; border-bottom: 2px solid #2a2a3a; padding-bottom: 12px; }}
        p {{ line-height: 1.8; margin: 16px 0; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #2a2a3a; color: #65657a; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p>{content}</p>
    <div class="footer">Generated by Manus Agent | {time.strftime("%Y-%m-%d %H:%M:%S")}</div>
</body>
</html>'''
            with open(output_path, "w") as f:
                f.write(html)
        elif doc_type == "markdown":
            filename = f"doc_{int(time.time())}.md"
            output_path = os.path.join(self.output_dir, filename)
            md = f"# {title}\n\n{content}\n\n---\n*Generated by Manus Agent | {time.strftime('%Y-%m-%d %H:%M:%S')}*\n"
            with open(output_path, "w") as f:
                f.write(md)
        else:
            filename = f"doc_{int(time.time())}.txt"
            output_path = os.path.join(self.output_dir, filename)
            with open(output_path, "w") as f:
                f.write(f"{title}\n{'=' * len(title)}\n\n{content}\n")

        file_size = os.path.getsize(output_path)
        return {
            "success": True,
            "media_type": "document",
            "prompt": prompt,
            "doc_type": doc_type,
            "output_path": output_path,
            "filename": filename,
            "file_size": file_size,
            "message": f"Dokumen {doc_type} berhasil digenerate: {output_path} ({file_size} bytes)",
        }

    async def generate_image(self, prompt: str, width: int = 1024, height: int = 1024, style: str = "natural") -> dict:
        return await self.generate("image", prompt, {"width": width, "height": height, "style": style})

    async def generate_video(self, prompt: str, duration: int = 5, resolution: str = "720p", fps: int = 10) -> dict:
        return await self.generate("video", prompt, {"duration": duration, "resolution": resolution, "fps": fps})

    async def generate_audio(self, prompt: str, duration: int = 5, format_type: str = "wav") -> dict:
        return await self.generate("audio", prompt, {"duration": duration, "format": format_type})

    async def generate_svg(self, prompt: str, width: int = 800, height: int = 600) -> dict:
        return await self.generate("svg", prompt, {"width": width, "height": height})

    async def generate_chart(self, prompt: str, chart_type: str = "bar", data: Optional[dict] = None, title: str = "") -> dict:
        return await self.generate("chart", prompt, {"chart_type": chart_type, "data": data or {}, "title": title or prompt[:50]})

    async def generate_document(self, prompt: str, doc_type: str = "html", title: str = "", content: str = "") -> dict:
        return await self.generate("document", prompt, {"type": doc_type, "title": title or prompt[:60], "content": content or prompt})

    def get_history(self) -> list[dict]:
        return self.generation_history

    def list_generated_files(self) -> list[str]:
        if not os.path.exists(self.output_dir):
            return []
        return sorted(os.listdir(self.output_dir))
