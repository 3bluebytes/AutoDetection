"""
RAG Wiki - UVP 组件代码架构知识库
"""

from .rag_engine import build_wiki_index, search_wiki, get_component_architecture

__all__ = [
    "build_wiki_index",
    "search_wiki",
    "get_component_architecture",
]
