# --- summarizer.py ---
def summarize(text: str, max_length: int = 300) -> str:
    if not text:
        return "⚠️ Пост порожній."
    return text[:max_length] + "..." if len(text) > max_length else text

