import os

BASE_DIR = "/var/www/files"


def read_file(filename: str) -> bytes | None:
    file_path = os.path.join(BASE_DIR, filename)
    try:
        with open(file_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None
