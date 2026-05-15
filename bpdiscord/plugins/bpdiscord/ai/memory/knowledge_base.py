"""知识库存储 - FAISS 向量检索"""
import os
import logging
from typing import List, Dict, Optional, Union
from pathlib import Path

import requests
from tqdm import tqdm
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from ...config import (
    KNOWLEDGE_DB_PATH,
    MODEL_CACHE_PATH,
    EMBEDDING_MODEL_NAME,
    HF_MIRRORS,
)

logger = logging.getLogger(__name__)


def _download_model_file(repo_id: str, filename: str, local_path: Path):
    """从国内镜像下载模型文件"""
    for mirror in HF_MIRRORS:
        try:
            url = f"{mirror}/{repo_id}/resolve/main/{filename}"
            logger.info(f"尝试从镜像下载: {url}")
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            total_size = int(response.headers.get("content-length", 0))
            progress_bar = tqdm(total=total_size, unit="iB", unit_scale=True, desc=f"下载 {filename}")
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        progress_bar.update(len(chunk))
                        f.write(chunk)
            progress_bar.close()
            if total_size != 0 and progress_bar.n != total_size:
                logger.error(f"下载不完整: {progress_bar.n}/{total_size} 字节")
                continue
            logger.info(f"成功下载: {filename}")
            return
        except Exception as e:
            logger.warning(f"镜像下载失败 ({mirror}): {e}")

    try:
        logger.warning("所有镜像失败，尝试官方源...")
        from huggingface_hub import hf_hub_download
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=local_path.parent,
            local_dir_use_symlinks=False,
        )
    except ImportError:
        raise RuntimeError("无法下载模型文件，请安装 huggingface_hub")


def _ensure_model_cached() -> str:
    """确保模型文件已缓存到本地"""
    model_dir = MODEL_CACHE_PATH / EMBEDDING_MODEL_NAME.replace("/", "_")
    required_files = [
        "config.json", "pytorch_model.bin", "special_tokens_map.json",
        "tokenizer_config.json", "vocab.txt",
    ]
    if not all((model_dir / f).exists() for f in required_files):
        logger.info(f"模型未缓存，开始下载: {EMBEDDING_MODEL_NAME}")
        for filename in required_files:
            file_path = model_dir / filename
            if not file_path.exists():
                _download_model_file(EMBEDDING_MODEL_NAME, filename, file_path)
    return str(model_dir)


class KnowledgeBaseMemory:
    def __init__(self):
        model_path = _ensure_model_cached()
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_path,
            encode_kwargs={"normalize_embeddings": True},
        )
        self.db_path = KNOWLEDGE_DB_PATH
        self.vectorstore = self._init_vectorstore()

    def _init_vectorstore(self) -> FAISS:
        index_file = os.path.join(self.db_path, "index.faiss")
        pkl_file = os.path.join(self.db_path, "index.pkl")
        version_file = os.path.join(self.db_path, ".version")
        current_version = "2"
        if os.path.exists(version_file):
            try:
                saved_version = open(version_file).read().strip()
                if saved_version != current_version:
                    logger.warning(f"索引版本不匹配 ({saved_version} → {current_version})，将重建")
                    os.remove(index_file)
                    os.remove(pkl_file)
            except Exception:
                pass
        if os.path.exists(index_file) and os.path.exists(pkl_file):
            try:
                vs = FAISS.load_local(
                    self.db_path, self.embeddings, allow_dangerous_deserialization=True
                )
                if vs.index.ntotal > 0:
                    return vs
            except Exception as e:
                logger.warning(f"加载旧索引失败，将重建: {e}")
        logger.info("创建新的向量数据库（归一化嵌入）")
        vs = FAISS.from_texts([""], self.embeddings, metadatas=[{"__placeholder__": True}])
        self._write_version()
        return vs

    def _write_version(self):
        os.makedirs(self.db_path, exist_ok=True)
        with open(os.path.join(self.db_path, ".version"), "w") as f:
            f.write("2")

    def _rebuild_without(self, docs_to_remove: list) -> None:
        all_docs = self.get_all_knowledge()
        remaining = [doc for doc in all_docs if doc not in docs_to_remove]
        if not remaining:
            self.vectorstore = FAISS.from_texts([""], self.embeddings, metadatas=[{"__placeholder__": True}])
        else:
            self.vectorstore = FAISS.from_documents(remaining, self.embeddings)
        self.vectorstore.save_local(self.db_path)
        self._write_version()

    def delete_knowledge_by_content(self, content: str) -> bool:
        to_delete = [doc for doc in self.get_all_knowledge() if content in doc.page_content]
        if not to_delete:
            return False
        self._rebuild_without(to_delete)
        logger.info(f"Deleted {len(to_delete)} knowledge items containing: {content}")
        return True

    def delete_knowledge_by_index(self, index: int) -> bool:
        all_docs = self.get_all_knowledge()
        if index < 1 or index > len(all_docs):
            return False
        doc_to_delete = all_docs[index - 1]
        self._rebuild_without([doc_to_delete])
        logger.info(f"Deleted knowledge item #{index}: {doc_to_delete.page_content}")
        return True

    def add_knowledge(self, text: str, metadata: dict = None):
        self.add_knowledge_batch([text], [metadata] if metadata else None)

    def add_knowledge_batch(self, texts: List[str], metadatas: Optional[List[dict]] = None):
        if not texts:
            return
        if metadatas is None:
            metadatas = [{}] * len(texts)
        elif len(metadatas) != len(texts):
            raise ValueError("Texts and metadatas must have the same length")
        docs = [Document(page_content=text, metadata=meta) for text, meta in zip(texts, metadatas)]
        self.vectorstore.add_documents(docs)
        self.vectorstore.save_local(self.db_path)
        self._write_version()
        logger.info(f"Added {len(texts)} knowledge items to vector DB")

    def get_all_knowledge(self) -> List[Document]:
        return [
            doc for doc in self.vectorstore.docstore._dict.values()
            if not doc.metadata.get("__placeholder__")
        ]

    def search_knowledge(
        self,
        query: str,
        k: int = 3,
        metadata_filter: Optional[dict] = None,
        score_threshold: Optional[float] = None,
    ) -> Union[str, List[Document]]:
        search_k = k + 1  # 预留占位文档槽位
        if score_threshold is not None:
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, k=search_k, filter=metadata_filter
            )
            docs = [doc for doc, score in docs_with_scores
                    if not doc.metadata.get("__placeholder__")
                    and 1 / (1 + score) >= score_threshold][:k]
        else:
            docs = self.vectorstore.similarity_search(query, k=search_k, filter=metadata_filter)
            docs = [doc for doc in docs if not doc.metadata.get("__placeholder__")][:k]

        if not docs:
            return "未找到相关知识"
        return "\n".join([f"- {doc.page_content}" for doc in docs])
