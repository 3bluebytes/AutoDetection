"""
OpenCLAW Tool: rag_wiki
UVP 组件代码架构知识库 - RAG 检索

使用 TF-IDF 向量化（不依赖 PyTorch/onnx，纯 Python 实现）
知识库包含 libvirt、qemu、dpdk、ovs 四个开源项目的代码架构信息

面试亮点：
1. 基于 TF-IDF 的轻量 RAG，不依赖 GPU/深度学习框架
2. 支持组件和失败类型双维度过滤
3. 知识库可扩展，新增组件只需更新 wiki_data.json
"""

import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─── 配置 ────────────────────────────────────────────────────

WIKI_DATA_PATH = Path(__file__).parent / "wiki_data.json"
INDEX_PATH = Path(__file__).parent / "tfidf_index.json"


# ─── TF-IDF 向量化 ──────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """分词：英文按空格，中文按字，去除标点"""
    text = text.lower()
    # 提取英文单词和中文单字
    tokens = re.findall(r'[a-z]+|[0-9]+|[\u4e00-\u9fff]', text)
    # 英文去掉太短的
    tokens = [t for t in tokens if len(t) > 1 or '\u4e00' <= t <= '\u9fff']
    return tokens


class TFIDFIndex:
    """轻量级 TF-IDF 索引"""

    def __init__(self):
        self.documents = []      # 原始文档
        self.metadatas = []      # 元数据
        self.doc_tokens = []     # 分词结果
        self.idf = {}            # 逆文档频率
        self.doc_vectors = []    # TF-IDF 向量

    def add_documents(self, documents: List[str], metadatas: List[Dict]):
        """添加文档到索引"""
        self.documents = documents
        self.metadatas = metadatas
        self.doc_tokens = [_tokenize(doc) for doc in documents]
        self._compute_idf()
        self._compute_vectors()

    def _compute_idf(self):
        """计算逆文档频率"""
        doc_count = len(self.doc_tokens)
        df = Counter()  # 文档频率

        for tokens in self.doc_tokens:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                df[token] += 1

        self.idf = {
            token: math.log((doc_count + 1) / (freq + 1)) + 1
            for token, freq in df.items()
        }

    def _compute_vectors(self):
        """计算 TF-IDF 向量"""
        self.doc_vectors = []
        for tokens in self.doc_tokens:
            tf = Counter(tokens)
            total = len(tokens) if tokens else 1
            vector = {
                token: (freq / total) * self.idf.get(token, 1.0)
                for token, freq in tf.items()
            }
            self.doc_vectors.append(vector)

    def search(self, query: str, top_k: int = 3, component: str = "",
               failure_type: str = "") -> List[Tuple[int, float]]:
        """搜索最相关的文档"""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # 计算 query 的 TF-IDF 向量
        query_tf = Counter(query_tokens)
        total = len(query_tokens)
        query_vector = {
            token: (freq / total) * self.idf.get(token, 1.0)
            for token, freq in query_tf.items()
        }

        # 计算余弦相似度
        scores = []
        for i, doc_vector in enumerate(self.doc_vectors):
            # 过滤条件
            meta = self.metadatas[i] if self.metadatas else {}
            if component and meta.get("component", "") != component:
                continue
            if failure_type and failure_type not in meta.get("related_failures", ""):
                continue

            # 余弦相似度
            score = self._cosine_similarity(query_vector, doc_vector)
            scores.append((i, score))

        # 排序
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]

    @staticmethod
    def _cosine_similarity(v1: Dict[str, float], v2: Dict[str, float]) -> float:
        """计算两个稀疏向量的余弦相似度"""
        common_keys = set(v1.keys()) & set(v2.keys())
        if not common_keys:
            return 0.0

        dot = sum(v1[k] * v2[k] for k in common_keys)
        norm1 = math.sqrt(sum(v * v for v in v1.values()))
        norm2 = math.sqrt(sum(v * v for v in v2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot / (norm1 * norm2)

    def save(self, path: str):
        """保存索引"""
        data = {
            "documents": self.documents,
            "metadatas": self.metadatas,
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: str) -> bool:
        """加载索引"""
        p = Path(path)
        if not p.exists():
            return False

        data = json.loads(p.read_text(encoding="utf-8"))
        self.documents = data.get("documents", [])
        self.metadatas = data.get("metadatas", [])
        self.doc_tokens = [_tokenize(doc) for doc in self.documents]
        self._compute_idf()
        self._compute_vectors()
        return True


# ─── 知识库构建 ───────────────────────────────────────────────

def build_wiki_index(force_rebuild: bool = False) -> Dict:
    """
    构建 RAG 知识库索引

    Returns:
        构建结果
    """
    if not WIKI_DATA_PATH.exists():
        return {"success": False, "error": "wiki_data.json not found"}

    wiki_data = json.loads(WIKI_DATA_PATH.read_text(encoding="utf-8"))

    # 构建文档
    documents = []
    metadatas = []

    for component, data in wiki_data.items():
        repo = data.get("repo", "")
        branches = data.get("branches", {})

        for arch in data.get("architecture", []):
            module = arch.get("module", "")
            description = arch.get("description", "")
            key_files = ", ".join(arch.get("key_files", []))
            related_failures = ", ".join(arch.get("related_failures", []))
            detail = arch.get("detail", "")

            doc_text = (
                f"组件: {component}\n"
                f"模块: {module}\n"
                f"描述: {description}\n"
                f"关键文件: {key_files}\n"
                f"关联失败类型: {related_failures}\n"
                f"详细说明: {detail}\n"
                f"仓库: {repo}\n"
                f"分支: {', '.join(branches.keys())}"
            )

            documents.append(doc_text)
            metadatas.append({
                "component": component,
                "module": module,
                "repo": repo,
                "related_failures": related_failures,
                "branch_list": ", ".join(branches.keys()),
            })

    # 构建索引
    index = TFIDFIndex()
    index.add_documents(documents, metadatas)
    index.save(str(INDEX_PATH))

    return {
        "success": True,
        "message": f"Indexed {len(documents)} documents",
        "doc_count": len(documents)
    }


# ─── 知识库检索 ───────────────────────────────────────────────

def search_wiki(
    query: str,
    component: str = "",
    failure_type: str = "",
    top_k: int = 3
) -> Dict:
    """
    在知识库中检索相关架构信息

    Args:
        query: 查询文本
        component: 组件名过滤
        failure_type: 失败类型过滤
        top_k: 返回结果数

    Returns:
        检索结果
    """
    # 加载索引
    index = TFIDFIndex()
    if not index.load(str(INDEX_PATH)):
        # 索引不存在，先构建
        build_result = build_wiki_index()
        if not build_result["success"]:
            return build_result
        index.load(str(INDEX_PATH))

    # 搜索
    results = index.search(query, top_k=top_k, component=component, failure_type=failure_type)

    formatted = []
    for doc_idx, score in results:
        doc = index.documents[doc_idx]
        meta = index.metadatas[doc_idx]

        formatted.append({
            "content": doc,
            "component": meta.get("component", ""),
            "module": meta.get("module", ""),
            "repo": meta.get("repo", ""),
            "branches": meta.get("branch_list", ""),
            "relevance": round(score, 3),
        })

    return {
        "success": True,
        "query": query,
        "results": formatted,
        "total": len(formatted)
    }


def get_component_architecture(component: str, failure_type: str = "") -> Dict:
    """
    获取指定组件的架构信息

    Args:
        component: 组件名
        failure_type: 失败类型（可选）

    Returns:
        架构信息
    """
    component_map = {
        "kernel": "qemu",
    }
    search_component = component_map.get(component, component)

    query = failure_type if failure_type else f"{component} architecture overview"

    return search_wiki(
        query=query,
        component=search_component,
        failure_type=failure_type,
        top_k=3
    )


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "rag_wiki",
    "description": "RAG-based component architecture wiki for UVP codebase",
    "parameters": {
        "query": "string - search query",
        "component": "string - component filter",
        "failure_type": "string - failure type",
        "top_k": "int - number of results"
    },
    "returns": "JSON with relevant architecture documents",
    "enabled": True
}


if __name__ == "__main__":
    # 构建索引
    print("Building wiki index...")
    result = build_wiki_index(force_rebuild=True)
    print(f"Result: {result}")

    # 测试检索
    print("\n--- Test: search for memory hotplug ---")
    r = search_wiki("memory hotplug not supported", component="libvirt", failure_type="libvirt_error")
    for item in r.get("results", []):
        print(f"\n[{item['component']}] {item['module']} (相似度: {item['relevance']})")
        print(item['content'][:200])

    print("\n--- Test: search for migration timeout ---")
    r = search_wiki("live migration timeout", failure_type="timeout")
    for item in r.get("results", []):
        print(f"\n[{item['component']}] {item['module']} (相似度: {item['relevance']})")
        print(item['content'][:200])

    print("\n--- Test: search for iscsi storage ---")
    r = search_wiki("iscsi connection refused storage pool", component="qemu")
    for item in r.get("results", []):
        print(f"\n[{item['component']}] {item['module']} (相似度: {item['relevance']})")
        print(item['content'][:200])
