from pathlib import Path


class KnowledgeBase:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def search(self, query: str, limit: int = 3) -> list[str]:
        if not self.root.exists():
            return []

        query_terms = {term for term in query.lower().split() if term}
        scored: list[tuple[int, str]] = []
        for path in self.root.rglob("*.txt"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            score = sum(1 for term in query_terms if term in text.lower())
            if score > 0 or not query_terms:
                snippet = text.strip().replace("\n", " ")[:240]
                scored.append((score, f"{path.name}: {snippet}"))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]
