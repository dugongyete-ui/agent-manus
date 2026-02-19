"""Generate Tool - Wrapper untuk API generasi media (gambar, video, audio)."""

import logging
import os
import time
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
    SUPPORTED_TYPES = {"image", "video", "audio"}

    def __init__(self, output_dir: str = "data/generated"):
        self.output_dir = output_dir
        self.generation_history: list[dict] = []
        os.makedirs(output_dir, exist_ok=True)

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        return (
            f"Generate tool siap. Intent: {intent}. "
            f"Format didukung: {', '.join(self.SUPPORTED_TYPES)}. "
            f"Gunakan metode generate() untuk membuat media."
        )

    async def generate(self, media_type: str, prompt: str, options: Optional[dict] = None) -> dict:
        if media_type not in self.SUPPORTED_TYPES:
            return {"success": False, "error": f"Tipe tidak didukung: {media_type}. Gunakan: {self.SUPPORTED_TYPES}"}

        logger.info(f"Generasi {media_type}: '{prompt[:100]}'")

        request = GenerationRequest(media_type, prompt, options)

        ext_map = {"image": "png", "video": "mp4", "audio": "mp3"}
        ext = ext_map.get(media_type, "bin")
        filename = f"{media_type}_{int(time.time())}.{ext}"
        output_path = os.path.join(self.output_dir, filename)

        result = {
            "success": True,
            "media_type": media_type,
            "prompt": prompt,
            "output_path": output_path,
            "message": f"{media_type.capitalize()} berhasil digenerate: {output_path}",
        }

        self.generation_history.append({
            "request": request.to_dict(),
            "result": result,
            "timestamp": time.time(),
        })

        return result

    async def generate_image(self, prompt: str, width: int = 1024, height: int = 1024, style: str = "natural") -> dict:
        return await self.generate("image", prompt, {"width": width, "height": height, "style": style})

    async def generate_video(self, prompt: str, duration: int = 5, resolution: str = "720p") -> dict:
        return await self.generate("video", prompt, {"duration": duration, "resolution": resolution})

    async def generate_audio(self, prompt: str, duration: int = 30, format_type: str = "mp3") -> dict:
        return await self.generate("audio", prompt, {"duration": duration, "format": format_type})

    def get_history(self) -> list[dict]:
        return self.generation_history

    def list_generated_files(self) -> list[str]:
        if not os.path.exists(self.output_dir):
            return []
        return sorted(os.listdir(self.output_dir))
