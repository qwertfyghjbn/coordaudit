def read_file(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None
