"""基于 pgvector 的向量知识库 —— 支持语义检索 (RAG)。

文档分块 → Embedding 向量化 → 存入 pgvector → 余弦相似度检索。
当向量检索不可用时，自动回退到关键词匹配。
"""

from pathlib import Path

from backend.cloud_api.cloud.embedding import EmbeddingClient
from backend.shared.core.config import get_settings


class VectorKnowledgeBase:
    def __init__(self, root: Path | str, embedding: EmbeddingClient) -> None:
        self.root = Path(root)
        self.embedding = embedding

    def search(self, query: str, limit: int = 3) -> list[str]:
        settings = get_settings()
        if settings.postgres_vector_enabled and self.embedding.enabled:
            results = self._vector_search(query, limit)
            if results:
                return results
        return self._keyword_search(query, limit)

    def index_documents(self) -> int:
        """扫描知识库目录，分块、向量化并存入 pgvector。返回索引的文档数。"""
        settings = get_settings()
        if not settings.postgres_vector_enabled or not self.embedding.enabled:
            return 0
        docs = list(self._iter_documents())
        if not docs:
            return 0
        self._clear_chunks()
        total = 0
        chunks_batch: list[tuple[str, int, str]] = []
        for path in docs:
            text = path.read_text(encoding="utf-8", errors="ignore")
            chunks = self._chunk_text(text)
            for i, chunk in enumerate(chunks):
                chunks_batch.append((path.name, i, chunk))
            if len(chunks_batch) >= 10:
                total += self._insert_chunks(chunks_batch)
                chunks_batch = []
        if chunks_batch:
            total += self._insert_chunks(chunks_batch)
        return total

    def _vector_search(self, query: str, limit: int) -> list[str]:
        try:
            from psycopg import connect, sql
            from backend.cloud_api.cloud.schema import qualified
            emb = self.embedding.embed([query])[0]
            emb_str = "[" + ",".join(str(v) for v in emb) + "]"
            s = get_settings()
            with connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db,
                         user=s.postgres_user, password=s.postgres_password) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "SELECT content, 1 - (embedding <=> %s::vector) AS similarity "
                            "FROM {} WHERE embedding IS NOT NULL "
                            "ORDER BY embedding <=> %s::vector LIMIT %s"
                        ).format(qualified(s, "knowledge_chunks")),
                        (emb_str, emb_str, limit),
                    )
                    rows = cur.fetchall()
                    return [f"{row[0][:200]}（相似度 {row[1]:.3f}）" for row in rows]
        except Exception:
            return []

    def _keyword_search(self, query: str, limit: int) -> list[str]:
        if not self.root.exists():
            return []
        query_terms = {t for t in query.lower().split() if t}
        scored: list[tuple[int, str]] = []
        for path in self._iter_documents():
            text = path.read_text(encoding="utf-8", errors="ignore")
            score = sum(1 for t in query_terms if t in text.lower())
            if score > 0 or not query_terms:
                snippet = text.strip().replace("\n", " ")[:240]
                scored.append((score, f"{path.name}: {snippet}"))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def _insert_chunks(self, chunks: list[tuple[str, int, str]]) -> int:
        try:
            texts = [c[2] for c in chunks]
            embeddings = self.embedding.embed(texts)
            from psycopg import connect, sql
            from backend.cloud_api.cloud.schema import qualified
            s = get_settings()
            with connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db,
                         user=s.postgres_user, password=s.postgres_password, autocommit=True) as conn:
                with conn.cursor() as cur:
                    for (doc_name, chunk_idx, content), emb in zip(chunks, embeddings):
                        emb_str = "[" + ",".join(str(v) for v in emb) + "]"
                        cur.execute(
                            sql.SQL("INSERT INTO {} (doc_name, chunk_index, content, embedding) VALUES (%s, %s, %s, %s::vector)").format(
                                qualified(s, "knowledge_chunks")
                            ), (doc_name, chunk_idx, content, emb_str))
                    return len(chunks)
        except Exception:
            return 0

    def _clear_chunks(self) -> None:
        try:
            from psycopg import connect, sql
            from backend.cloud_api.cloud.schema import qualified
            s = get_settings()
            with connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db,
                         user=s.postgres_user, password=s.postgres_password, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL("DELETE FROM {}").format(qualified(s, "knowledge_chunks")))
        except Exception:
            pass

    def _chunk_text(self, text: str, max_chars: int = 500) -> list[str]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) < max_chars:
                current = (current + "\n\n" + para).strip()
            else:
                if current:
                    chunks.append(current[:max_chars])
                current = para[:max_chars]
        if current:
            chunks.append(current[:max_chars])
        return chunks or [text[:max_chars]]

    def _iter_documents(self):
        for pattern in ("*.txt", "*.md"):
            yield from self.root.rglob(pattern)
