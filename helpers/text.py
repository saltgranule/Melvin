def truncate(text: str, length: int) -> str:
    return text[: length - 3] + "..." if len(text) > length else text
