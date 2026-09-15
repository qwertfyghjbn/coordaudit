from app.common.storage import read_file


class FileService:
    def get_file_content(self, filename: str) -> bytes | None:
        return read_file(filename)
