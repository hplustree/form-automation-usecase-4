from typing import List, Dict, Optional
import weaviate
import json
from app.utils.file_handler import DocumentLoader
from datetime import datetime, timedelta
import redis as rqredis
import os
from app.logging_config import logger

DOC_TTL_DAYS = int(os.getenv("DOC_TTL_DAYS", 180))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", 86400))

sync_redis = rqredis.from_url(REDIS_URL)

class WeaviateClient:
    def __init__(self, url: str, document_loader: DocumentLoader):
        self.url = url
        self.document_loader = document_loader
        self.client = None
        self.class_name = "DataPipeline"
        self._connect()
        self._create_class_if_not_exists()

    def _connect(self):
        try:
            self.client = weaviate.Client(self.url, startup_period=60)
            if not self.client.is_ready():
                raise ConnectionError("Weaviate client not ready")
            logger.info(f"Connected to Weaviate at {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {str(e)}")
            raise

    def _create_class_if_not_exists(self):
        try:
            existing_classes = self.client.schema.get().get("classes", [])
            if not any(cls["class"] == self.class_name for cls in existing_classes):
                class_obj = {
                    "class": self.class_name,
                    "properties": [
                        {"name": "text", "dataType": ["text"]},
                        {"name": "project_id", "dataType": ["text"]},
                        {"name": "doc_id", "dataType": ["text"]},
                        {"name": "doc_name", "dataType": ["text"]},
                        {"name": "filename", "dataType": ["text"]},
                        {"name": "page_number", "dataType": ["int"]},
                        {"name": "chunk_number", "dataType": ["int"]},
                        {"name": "file_hash", "dataType": ["text"]},
                        {"name": "upload_timestamp", "dataType": ["text"]},
                        {"name": "expiry_timestamp", "dataType": ["text"]},
                        {"name": "section_title", "dataType": ["text"]},
                        {"name": "section_type", "dataType": ["text"]},
                        {"name": "key_terms", "dataType": ["text[]"]},
                        {"name": "content_type", "dataType": ["text"]},
                    ],
                    "vectorizer": "none"
                }
                self.client.schema.create_class(class_obj)
                logger.info(f"Created Weaviate class: {self.class_name}")
        except Exception as e:
            logger.error(f"Failed to create class {self.class_name}: {str(e)}")
            raise

    def delete_by_project_id(self, project_id: str):
        """Delete all chunks for a project"""
        try:
            self.client.batch.delete_objects(
                class_name=self.class_name,
                where={
                    "path": ["project_id"],
                    "operator": "Equal",
                    "valueText": project_id
                }
            )
            logger.info(f"Deleted objects for project_id={project_id}")
        except Exception as e:
            logger.error(f"Failed to delete objects for project_id={project_id}: {str(e)}")
            raise

    def delete_by_doc_id(self, project_id: str, doc_id: str):
        """Delete all chunks for a specific document in a project"""
        try:
            self.client.batch.delete_objects(
                class_name=self.class_name,
                where={
                    "operator": "And",
                    "operands": [
                        {
                            "path": ["project_id"],
                            "operator": "Equal",
                            "valueText": project_id
                        },
                        {
                            "path": ["doc_id"],
                            "operator": "Equal",
                            "valueText": doc_id
                        }
                    ]
                }
            )
            logger.info(f"Deleted objects for project_id={project_id}, doc_id={doc_id}")
        except Exception as e:
            logger.error(f"Failed to delete objects for project_id={project_id}, doc_id={doc_id}: {str(e)}")
            raise

    def insert_chunks(self, project_id: str, doc_id: str, doc_name: str, chunks: List[Dict], embeddings: List[List[float]]):
        """Insert document chunks with embeddings"""
        try:
            expiry_iso = (datetime.now() + timedelta(days=DOC_TTL_DAYS)).isoformat()
            for chunk, vector in zip(chunks, embeddings):
                chunk_data = {
                    "text": chunk["text"],
                    "project_id": project_id,
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "filename": chunk.get("filename", doc_name),
                    "page_number": chunk.get("page_numbers", [1])[0] if isinstance(chunk.get("page_numbers"), list) else 1,
                    "chunk_number": chunk.get("chunk_number", 0),
                    "file_hash": chunk.get("file_hash", ""),
                    "upload_timestamp": datetime.now().isoformat(),
                    "expiry_timestamp": expiry_iso,
                    "section_title": chunk.get("section_title"),
                    "section_type": chunk.get("section_type"),
                    "key_terms": chunk.get("key_terms", []),
                    "content_type": chunk.get("content_type", "text"),
                }
                
                self.client.data_object.create(
                    data_object=chunk_data,
                    class_name=self.class_name,
                    vector=vector
                )
            logger.info(f"Inserted {len(chunks)} chunks for project_id={project_id}, doc_id={doc_id}")
        except Exception as e:
            logger.error(f"Failed to insert chunks: {str(e)}")
            raise

    def search_similar(
        self,
        project_id: str,
        doc_id: str,
        query_vector: List[float],
        query_text: str,
        limit: int = 10,
        alpha: float = 0.5,
    ) -> List[Dict]:
        """Hybrid search for a specific document in a project"""
        try:
            logger.info(f"Performing hybrid search for project_id={project_id}, doc_id={doc_id}, limit={limit}")
            
            query = self.client.query.get(
                self.class_name,
                ["text", "filename", "doc_name", "page_number", "chunk_number", 
                 "content_type", "section_title", "section_type", "key_terms",
                 "_additional { distance, score }"]
            ).with_hybrid(
                query=query_text.lower(),
                vector=query_vector,
                alpha=alpha
            ).with_where({
                "operator": "And",
                "operands": [
                    {
                        "path": ["project_id"],
                        "operator": "Equal",
                        "valueText": project_id
                    },
                    {
                        "path": ["doc_id"],
                        "operator": "Equal",
                        "valueText": doc_id
                    }
                ]
            }).with_limit(limit)

            response = query.do()
            results_raw = response.get("data", {}).get("Get", {}).get(self.class_name, [])

            results = []
            # Compute max_bm25 using only numeric scores; default to 1.0 to avoid division by zero
            bm25_values = []
            for obj in results_raw:
                try:
                    score_val = obj.get("_additional", {}).get("score")
                    if score_val is not None:
                        bm25_values.append(float(score_val))
                except (TypeError, ValueError):
                    continue
            max_bm25 = max(bm25_values + [1.0]) or 1.0

            for obj in results_raw:
                try:
                    addl = obj.get("_additional", {})
                    # similarity from vector distance, fall back to 0.0 if missing/invalid
                    distance_val = addl.get("distance")
                    try:
                        similarity = 1 - float(distance_val) if distance_val is not None else 0.0
                    except (TypeError, ValueError):
                        similarity = 0.0

                    # bm25 score normalized, fall back to 0.0 if missing/invalid
                    score_val = addl.get("score")
                    try:
                        bm25_score = float(score_val) / max_bm25 if score_val is not None else 0.0
                    except (TypeError, ValueError):
                        bm25_score = 0.0

                    hybrid_score = (alpha * similarity) + ((1 - alpha) * bm25_score)

                    results.append({
                        "text": obj.get("text", ""),
                        "filename": obj.get("filename", ""),
                        "doc_name": obj.get("doc_name", ""),
                        "page_number": obj.get("page_number"),
                        "chunk_number": obj.get("chunk_number", 0),
                        "content_type": obj.get("content_type", "text"),
                        "section_title": obj.get("section_title"),
                        "section_type": obj.get("section_type"),
                        "key_terms": obj.get("key_terms", []),
                        "similarity": similarity,
                        "bm25_score": bm25_score,
                        "hybrid_score": hybrid_score
                    })
                except Exception as e:
                    logger.warning(f"Skipping result due to invalid score data: {str(e)}")
                    continue

            # Filter out entries that have both signals zero to reduce noise
            results = [r for r in results if (r["similarity"] > 0.0 or r["bm25_score"] > 0.0)]
            results.sort(key=lambda x: x["hybrid_score"], reverse=True)

            if not results:
                # Fallback: BM25-only search if hybrid yielded no usable results
                logger.info("Hybrid search empty; retrying with BM25-only search")
                bm25_query = self.client.query.get(
                    self.class_name,
                    ["text", "filename", "doc_name", "page_number", "chunk_number",
                     "content_type", "section_title", "section_type", "key_terms",
                     "_additional { score }"]
                ).with_hybrid(
                    query=query_text.lower(),
                    alpha=0.0
                ).with_where({
                    "operator": "And",
                    "operands": [
                        {
                            "path": ["project_id"],
                            "operator": "Equal",
                            "valueText": project_id
                        },
                        {
                            "path": ["doc_id"],
                            "operator": "Equal",
                            "valueText": doc_id
                        }
                    ]
                }).with_limit(limit)

                bm25_resp = bm25_query.do()
                bm25_raw = bm25_resp.get("data", {}).get("Get", {}).get(self.class_name, [])

                bm25_values = []
                for obj in bm25_raw:
                    try:
                        score_val = obj.get("_additional", {}).get("score")
                        if score_val is not None:
                            bm25_values.append(float(score_val))
                    except (TypeError, ValueError):
                        continue
                max_bm25_fallback = max(bm25_values + [1.0]) or 1.0

                for obj in bm25_raw:
                    try:
                        score_val = obj.get("_additional", {}).get("score")
                        try:
                            bm25_score = float(score_val) / max_bm25_fallback if score_val is not None else 0.0
                        except (TypeError, ValueError):
                            bm25_score = 0.0

                        results.append({
                            "text": obj.get("text", ""),
                            "filename": obj.get("filename", ""),
                            "doc_name": obj.get("doc_name", ""),
                            "page_number": obj.get("page_number", 1),
                            "chunk_number": obj.get("chunk_number", 0),
                            "content_type": obj.get("content_type", "text"),
                            "section_title": obj.get("section_title"),
                            "section_type": obj.get("section_type"),
                            "key_terms": obj.get("key_terms", []),
                            "similarity": 0.0,
                            "bm25_score": bm25_score,
                            "hybrid_score": bm25_score  # alpha=0.0
                        })
                    except Exception as e:
                        logger.warning(f"Skipping BM25 fallback result due to invalid score data: {str(e)}")
                        continue

                results.sort(key=lambda x: x["hybrid_score"], reverse=True)

            logger.info(f"Hybrid search returned {len(results)} results")
            return results[:limit]
        
        except Exception as e:
            logger.error(f"Hybrid search failed: {str(e)}")
            raise

    def get_all_chunks_by_doc_id(self, project_id: str, doc_id: str) -> List[Dict]:
        """Get all chunks for a specific document"""
        try:
            logger.info(f"Retrieving all chunks for project_id={project_id}, doc_id={doc_id}")
            
            query = self.client.query.get(
                self.class_name,
                ["text", "filename", "doc_name", "page_number", "chunk_number",
                 "content_type", "section_title", "section_type", "key_terms"]
            ).with_where({
                "operator": "And",
                "operands": [
                    {
                        "path": ["project_id"],
                        "operator": "Equal",
                        "valueText": project_id
                    },
                    {
                        "path": ["doc_id"],
                        "operator": "Equal",
                        "valueText": doc_id
                    }
                ]
            }).with_limit(10000)

            response = query.do()
            objs = response.get("data", {}).get("Get", {}).get(self.class_name, [])
            
            chunks = [
                {
                    "text": obj["text"],
                    "filename": obj["filename"],
                    "doc_name": obj["doc_name"],
                    "page_number": obj["page_number"],
                    "chunk_number": obj["chunk_number"],
                    "content_type": obj.get("content_type", "text"),
                    "section_title": obj.get("section_title"),
                    "section_type": obj.get("section_type"),
                    "key_terms": obj.get("key_terms", []),
                }
                for obj in objs
            ]
            chunks.sort(key=lambda x: (x.get("page_number", 0), x.get("chunk_number", 0)))
            logger.info(f"Retrieved {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Failed to retrieve chunks: {str(e)}")
            raise

    def close(self):
        logger.info("Weaviate client closed")
