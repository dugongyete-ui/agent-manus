"""Slides Tool - Logika untuk pembuatan presentasi."""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


class Slide:
    def __init__(self, title: str, content: str, layout: str = "title_content", notes: str = ""):
        self.title = title
        self.content = content
        self.layout = layout
        self.notes = notes
        self.images: list[str] = []

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "content": self.content,
            "layout": self.layout,
            "notes": self.notes,
            "images": self.images,
        }


class Presentation:
    def __init__(self, title: str, author: str = "", theme: str = "modern"):
        self.title = title
        self.author = author
        self.theme = theme
        self.slides: list[Slide] = []
        self.created_at = time.time()

    def add_slide(self, title: str, content: str, layout: str = "title_content", notes: str = "") -> Slide:
        slide = Slide(title=title, content=content, layout=layout, notes=notes)
        self.slides.append(slide)
        return slide

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "author": self.author,
            "theme": self.theme,
            "slides": [s.to_dict() for s in self.slides],
            "slide_count": len(self.slides),
        }


class SlidesTool:
    def __init__(self, output_dir: str = "data/presentations", default_template: str = "modern"):
        self.output_dir = output_dir
        self.default_template = default_template
        self.presentations: list[Presentation] = []
        os.makedirs(output_dir, exist_ok=True)

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        return (
            f"Slides tool siap. Intent: {intent}. "
            f"Operasi: create_presentation, add_slide, export."
        )

    def create_presentation(self, title: str, author: str = "", theme: Optional[str] = None) -> Presentation:
        pres = Presentation(title=title, author=author, theme=theme or self.default_template)
        self.presentations.append(pres)
        logger.info(f"Presentasi dibuat: '{title}'")
        return pres

    def add_slide_to_presentation(self, presentation: Presentation, title: str, content: str,
                                   layout: str = "title_content") -> Slide:
        slide = presentation.add_slide(title=title, content=content, layout=layout)
        logger.info(f"Slide ditambahkan: '{title}' ke presentasi '{presentation.title}'")
        return slide

    def generate_outline(self, topic: str, num_slides: int = 10) -> list[dict]:
        outline = [
            {"title": f"Judul: {topic}", "layout": "title"},
            {"title": "Pendahuluan", "layout": "title_content"},
            {"title": "Latar Belakang", "layout": "title_content"},
        ]
        for i in range(num_slides - 5):
            outline.append({"title": f"Poin {i + 1}", "layout": "title_content"})
        outline.append({"title": "Kesimpulan", "layout": "title_content"})
        outline.append({"title": "Terima Kasih", "layout": "title"})
        return outline

    def export_presentation(self, presentation: Presentation, filename: Optional[str] = None) -> str:
        if not filename:
            safe_title = presentation.title.replace(" ", "_").lower()
            filename = f"{safe_title}_{int(time.time())}.json"
        output_path = os.path.join(self.output_dir, filename)
        import json
        with open(output_path, "w") as f:
            json.dump(presentation.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Presentasi diekspor: {output_path}")
        return output_path

    def list_presentations(self) -> list[dict]:
        return [{"title": p.title, "slides": len(p.slides), "theme": p.theme} for p in self.presentations]
