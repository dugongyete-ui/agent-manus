"""File Tool - Operasi sistem file dengan pemahaman dokumen multimodal."""

import base64
import io
import json
import logging
import mimetypes
import os
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

BLOCKED_PATHS = {"/etc/shadow", "/etc/passwd", "/proc", "/sys"}

SUPPORTED_DOC_TYPES = {
    "pdf": [".pdf"],
    "image": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff"],
    "audio": [".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"],
    "video": [".mp4", ".avi", ".mkv", ".mov", ".webm", ".flv", ".wmv"],
    "document": [".doc", ".docx", ".xls", ".xlsx", ".pptx", ".odt", ".ods"],
    "data": [".csv", ".json", ".xml", ".yaml", ".yml", ".toml"],
    "code": [".py", ".js", ".ts", ".html", ".css", ".java", ".go", ".rs", ".cpp", ".c", ".rb", ".php"],
    "text": [".txt", ".md", ".rst", ".log"],
}


def _detect_media_category(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    for category, extensions in SUPPORTED_DOC_TYPES.items():
        if ext in extensions:
            return category
    return "unknown"


class FileTool:
    def __init__(self, base_dir: str = ".", max_file_size_mb: int = 100):
        self.base_dir = base_dir
        self.max_file_size_mb = max_file_size_mb

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        input_text = plan.get("analysis", {}).get("input", "")
        return (
            f"File tool siap. Intent: {intent}. "
            f"Operasi file tersedia: read, write, edit, append, view, list, delete, copy, move, analyze, extract_pdf, extract_image_info."
        )

    def _validate_path(self, path: str) -> str:
        abs_path = os.path.abspath(path)
        for blocked in BLOCKED_PATHS:
            if abs_path.startswith(blocked):
                raise PermissionError(f"Akses ditolak ke path: {abs_path}")
        return abs_path

    def read_file(self, path: str, encoding: str = "utf-8") -> str:
        abs_path = self._validate_path(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File tidak ditemukan: {abs_path}")
        file_size = os.path.getsize(abs_path) / (1024 * 1024)
        if file_size > self.max_file_size_mb:
            raise ValueError(f"File terlalu besar: {file_size:.1f}MB (maks: {self.max_file_size_mb}MB)")
        with open(abs_path, "r", encoding=encoding) as f:
            content = f.read()
        logger.info(f"File dibaca: {abs_path} ({len(content)} karakter)")
        return content

    def read_binary(self, path: str) -> bytes:
        abs_path = self._validate_path(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File tidak ditemukan: {abs_path}")
        file_size = os.path.getsize(abs_path) / (1024 * 1024)
        if file_size > self.max_file_size_mb:
            raise ValueError(f"File terlalu besar: {file_size:.1f}MB")
        with open(abs_path, "rb") as f:
            return f.read()

    def write_file(self, path: str, content: str, encoding: str = "utf-8") -> str:
        abs_path = self._validate_path(path)
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        with open(abs_path, "w", encoding=encoding) as f:
            f.write(content)
        logger.info(f"File ditulis: {abs_path} ({len(content)} karakter)")
        return f"File berhasil ditulis: {abs_path}"

    def write_binary(self, path: str, data: bytes) -> str:
        abs_path = self._validate_path(path)
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(data)
        logger.info(f"File biner ditulis: {abs_path} ({len(data)} bytes)")
        return f"File biner berhasil ditulis: {abs_path}"

    def append_file(self, path: str, content: str, encoding: str = "utf-8") -> str:
        abs_path = self._validate_path(path)
        with open(abs_path, "a", encoding=encoding) as f:
            f.write(content)
        logger.info(f"Konten ditambahkan ke: {abs_path}")
        return f"Konten berhasil ditambahkan ke: {abs_path}"

    def edit_file(self, path: str, old_text: str, new_text: str, encoding: str = "utf-8") -> str:
        abs_path = self._validate_path(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File tidak ditemukan: {abs_path}")
        with open(abs_path, "r", encoding=encoding) as f:
            content = f.read()
        if old_text not in content:
            return f"Teks '{old_text[:50]}...' tidak ditemukan dalam file {abs_path}"
        new_content = content.replace(old_text, new_text, 1)
        with open(abs_path, "w", encoding=encoding) as f:
            f.write(new_content)
        logger.info(f"File diedit: {abs_path}")
        return f"File berhasil diedit: {abs_path}"

    def view_file(self, path: str, start_line: int = 1, end_line: Optional[int] = None, encoding: str = "utf-8") -> str:
        abs_path = self._validate_path(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File tidak ditemukan: {abs_path}")
        with open(abs_path, "r", encoding=encoding) as f:
            lines = f.readlines()
        total_lines = len(lines)
        start = max(0, start_line - 1)
        end = min(total_lines, end_line) if end_line else min(total_lines, start + 50)
        selected = lines[start:end]
        output_lines = []
        for i, line in enumerate(selected, start=start + 1):
            output_lines.append(f"{i:4d} | {line.rstrip()}")
        header = f"--- {abs_path} (baris {start + 1}-{end} dari {total_lines}) ---"
        return header + "\n" + "\n".join(output_lines)

    def delete_file(self, path: str) -> str:
        abs_path = self._validate_path(path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)
            logger.info(f"File dihapus: {abs_path}")
            return f"File berhasil dihapus: {abs_path}"
        elif os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
            logger.info(f"Direktori dihapus: {abs_path}")
            return f"Direktori berhasil dihapus: {abs_path}"
        raise FileNotFoundError(f"Path tidak ditemukan: {abs_path}")

    def list_directory(self, path: str = ".") -> list[dict]:
        abs_path = self._validate_path(path)
        if not os.path.isdir(abs_path):
            raise NotADirectoryError(f"Bukan direktori: {abs_path}")
        entries = []
        for entry in sorted(os.listdir(abs_path)):
            full_path = os.path.join(abs_path, entry)
            info = {
                "name": entry,
                "type": "directory" if os.path.isdir(full_path) else "file",
                "size": os.path.getsize(full_path) if os.path.isfile(full_path) else 0,
            }
            if os.path.isfile(full_path):
                info["media_category"] = _detect_media_category(full_path)
            entries.append(info)
        return entries

    def copy_file(self, src: str, dst: str) -> str:
        src_path = self._validate_path(src)
        dst_path = self._validate_path(dst)
        os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)
        logger.info(f"Disalin: {src_path} -> {dst_path}")
        return f"Berhasil disalin: {src_path} -> {dst_path}"

    def move_file(self, src: str, dst: str) -> str:
        src_path = self._validate_path(src)
        dst_path = self._validate_path(dst)
        os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
        shutil.move(src_path, dst_path)
        logger.info(f"Dipindahkan: {src_path} -> {dst_path}")
        return f"Berhasil dipindahkan: {src_path} -> {dst_path}"

    def file_exists(self, path: str) -> bool:
        return os.path.exists(self._validate_path(path))

    def get_file_info(self, path: str) -> dict:
        abs_path = self._validate_path(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Path tidak ditemukan: {abs_path}")
        stat = os.stat(abs_path)
        mime_type, _ = mimetypes.guess_type(abs_path)
        return {
            "path": abs_path,
            "size": stat.st_size,
            "size_human": self._human_size(stat.st_size),
            "is_file": os.path.isfile(abs_path),
            "is_dir": os.path.isdir(abs_path),
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
            "extension": os.path.splitext(abs_path)[1].lower(),
            "mime_type": mime_type,
            "media_category": _detect_media_category(abs_path),
        }

    def _human_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def analyze_file(self, path: str) -> dict:
        abs_path = self._validate_path(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File tidak ditemukan: {abs_path}")

        info = self.get_file_info(path)
        category = info["media_category"]

        analysis = {
            "file_info": info,
            "category": category,
        }

        analyzers = {
            "pdf": self._analyze_pdf,
            "image": self._analyze_image,
            "audio": self._analyze_audio,
            "data": self._analyze_data,
            "code": self._analyze_code,
            "text": self._analyze_text,
        }

        analyzer = analyzers.get(category)
        if analyzer:
            try:
                extra = analyzer(abs_path)
                analysis.update(extra)
            except Exception as e:
                analysis["analysis_error"] = str(e)
                logger.warning(f"Error analisis {category} {abs_path}: {e}")

        return analysis

    def _analyze_pdf(self, path: str) -> dict:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(path)
            total_pages = len(reader.pages)

            text_content = []
            for i, page in enumerate(reader.pages[:10]):
                text = page.extract_text() or ""
                text_content.append({"page": i + 1, "text": text[:2000]})

            metadata = {}
            if reader.metadata:
                for key in ["/Title", "/Author", "/Subject", "/Creator", "/Producer"]:
                    val = reader.metadata.get(key)
                    if val:
                        metadata[key.strip("/")] = str(val)

            return {
                "pdf_info": {
                    "total_pages": total_pages,
                    "metadata": metadata,
                    "is_encrypted": reader.is_encrypted,
                },
                "extracted_text": text_content,
                "total_text_length": sum(len(p["text"]) for p in text_content),
            }
        except ImportError:
            return {"error": "PyPDF2 tidak terinstall. Install dengan: pip install PyPDF2"}
        except Exception as e:
            return {"error": f"Gagal membaca PDF: {e}"}

    def _analyze_image(self, path: str) -> dict:
        result = {"image_info": {}}

        try:
            from PIL import Image
            with Image.open(path) as img:
                result["image_info"] = {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "has_transparency": img.mode in ("RGBA", "LA", "PA"),
                    "is_animated": getattr(img, "is_animated", False),
                    "n_frames": getattr(img, "n_frames", 1),
                }

                if img.info:
                    safe_info = {}
                    for k, v in img.info.items():
                        if isinstance(v, (str, int, float, bool)):
                            safe_info[k] = v
                        elif isinstance(v, bytes) and len(v) < 200:
                            safe_info[k] = v.hex()
                    result["image_metadata"] = safe_info

                histogram = img.histogram()
                if histogram:
                    total_pixels = img.width * img.height
                    brightness = sum(i * v for i, v in enumerate(histogram[:256])) / max(total_pixels, 1)
                    result["image_stats"] = {
                        "brightness": round(brightness, 1),
                        "brightness_level": "gelap" if brightness < 85 else "sedang" if brightness < 170 else "terang",
                        "total_pixels": total_pixels,
                        "megapixels": round(total_pixels / 1_000_000, 2),
                    }

                if img.width <= 512 and img.height <= 512:
                    buf = io.BytesIO()
                    thumb = img.copy()
                    thumb.thumbnail((128, 128))
                    thumb.save(buf, format="PNG")
                    result["thumbnail_base64"] = base64.b64encode(buf.getvalue()).decode("utf-8")

        except ImportError:
            result["error"] = "Pillow tidak terinstall"
        except Exception as e:
            result["error"] = f"Gagal analisis gambar: {e}"

        return result

    def _analyze_audio(self, path: str) -> dict:
        result = {"audio_info": {}}

        try:
            import mutagen
            audio = mutagen.File(path)
            if audio is not None:
                result["audio_info"] = {
                    "duration_seconds": round(audio.info.length, 2) if hasattr(audio.info, "length") else None,
                    "sample_rate": getattr(audio.info, "sample_rate", None),
                    "channels": getattr(audio.info, "channels", None),
                    "bitrate": getattr(audio.info, "bitrate", None),
                    "format": type(audio).__name__,
                }
                if audio.tags:
                    tags = {}
                    for key in list(audio.tags.keys())[:20]:
                        val = audio.tags.get(key)
                        if val:
                            tags[str(key)] = str(val)[:200]
                    result["audio_tags"] = tags
        except ImportError:
            result["error"] = "mutagen tidak terinstall"
        except Exception as e:
            result["error"] = f"Gagal analisis audio: {e}"

        ext = os.path.splitext(path)[1].lower()
        if ext == ".wav":
            try:
                import wave
                with wave.open(path, "r") as wf:
                    result["wav_info"] = {
                        "channels": wf.getnchannels(),
                        "sample_width": wf.getsampwidth(),
                        "framerate": wf.getframerate(),
                        "n_frames": wf.getnframes(),
                        "duration_seconds": round(wf.getnframes() / wf.getframerate(), 2),
                    }
            except Exception:
                pass

        return result

    def _analyze_data(self, path: str) -> dict:
        ext = os.path.splitext(path)[1].lower()

        if ext == ".csv":
            return self._analyze_csv(path)
        elif ext == ".json":
            return self._analyze_json(path)
        elif ext in (".yaml", ".yml"):
            return self._analyze_yaml(path)
        elif ext == ".xml":
            return self._analyze_xml(path)

        return {}

    def _analyze_csv(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            total_rows = len(lines)
            headers = lines[0].strip().split(",") if lines else []
            sample_rows = [l.strip().split(",") for l in lines[1:6]]
            return {
                "csv_info": {
                    "total_rows": total_rows,
                    "columns": len(headers),
                    "headers": headers[:50],
                    "sample_data": sample_rows,
                }
            }
        except Exception as e:
            return {"error": f"Gagal analisis CSV: {e}"}

    def _analyze_json(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            info = {"json_type": type(data).__name__}
            if isinstance(data, list):
                info["total_items"] = len(data)
                if data:
                    info["sample_item"] = str(data[0])[:500]
            elif isinstance(data, dict):
                info["keys"] = list(data.keys())[:50]
                info["total_keys"] = len(data)
            return {"json_info": info}
        except Exception as e:
            return {"error": f"Gagal analisis JSON: {e}"}

    def _analyze_yaml(self, path: str) -> dict:
        try:
            with open(path, "r") as f:
                content = f.read()
            return {"yaml_preview": content[:2000], "yaml_size": len(content)}
        except Exception as e:
            return {"error": f"Gagal analisis YAML: {e}"}

    def _analyze_xml(self, path: str) -> dict:
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(path)
            root = tree.getroot()
            return {
                "xml_info": {
                    "root_tag": root.tag,
                    "children_count": len(list(root)),
                    "child_tags": list(set(child.tag for child in root))[:20],
                }
            }
        except Exception as e:
            return {"error": f"Gagal analisis XML: {e}"}

    def _analyze_code(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            lines = content.splitlines()
            code_lines = [l for l in lines if l.strip() and not l.strip().startswith(("#", "//", "/*", "*", "'''", '"""'))]
            ext = os.path.splitext(path)[1].lower()

            import re
            functions = []
            classes = []

            if ext in (".py",):
                functions = re.findall(r"def\s+(\w+)\s*\(", content)
                classes = re.findall(r"class\s+(\w+)", content)
            elif ext in (".js", ".ts"):
                functions = re.findall(r"(?:function|const|let|var)\s+(\w+)\s*(?:=\s*(?:async\s+)?(?:\([^)]*\)\s*=>|\([^)]*\)\s*\{)|[\s(])", content)
                classes = re.findall(r"class\s+(\w+)", content)
            elif ext in (".java", ".go", ".rs", ".cpp", ".c"):
                functions = re.findall(r"(?:func|fn|void|int|string|bool)\s+(\w+)\s*\(", content)
                classes = re.findall(r"(?:class|struct|interface)\s+(\w+)", content)

            imports = re.findall(r"(?:import|from|require|use)\s+(.+?)(?:\n|;)", content)

            return {
                "code_info": {
                    "language": ext.lstrip("."),
                    "total_lines": len(lines),
                    "code_lines": len(code_lines),
                    "blank_lines": len([l for l in lines if not l.strip()]),
                    "functions": functions[:30],
                    "classes": classes[:20],
                    "imports": [i.strip() for i in imports[:20]],
                }
            }
        except Exception as e:
            return {"error": f"Gagal analisis kode: {e}"}

    def _analyze_text(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            lines = content.splitlines()
            words = content.split()
            return {
                "text_info": {
                    "total_lines": len(lines),
                    "total_words": len(words),
                    "total_chars": len(content),
                    "preview": content[:1000],
                }
            }
        except Exception as e:
            return {"error": f"Gagal analisis teks: {e}"}

    def extract_pdf_text(self, path: str, pages: Optional[list[int]] = None) -> dict:
        abs_path = self._validate_path(path)
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(abs_path)
            total = len(reader.pages)

            target_pages = pages if pages else list(range(total))

            extracted = []
            for i in target_pages:
                if 0 <= i < total:
                    text = reader.pages[i].extract_text() or ""
                    extracted.append({"page": i + 1, "text": text})

            full_text = "\n\n".join(p["text"] for p in extracted)

            return {
                "success": True,
                "total_pages": total,
                "extracted_pages": len(extracted),
                "pages": extracted,
                "full_text": full_text,
                "text_length": len(full_text),
            }
        except ImportError:
            return {"success": False, "error": "PyPDF2 tidak terinstall"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_image_info(self, path: str) -> dict:
        abs_path = self._validate_path(path)
        return self._analyze_image(abs_path)

    def get_image_base64(self, path: str, max_size: int = 512) -> dict:
        abs_path = self._validate_path(path)
        try:
            from PIL import Image
            with Image.open(abs_path) as img:
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size))
                if img.mode == "RGBA":
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                return {
                    "success": True,
                    "base64": b64,
                    "width": img.width,
                    "height": img.height,
                    "mime_type": "image/jpeg",
                    "size_bytes": len(buf.getvalue()),
                }
        except ImportError:
            return {"success": False, "error": "Pillow tidak terinstall"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_files(self, directory: str, pattern: str, recursive: bool = True) -> list[dict]:
        import fnmatch
        abs_dir = self._validate_path(directory)
        results = []

        if recursive:
            for root, dirs, files in os.walk(abs_dir):
                for name in files:
                    if fnmatch.fnmatch(name.lower(), pattern.lower()):
                        full_path = os.path.join(root, name)
                        results.append({
                            "name": name,
                            "path": full_path,
                            "size": os.path.getsize(full_path),
                            "media_category": _detect_media_category(full_path),
                        })
        else:
            for entry in os.listdir(abs_dir):
                if fnmatch.fnmatch(entry.lower(), pattern.lower()):
                    full_path = os.path.join(abs_dir, entry)
                    if os.path.isfile(full_path):
                        results.append({
                            "name": entry,
                            "path": full_path,
                            "size": os.path.getsize(full_path),
                            "media_category": _detect_media_category(full_path),
                        })

        return results[:100]

    def get_directory_tree(self, path: str = ".", max_depth: int = 3, show_hidden: bool = False) -> str:
        abs_path = self._validate_path(path)
        lines = []
        self._build_tree(abs_path, "", max_depth, 0, lines, show_hidden)
        return "\n".join(lines[:500])

    def _build_tree(self, path: str, prefix: str, max_depth: int, depth: int, lines: list, show_hidden: bool):
        if depth > max_depth:
            return
        name = os.path.basename(path) or path
        if os.path.isdir(path):
            lines.append(f"{prefix}{name}/")
            try:
                entries = sorted(os.listdir(path))
                if not show_hidden:
                    entries = [e for e in entries if not e.startswith(".")]
                for i, entry in enumerate(entries[:50]):
                    is_last = i == len(entries) - 1
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    connector = "└── " if is_last else "├── "
                    child_path = os.path.join(path, entry)
                    if os.path.isdir(child_path):
                        self._build_tree(child_path, prefix + connector, max_depth, depth + 1, lines, show_hidden)
                    else:
                        size = os.path.getsize(child_path)
                        lines.append(f"{prefix}{connector}{entry} ({self._human_size(size)})")
            except PermissionError:
                lines.append(f"{prefix}    [akses ditolak]")
        else:
            size = os.path.getsize(path)
            lines.append(f"{prefix}{name} ({self._human_size(size)})")
