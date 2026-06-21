"""知识库管理接口。

GET  /api/knowledge        → 列出所有知识库文件名
GET  /api/knowledge/{name} → 读取指定文件内容
PUT  /api/knowledge/{name} → 更新指定文件内容
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.shared.core.config import get_settings

router = APIRouter(prefix="/api/knowledge", tags=["cloud-knowledge"])

_ALLOWED_SUFFIXES = {".txt", ".md"}


class KnowledgeFileUpdate(BaseModel):
    content: str


def _root() -> Path:
    return get_settings().knowledge_dir


def _is_safe(name: str) -> bool:
    return ".." not in name and "/" not in name and "\\" not in name


@router.get("")
def list_files() -> list[dict]:
    root = _root()
    if not root.exists():
        return []
    files = sorted(root.glob("*"))
    return [
        {"name": f.name, "size": f.stat().st_size}
        for f in files
        if f.suffix.lower() in _ALLOWED_SUFFIXES
    ]


@router.get("/{name}")
def read_file(name: str) -> dict:
    if not _is_safe(name):
        raise HTTPException(status_code=400, detail="非法文件名")
    path = _root() / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    suffix = path.suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    return {
        "name": path.name,
        "suffix": suffix,
        "content": path.read_text(encoding="utf-8"),
        "size": path.stat().st_size,
    }


@router.put("/{name}")
def update_file(name: str, body: KnowledgeFileUpdate) -> dict:
    if not _is_safe(name):
        raise HTTPException(status_code=400, detail="非法文件名")
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    suffix = path.suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持 .txt 和 .md 文件")
    path.write_text(body.content, encoding="utf-8")
    return {"name": path.name, "size": path.stat().st_size, "ok": True}
