import os

from app.common.io import read_file

BASE_DIR = "/var/www/files"


class DocumentService:
    def _resolve_safe_path(self, filename: str) -> str:
        clean = os.path.normpath(filename)
        if os.path.isabs(clean):
            raise ValueError("absolute path rejected")
        joined = os.path.join(BASE_DIR, clean)
        resolved = os.path.realpath(joined)
        real_base = os.path.realpath(BASE_DIR)
        if not resolved.startswith(real_base + os.sep):
            raise ValueError("path escape detected")
        return resolved

    def get_file_content(self, filename: str) -> bytes | None:
        try:
            safe_path = self._resolve_safe_path(filename)
        except ValueError:
            return None
        return read_file(safe_path)
