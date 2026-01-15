# scripts/skill_data/rebuild_from_config.py
#!/usr/bin/env python3
"""
rebuild_from_config.py
=======================
根據 skill_config.json 重建所有 Skills

從 JSON 配置文件讀取 skill 定義，並使用 BGE-M3 embedding 建立向量索引。

環境變數：
    SKILL_CONFIG_PATH: 配置文件路徑 (可選)
    SKILL_FILTER: 只重建指定的 skill 名稱 (可選)

使用方式：
    python scripts/skill_data/rebuild_from_config.py
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import PyPDF2
import numpy as np

# 添加專案根目錄到 Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.Providers.bge_embedding_provider import get_bge_embedding_provider
from app.Providers.skill_metadata_provider.client import SkillMetadataProvider
from app.Providers.vector_store_provider.client import VectorStoreProvider

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / 'logs' / 'rebuild_skills.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class SmartRebuildStrategy:
    """智能重建策略 - 確定重建範圍"""

    class RebuildScope:
        """重建範圍定義"""
        NONE = "none"          # 不重建（等待更多臨時附件）
        TARGETED = "targeted"  # 只重建受影響的 skills
        ALL = "all"            # 重建所有 skills

    def __init__(self, config: Dict[str, Any]):
        """
        初始化智能重建策略

        Args:
            config: skill_config.json 配置
        """
        self.config = config
        self.instant_attachments = config.get('instant_attachments', [])
        self.rebuild_threshold = config.get('settings', {}).get('rebuild_threshold', 5)
        self.skills = config.get('skills', [])

    def determine_rebuild_scope(self, force_all: bool = False) -> tuple[str, List[str]]:
        """
        確定重建範圍

        Args:
            force_all: 是否強制重建所有 skills

        Returns:
            (scope, affected_skills) - 重建範圍和受影響的 skill 名稱列表
        """
        if force_all:
            logger.info("強制重建模式：將重建所有 skills")
            skill_names = [s.get('skill_name') for s in self.skills if s.get('enabled', True)]
            return self.RebuildScope.ALL, skill_names

        attachment_count = len(self.instant_attachments)

        if attachment_count == 0:
            logger.info("沒有臨時附件，無需重建")
            return self.RebuildScope.NONE, []

        if attachment_count < self.rebuild_threshold:
            logger.info(
                f"臨時附件數 ({attachment_count}) 未達到閾值 ({self.rebuild_threshold})，"
                f"等待更多附件或手動觸發重建"
            )
            return self.RebuildScope.NONE, []

        # 達到閾值 - 只重建受影響的 skills
        affected_skills = self._get_affected_skills()

        if affected_skills:
            logger.info(
                f"臨時附件數達到閾值 ({attachment_count}/{self.rebuild_threshold})，"
                f"使用有目標重建模式"
            )
            logger.info(f"受影響的 skills: {', '.join(affected_skills)}")
            return self.RebuildScope.TARGETED, affected_skills
        else:
            # 沒有找到受影響的 skills，使用全量重建
            logger.warning("找不到臨時附件對應的 skill，執行全量重建")
            skill_names = [s.get('skill_name') for s in self.skills if s.get('enabled', True)]
            return self.RebuildScope.ALL, skill_names

    def _get_affected_skills(self) -> List[str]:
        """
        根據臨時附件確定受影響的 skills

        Returns:
            受影響的 skill 名稱列表
        """
        affected = set()

        for attachment in self.instant_attachments:
            skill_name = attachment.get('skill_name')
            if skill_name:
                affected.add(skill_name)

        return sorted(list(affected))

    def should_clear_attachments_after_rebuild(self, scope: str) -> bool:
        """
        判斷重建後是否應清除臨時附件

        Args:
            scope: 重建範圍

        Returns:
            是否應清除臨時附件
        """
        # 只有在全量或有目標重建後才清除臨時附件
        return scope in [self.RebuildScope.ALL, self.RebuildScope.TARGETED]


class SkillConfigRebuilder:
    """根據 JSON 配置重建 Skills"""

    def __init__(self, config_path: str):
        """
        初始化重建器

        Args:
            config_path: skill_config.json 的路徑
        """
        self.config_path = Path(config_path)
        self.project_root = PROJECT_ROOT

        # 載入配置
        self.config = self._load_config()
        self.settings = self.config.get('settings', {})

        # 初始化 providers
        self.metadata_provider = SkillMetadataProvider(
            db_path=str(self.project_root / "data" / "skill_metadata.db")
        )
        self.vector_provider = VectorStoreProvider(
            persist_directory=str(self.project_root / "data" / "faiss_indices")
        )
        self.embedding_provider = get_bge_embedding_provider()

        # 從配置獲取 embedding 設定
        self.embedding_dimension = self.settings.get('embedding_dimension', 1024)
        self.chunk_size = self.settings.get('chunk_size', 1000)
        self.chunk_overlap = self.settings.get('chunk_overlap', 200)

        logger.info(f"Skill Config Rebuilder 初始化完成")
        logger.info(f"  配置文件: {self.config_path}")
        logger.info(f"  Chunk Size: {self.chunk_size}")
        logger.info(f"  Embedding Dimension: {self.embedding_dimension}")

    def _load_config(self) -> Dict[str, Any]:
        """載入配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"成功載入配置文件: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"無法載入配置文件: {e}")
            raise

    def generate_skill_id(self, skill_name: str) -> str:
        """生成唯一的 skill_id"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name_hash = hashlib.md5(skill_name.encode('utf-8')).hexdigest()[:8]
        return f"skill_{timestamp}_{name_hash}"

    async def extract_pdf_pages(self, pdf_path: Path) -> List[str]:
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

            logger.info(f"    提取 {len(pages)} 頁 from {pdf_path.name}")

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

    async def build_skill_from_config(self, skill_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        根據配置建立單個 Skill (Per-PDF Architecture)

        新架構：
        - 每個 PDF 建立獨立的 FAISS 索引和 SQLite 條目
        - Main Skill 作為 Group Header (無 FAISS 索引)
        - 符合 NotebookLM Source-Centric 設計理念

        Args:
            skill_config: skill 配置字典

        Returns:
            建立結果或 None（如果跳過）
        """
        skill_name = skill_config.get('skill_name')
        description = skill_config.get('description', '')
        category = skill_config.get('category', 'General')
        enabled = skill_config.get('enabled', True)
        sources = skill_config.get('sources', [])

        # 檢查是否啟用
        if not enabled:
            logger.info(f"跳過已停用的 Skill: {skill_name}")
            return None

        # 過濾啟用的 sources
        enabled_sources = [s for s in sources if s.get('enabled', True)]

        if not enabled_sources:
            logger.warning(f"Skill '{skill_name}' 沒有啟用的 PDF sources，跳過")
            return None

        logger.info(f"\n{'=' * 60}")
        logger.info(f"開始建立 Skill (Per-PDF Mode): {skill_name}")
        logger.info(f"描述: {description}")
        logger.info(f"類別: {category}")
        logger.info(f"PDF 數量: {len(enabled_sources)}")
        logger.info(f"{'=' * 60}")

        # 生成 Main Skill ID (Group Header)
        main_skill_id = self.generate_skill_id(skill_name)
        logger.info(f"Main Skill ID (Group Header): {main_skill_id}")

        # 追蹤處理結果
        child_skill_ids = []
        total_chunks_all = 0
        document_names = []

        # === Per-PDF Processing ===
        for idx, source in enumerate(enabled_sources):
            pdf_path = self.project_root / source['path']

            if not pdf_path.exists():
                logger.error(f"PDF 檔案不存在: {pdf_path}")
                continue

            source_name = pdf_path.stem  # e.g., "民法", "強制執行法"
            logger.info(f"\n  [{idx + 1}/{len(enabled_sources)}] 處理 PDF: {source_name}")

            # 提取頁面
            pages = await self.extract_pdf_pages(pdf_path)

            if not pages:
                logger.warning(f"    無法從 {source_name} 提取內容")
                continue

            # 生成 Child Skill ID
            child_skill_id = f"{main_skill_id}_src_{idx:02d}"
            doc_id = f"doc_{hashlib.md5(str(pdf_path).encode()).hexdigest()[:8]}"
            logger.info(f"    Child Skill ID: {child_skill_id}")

            # 第一步：創建所有 chunks 並收集文本
            pdf_texts = []
            pdf_chunks = []

            for page_num, page_text in enumerate(pages, 1):
                chunk_id = f"{child_skill_id}_{doc_id}_p{page_num}"

                chunk_metadata = {
                    'chunk_id': chunk_id,
                    'skill_id': child_skill_id,
                    'document_id': doc_id,
                    'document_name': source_name,
                    'source_file': pdf_path.name,
                    'page_number': page_num,
                    'chunk_index': len(pdf_chunks),
                    'embedding_model': 'BAAI/bge-m3',
                    'embedding_dimension': self.embedding_dimension
                }

                pdf_chunks.append({
                    'chunk_id': chunk_id,
                    'content': page_text,
                    'metadata': chunk_metadata
                })

                pdf_texts.append(page_text)

            # 第二步：批次生成 embeddings
            logger.info(f"    生成 {len(pdf_texts)} 個 embeddings (batch processing)...")
            pdf_embeddings = self.embedding_provider.embed_texts(
                pdf_texts,
                batch_size=32,
                show_progress=False
            )

            # 第三步：存儲 Child Skill 的 FAISS 索引
            logger.info(f"    存儲 FAISS 索引...")
            await self._store_embeddings(child_skill_id, pdf_chunks, pdf_embeddings)

            # 第四步：存儲 Child Skill 的 SQLite metadata
            logger.info(f"    存儲 SQLite metadata...")
            await self._store_child_metadata(
                child_skill_id=child_skill_id,
                parent_skill_id=main_skill_id,
                skill_name=skill_name,
                skill_description=source.get('description', ''),
                skill_category=category,
                source_name=source_name,
                source_file=pdf_path.name,
                chunks=pdf_chunks,
                doc_id=doc_id,
                pdf_path=pdf_path,
                total_pages=len(pages)
            )

            child_skill_ids.append(child_skill_id)
            total_chunks_all += len(pdf_chunks)
            document_names.append(source_name)

            logger.info(f"    ✅ 完成 {source_name}: {len(pages)} 頁 → {len(pdf_embeddings)} embeddings")

        if not child_skill_ids:
            logger.error(f"Skill '{skill_name}' 沒有任何有效的 PDF 被處理")
            return None

        # === 創建 Main Skill Entry (Group Header) ===
        logger.info(f"\n創建 Main Skill (Group Header)...")
        await self.metadata_provider.create_skill(
            skill_id=main_skill_id,
            skill_name=skill_name,
            skill_description=description,
            skill_category=category,
            skill_level="professional",
            tags=[category.lower()],
            total_chunks=total_chunks_all,  # 所有 children 的 chunks 總和
            metadata={
                'embedding_model': 'BAAI/bge-m3',
                'embedding_dimension': self.embedding_dimension,
                'config_version': self.config.get('version', '1.0'),
                'child_count': len(child_skill_ids),
                'child_skill_ids': child_skill_ids,
                'is_group_header': True
            },
            parent_skill_id='root',
            source_name=None  # Group header 沒有 source_name
        )

        logger.info(f"  ✅ Main Skill (Group Header) 創建完成")

        result = {
            'skill_id': main_skill_id,
            'skill_name': skill_name,
            'category': category,
            'documents_processed': len(child_skill_ids),
            'total_chunks': total_chunks_all,
            'documents': document_names,
            'child_skill_ids': child_skill_ids
        }

        logger.info(f"\n✅ 成功建立 Skill: {skill_name}")
        logger.info(f"   - Group Header: {main_skill_id}")
        logger.info(f"   - Child Skills: {len(child_skill_ids)}")
        logger.info(f"   - Total Chunks: {total_chunks_all}")
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
        """存儲 metadata 到 SQLite"""
        try:
            # 建立 skill entry
            await self.metadata_provider.create_skill(
                skill_id=skill_id,
                skill_name=skill_name,
                skill_description=skill_description,
                skill_category=skill_category,
                skill_level="professional",
                tags=[skill_category.lower()],
                total_chunks=len(chunks),
                metadata={
                    'embedding_model': 'BAAI/bge-m3',
                    'embedding_dimension': self.embedding_dimension,
                    'config_version': self.config.get('version', '1.0')
                }
            )

            # 直接操作 SQLite 存儲文檔映射和 chunk metadata
            db_path = self.project_root / "data" / "skill_metadata.db"
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

    async def _store_child_metadata(
        self,
        child_skill_id: str,
        parent_skill_id: str,
        skill_name: str,
        skill_description: str,
        skill_category: str,
        source_name: str,
        source_file: str,
        chunks: list,
        doc_id: str,
        pdf_path: Path,
        total_pages: int
    ):
        """
        存儲 Child Skill (Per-PDF) 的 metadata 到 SQLite

        Args:
            child_skill_id: Child skill ID
            parent_skill_id: Parent (main) skill ID
            skill_name: Skill name (same as parent for grouping)
            skill_description: Description from source config
            skill_category: Category
            source_name: PDF file stem (e.g., "民法")
            source_file: PDF file name (e.g., "民法.pdf")
            chunks: List of chunks
            doc_id: Document ID
            pdf_path: Path to PDF file
            total_pages: Total pages in PDF
        """
        try:
            # 建立 child skill entry (使用 parent_skill_id 和 source_name)
            await self.metadata_provider.create_skill(
                skill_id=child_skill_id,
                skill_name=skill_name,
                skill_description=skill_description,
                skill_category=skill_category,
                skill_level="professional",
                tags=[skill_category.lower()],
                total_chunks=len(chunks),
                metadata={
                    'embedding_model': 'BAAI/bge-m3',
                    'embedding_dimension': self.embedding_dimension,
                    'config_version': self.config.get('version', '1.0'),
                    'source_file': source_file,
                    'is_per_pdf_child': True
                },
                parent_skill_id=parent_skill_id,
                source_name=source_name
            )

            # 直接操作 SQLite 存儲文檔映射和 chunk metadata
            db_path = self.project_root / "data" / "skill_metadata.db"
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 插入文檔映射
            cursor.execute("""
                INSERT INTO skill_document_mapping
                (skill_id, file_id, document_name, document_path, total_pages, relevance_score)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                child_skill_id,
                doc_id,
                source_name,
                str(pdf_path),
                total_pages,
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
                    child_skill_id,
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

            logger.info(f"    ✓ Child SQLite metadata 存儲完成: {source_name}")

        except Exception as e:
            logger.error(f"Child Metadata 存儲錯誤: {e}")
            raise

    async def rebuild_all(
        self,
        skill_filter: Optional[str] = None,
        force_all: bool = False,
        use_smart_strategy: bool = True
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """
        重建所有 Skills（支持智能重建策略）

        Args:
            skill_filter: 可選，只重建指定名稱的 skill
            force_all: 強制重建所有 skills（忽略智能策略）
            use_smart_strategy: 是否使用智能重建策略

        Returns:
            (建立結果列表, 重建範圍) - 若使用智能策略，返回範圍；否則為 None
        """
        logger.info("\n" + "=" * 60)
        logger.info("開始重建 Skills (from JSON config)")
        logger.info("=" * 60)

        rebuild_scope = None

        # 使用智能重建策略確定範圍
        if use_smart_strategy and not skill_filter and not force_all:
            strategy = SmartRebuildStrategy(self.config)
            rebuild_scope, skills_to_rebuild = strategy.determine_rebuild_scope(force_all=False)

            if rebuild_scope == SmartRebuildStrategy.RebuildScope.NONE:
                logger.info("❌ 智能策略判斷無需重建，結束")
                return [], rebuild_scope

            # 轉換為 skill config 列表
            all_skills = self.config.get('skills', [])
            skills = [s for s in all_skills if s.get('skill_name') in skills_to_rebuild]
        else:
            # 傳統模式：重建所有或指定的 skill
            skills = self.config.get('skills', [])

            if skill_filter:
                skills = [s for s in skills if s.get('skill_name') == skill_filter]
                if not skills:
                    logger.warning(f"找不到名為 '{skill_filter}' 的 skill")
                    return [], None

        results = []
        for skill_config in skills:
            try:
                result = await self.build_skill_from_config(skill_config)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"建立 Skill 失敗 [{skill_config.get('skill_name')}]: {e}")
                continue

        # 顯示結果摘要
        self._show_summary(results)

        # 智能清理臨時附件
        if use_smart_strategy and rebuild_scope:
            strategy = SmartRebuildStrategy(self.config)
            if strategy.should_clear_attachments_after_rebuild(rebuild_scope):
                logger.info(f"自動清除臨時附件（重建範圍: {rebuild_scope}）")
                # 將在 API 層面處理清除

        return results, rebuild_scope

    def _show_summary(self, results: List[Dict[str, Any]]):
        """顯示重建結果摘要"""
        logger.info("\n" + "=" * 60)
        logger.info("重建完成！結果摘要：")
        logger.info("=" * 60)

        if not results:
            logger.warning("沒有成功建立任何 Skill")
            return

        total_docs = 0
        total_chunks = 0

        for result in results:
            logger.info(f"\n📚 Skill: {result['skill_name']}")
            logger.info(f"   ID: {result['skill_id']}")
            logger.info(f"   類別: {result['category']}")
            logger.info(f"   文檔數: {result['documents_processed']}")
            logger.info(f"   Chunks: {result['total_chunks']}")
            logger.info(f"   文檔: {', '.join(result['documents'])}")

            total_docs += result['documents_processed']
            total_chunks += result['total_chunks']

        logger.info(f"\n{'=' * 60}")
        logger.info(f"總計: {len(results)} Skills, {total_docs} 文檔, {total_chunks} Chunks")
        logger.info("=" * 60)


async def main():
    """主程式入口"""
    # 從環境變數獲取配置
    config_path = os.environ.get(
        'SKILL_CONFIG_PATH',
        str(PROJECT_ROOT / 'scripts' / 'skill_data' / 'skill_config.json')
    )
    skill_filter = os.environ.get('SKILL_FILTER', None)
    force_all = os.environ.get('FORCE_ALL', 'false').lower() == 'true'
    use_smart_strategy = os.environ.get('SMART_REBUILD', 'true').lower() == 'true'

    # 確保日誌目錄存在
    log_dir = PROJECT_ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)

    try:
        rebuilder = SkillConfigRebuilder(config_path)
        results, rebuild_scope = await rebuilder.rebuild_all(
            skill_filter=skill_filter,
            force_all=force_all,
            use_smart_strategy=use_smart_strategy
        )

        if results:
            logger.info(f"\n✅ 重建完成！(範圍: {rebuild_scope or 'all'})")
            return 0
        else:
            if rebuild_scope == SmartRebuildStrategy.RebuildScope.NONE:
                logger.info("\n⚠️ 智能策略判斷無需重建")
                return 0
            else:
                logger.warning("\n⚠️ 沒有成功建立任何 Skills")
                return 1

    except Exception as e:
        logger.error(f"\n❌ 重建失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
