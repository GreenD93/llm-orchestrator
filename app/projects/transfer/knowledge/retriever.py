# app/projects/transfer/knowledge/retriever.py
"""파일 기반 RAG. 필요 시 retriever.search(query)만 구현해 Agent에 주입."""

from typing import Any, List


class Retriever:
    def search(self, query: str) -> List[Any]:
        """query로 검색한 문서 목록 반환. 기본은 빈 리스트."""
        return []
