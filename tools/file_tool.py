"""File Tool - Wrapper untuk operasi sistem file."""

import logging
import os
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

BLOCKED_PATHS = {"/etc/shadow", "/etc/passwd", "/proc", "/sys"}


class FileTool:
    def __init__(self, base_dir: str = ".", max_file_size_mb: int = 100):
        self.base_dir = base_dir
        self.max_file_size_mb = max_file_size_mb

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        input_text = plan.get("analysis", {}).get("input", "")
        return f"File tool siap. Intent: {intent}. Operasi file tersedia: read, write, edit, append, view, list, delete, copy, move."

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

    def write_file(self, path: str, content: str, encoding: str = "utf-8") -> str:
        abs_path = self._validate_path(path)
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        with open(abs_path, "w", encoding=encoding) as f:
            f.write(content)
        logger.info(f"File ditulis: {abs_path} ({len(content)} karakter)")
        return f"File berhasil ditulis: {abs_path}"

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
        return {
            "path": abs_path,
            "size": stat.st_size,
            "is_file": os.path.isfile(abs_path),
            "is_dir": os.path.isdir(abs_path),
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
        }
