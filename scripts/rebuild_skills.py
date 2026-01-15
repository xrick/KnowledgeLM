# scripts/rebuild_skills.py
#!/usr/bin/env python
"""
Skill 重建腳本
嚴格使用用戶指定的 skill 名稱，禁止系統自動改名
"""

import asyncio
import sys
import os
from pathlib import Path
import logging
import hashlib
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.Providers.skill_metadata_provider.client import SkillMetadataProvider
from app.Providers.vector_store_provider.client import VectorStoreProvider
from app.Providers.bge_embedding_provider import get_bge_embedding_provider
import PyPDF2
import sqlite3
import json

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# 重要：嚴格使用用戶指定的 skill 名稱，禁止系統自動改名
# ============================================================================
SKILLS_TO_BUILD = [
    {
        "skill_name": "六法全書-刑法",  # 嚴禁改名
        "directory": "refData/rawdata/law/刑法",
        "description": "刑法相關法律條文，包含刑法、刑事訴訟法等",
        "category": "Legal"
    },
    {
        "skill_name": "六法全書-民法",  # 嚴禁改名
        "directory": "refData/rawdata/law/民法",
        "description": "民法相關法律條文，包含民法、民事訴訟法、家事事件法等",
        "category": "Legal"
    },
    {
        "skill_name": "LLM",  # 嚴禁改名
        "directory": "refData/rawdata/LLM",
        "description": "大型語言模型相關技術文檔，涵蓋 LLM 建構與工程實踐",
        "category": "Technology"
    }
]


class SkillRebuilder:
    """Skill 重建器"""

    def __init__(self):
        """初始化"""
        self.metadata_provider = SkillMetadataProvider(
            db_path="./data/skill_metadata.db"
        )
        self.vector_provider = VectorStoreProvider(
            persist_directory="./data/faiss_indices"
        )
        self.embedding_provider = get_bge_embedding_provider()
        self.embedding_dimension = 1024  # BGE-M3 dimension
        logger.info("Skill Rebuilder 初始化完成")

    def generate_skill_id(self, skill_name: str) -> str:
        """
        生成 skill_id

        重要：skill_id 僅用於內部標識，不影響 skill_name 的顯示
        skill_name 必須嚴格保持用戶指定的名稱
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name_hash = hashlib.md5(skill_name.encode('utf-8')).hexdigest()[:8]
        return f"skill_{timestamp}_{name_hash}"

    async def extract_pdf_pages(self, pdf_path: Path) -> list:
        """從 PDF 提取每頁文字"""
        pages = []
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)

                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    text = self._clean_text(text)
                    if text.strip():
                        pages.append(text)

        except Exception as e:
            logger.error(f"PDF 提取錯誤 {pdf_path}: {e}")
            raise
        return pages

    def _clean_text(self, text: str) -> str:
        """清理文字"""
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        cleaned_text = '\n'.join(cleaned_lines)
        while '  ' in cleaned_text:
            cleaned_text = cleaned_text.replace('  ', ' ')
        return cleaned_text

    async def build_skill(self, skill_config: dict) -> dict:
        """
        建立單個 Skill

        重要：skill_name 必須使用 skill_config 中的原始名稱
        嚴禁系統自動更改名稱
        """
        # 嚴格使用用戶指定的名稱
        skill_name = skill_config["skill_name"]
        directory = skill_config["directory"]
        description = skill_config["description"]
        category = skill_config.get("category", "General")

        logger.info(f"=" * 60)
        logger.info(f"開始建立 Skill: {skill_name}")
        logger.info(f"目錄: {directory}")
        logger.info(f"=" * 60)

        # 檢查目錄
        dir_path = Path(directory)
        if not dir_path.exists():
            raise ValueError(f"目錄不存在: {directory}")

        pdf_files = list(dir_path.glob("*.pdf"))
        if not pdf_files:
            raise ValueError(f"目錄中沒有 PDF 檔案: {directory}")

        logger.info(f"找到 {len(pdf_files)} 個 PDF 檔案")

        # 生成 skill_id (內部標識，不影響名稱)
        skill_id = self.generate_skill_id(skill_name)
        logger.info(f"Skill ID: {skill_id}")

        # 處理所有 PDF
        all_chunks = []
        all_embeddings = []
        document_mappings = []

        for pdf_path in pdf_files:
            logger.info(f"處理 PDF: {pdf_path.name}")

            # 提取頁面
            pages = await self.extract_pdf_pages(pdf_path)
            logger.info(f"  提取 {len(pages)} 頁")

            # 建立文檔 ID
            doc_id = f"doc_{hashlib.md5(str(pdf_path).encode()).hexdigest()[:8]}"
            document_mappings.append({
                'document_id': doc_id,
                'document_name': pdf_path.stem,
                'document_path': str(pdf_path),
                'total_pages': len(pages)
            })

            # 處理每頁
            for page_num, page_text in enumerate(pages, 1):
                chunk_id = f"{skill_id}_{doc_id}_p{page_num}"

                chunk_metadata = {
                    'chunk_id': chunk_id,
                    'skill_id': skill_id,
                    'document_id': doc_id,
                    'document_name': pdf_path.stem,
                    'page_number': page_num,
                    'chunk_index': len(all_chunks),
                    'embedding_model': 'BAAI/bge-m3',
                    'embedding_dimension': self.embedding_dimension
                }

                all_chunks.append({
                    'chunk_id': chunk_id,
                    'content': page_text,
                    'metadata': chunk_metadata
                })

                # 生成 embedding
                embedding = self.embedding_provider.embed_single(page_text)
                all_embeddings.append(embedding)

            logger.info(f"  完成 {pdf_path.name}")

        logger.info(f"總共 {len(all_chunks)} 個 chunks")

        # 存儲 embeddings 到 FAISS
        logger.info("存儲 embeddings 到 FAISS...")
        await self._store_embeddings(skill_id, all_chunks, all_embeddings)

        # 存儲 metadata 到 SQLite
        # 重要：這裡使用原始的 skill_name，嚴禁修改
        logger.info("存儲 metadata 到 SQLite...")
        await self._store_metadata(
            skill_id=skill_id,
            skill_name=skill_name,  # 嚴格使用原始名稱
            skill_description=description,
            skill_category=category,
            chunks=all_chunks,
            document_mappings=document_mappings
        )

        result = {
            'skill_id': skill_id,
            'skill_name': skill_name,  # 嚴格保持原始名稱
            'documents_processed': len(pdf_files),
            'total_chunks': len(all_chunks),
            'documents': [dm['document_name'] for dm in document_mappings]
        }

        logger.info(f"✅ 成功建立 Skill: {skill_name}")
        return result

    async def _store_embeddings(self, skill_id: str, chunks: list, embeddings: list):
        """存儲 embeddings 到 FAISS"""
        try:
            texts = [chunk['content'] for chunk in chunks]
            metadata_list = [chunk['metadata'] for chunk in chunks]

            # Create embedding wrapper for query compatibility
            class EmbeddingWrapper:
                def __init__(self, provider):
                    self._provider = provider
                def embed_query(self, text):
                    return self._provider.embed_single(text).tolist()

            store_id = self.vector_provider.create_store_from_texts(
                texts=texts,
                embeddings=EmbeddingWrapper(self.embedding_provider),
                metadatas=metadata_list,
                file_id=skill_id,
                store_type='skill',
                precomputed_embeddings=embeddings
            )

            logger.info(f"  ✓ FAISS 存儲完成: {store_id}")

        except Exception as e:
            logger.error(f"FAISS 存儲錯誤: {e}")
            raise

    async def _store_metadata(self, skill_id: str, skill_name: str,
                             skill_description: str, skill_category: str,
                             chunks: list, document_mappings: list):
        """
        存儲 metadata 到 SQLite

        重要：skill_name 必須使用傳入的原始名稱，嚴禁修改
        """
        try:
            # 建立 skill entry
            # 注意：skill_name 直接使用傳入值，不做任何轉換
            await self.metadata_provider.create_skill(
                skill_id=skill_id,
                skill_name=skill_name,  # 嚴格使用原始名稱
                skill_description=skill_description,
                skill_category=skill_category,
                skill_level="professional",
                tags=[skill_category.lower()],
                total_chunks=len(chunks),
                metadata={
                    'embedding_model': 'BAAI/bge-m3',
                    'embedding_dimension': self.embedding_dimension
                }
            )

            # 直接操作 SQLite 存儲文檔映射和 chunk metadata
            db_path = Path("data/skill_metadata.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 插入文檔映射
            for doc_mapping in document_mappings:
                cursor.execute("""
                    INSERT INTO skill_document_mapping
                    (skill_id, file_id, document_name, document_path, total_pages, relevance_score)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    skill_id,
                    doc_mapping['document_id'],
                    doc_mapping['document_name'],
                    doc_mapping['document_path'],
                    doc_mapping['total_pages'],
                    1.0
                ))

            # 插入 chunk metadata
            for chunk in chunks:
                metadata = chunk['metadata']
                cursor.execute("""
                    INSERT INTO skill_chunk_metadata
                    (chunk_id, skill_id, document_id, document_name, page_number,
                     chunk_index, chunk_text, embedding_model, embedding_dimension, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metadata['chunk_id'],
                    skill_id,
                    metadata['document_id'],
                    metadata['document_name'],
                    metadata['page_number'],
                    metadata['chunk_index'],
                    chunk['content'][:500],
                    'BAAI/bge-m3',
                    self.embedding_dimension,
                    json.dumps(metadata)
                ))

            conn.commit()
            conn.close()

            logger.info(f"  ✓ SQLite metadata 存儲完成")

        except Exception as e:
            logger.error(f"Metadata 存儲錯誤: {e}")
            raise

    async def rebuild_all(self):
        """重建所有 Skills"""
        logger.info("=" * 60)
        logger.info("開始重建所有 Skills")
        logger.info("重要：所有 skill 名稱嚴格使用用戶指定的名稱")
        logger.info("=" * 60)

        results = []
        for skill_config in SKILLS_TO_BUILD:
            try:
                result = await self.build_skill(skill_config)
                results.append(result)
            except Exception as e:
                logger.error(f"建立 Skill 失敗 [{skill_config['skill_name']}]: {e}")
                continue

        # 顯示結果
        logger.info("\n" + "=" * 60)
        logger.info("重建完成！結果如下：")
        logger.info("=" * 60)

        for result in results:
            logger.info(f"\nSkill: {result['skill_name']}")
            logger.info(f"  ID: {result['skill_id']}")
            logger.info(f"  文檔數: {result['documents_processed']}")
            logger.info(f"  Chunks: {result['total_chunks']}")
            logger.info(f"  文檔: {', '.join(result['documents'])}")

        return results

    async def verify_skills(self):
        """驗證建立的 Skills"""
        logger.info("\n驗證 Skills...")

        skills = await self.metadata_provider.list_skills()

        if not skills:
            logger.error("沒有找到任何 Skills！")
            return False

        logger.info(f"找到 {len(skills)} 個 Skills:")
        for skill in skills:
            skill_id = skill['skill_id']
            skill_name = skill['skill_name']

            # 獲取文檔映射
            docs = await self.metadata_provider.get_documents_for_skill(skill_id)

            logger.info(f"  - {skill_name}")
            logger.info(f"    ID: {skill_id}")
            logger.info(f"    文檔數: {len(docs)}")

        return True


async def main():
    """主函數"""
    print("\n" + "=" * 60)
    print("Skill 重建腳本")
    print("重要：所有 skill 名稱嚴格使用用戶指定的名稱")
    print("嚴禁系統自動改名")
    print("=" * 60 + "\n")

    rebuilder = SkillRebuilder()

    # 重建所有 Skills
    results = await rebuilder.rebuild_all()

    # 驗證結果
    await rebuilder.verify_skills()

    print("\n" + "=" * 60)
    print("🎉 重建完成！")
    print("=" * 60)

    # 輸出 skill_ids 供前端使用
    print("\n前端 fallback skills 更新資訊：")
    for result in results:
        print(f"  {result['skill_name']}: {result['skill_id']}")


if __name__ == "__main__":
    asyncio.run(main())
