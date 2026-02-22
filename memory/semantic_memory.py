"""
╔══════════════════════════════════════════════════════════╗
║      TARS — Semantic Memory (ChromaDB + RAG)             ║
╠══════════════════════════════════════════════════════════╣
║  Vector-based memory for:                                ║
║    • Semantic recall ("what did I say about X?")         ║
║    • Document ingestion (PDF, TXT, MD, DOCX)            ║
║    • RAG search over ingested documents                  ║
║  Uses ChromaDB for local vector storage with             ║
║  OpenAI text-embedding-3-small (fallback to default).    ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime

logger = logging.getLogger("tars.semantic")

CHROMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")


class OpenAIEmbeddingFunction:
    """ChromaDB-compatible embedding function using OpenAI text-embedding-3-small.
    
    Implements the chromadb.EmbeddingFunction protocol:
        __call__(input: Documents) -> Embeddings
    
    Falls back gracefully if OpenAI is unavailable.
    """

    def __init__(self, api_key, model="text-embedding-3-small"):
        self._api_key = api_key
        self._model = model
        self._available = False

        try:
            import openai
            self._client = openai.OpenAI(api_key=api_key)
            # Quick connectivity check — embed a single token
            self._client.embeddings.create(input=["test"], model=self._model)
            self._available = True
            logger.info(f"  🧠 OpenAI embeddings online ({self._model})")
        except ImportError:
            logger.info("  🧠 OpenAI embeddings unavailable (pip install openai)")
        except Exception as e:
            logger.warning(f"  🧠 OpenAI embeddings error: {e} — falling back to defaults")

    @property
    def available(self):
        return self._available

    def __call__(self, input):
        """Embed a list of documents. Returns list of float lists."""
        import openai
        try:
            response = self._client.embeddings.create(input=input, model=self._model)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.warning(f"  🧠 OpenAI embedding call failed: {e}")
            raise


class SemanticMemory:
    """Vector-based semantic memory for TARS.
    
    Provides three collections:
        1. conversations — stores user messages and TARS responses
        2. knowledge — stores saved facts, preferences, learned patterns
        3. documents — stores ingested document chunks (RAG)
    
    Falls back gracefully if ChromaDB is not installed.
    """

    def __init__(self, base_dir=None, config=None):
        self._client = None
        self._collections = {}
        self._available = False
        self._embedding_fn = None
        self._base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self._chroma_dir = os.path.join(self._base_dir, "memory", "chroma_db")

        try:
            import chromadb
            from chromadb.config import Settings

            os.makedirs(self._chroma_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=self._chroma_dir,
                settings=Settings(anonymized_telemetry=False),
            )

            # Try OpenAI embeddings — fall back to ChromaDB defaults
            openai_key = None
            if config:
                # Check multiple config locations for the key
                openai_key = (
                    config.get("memory", {}).get("openai_api_key")
                    or config.get("openai", {}).get("api_key")
                    or os.environ.get("OPENAI_API_KEY")
                )

            if openai_key:
                ef = OpenAIEmbeddingFunction(api_key=openai_key)
                if ef.available:
                    self._embedding_fn = ef

            embed_label = "OpenAI text-embedding-3-small" if self._embedding_fn else "default"

            # Create collections (with embedding function if available)
            col_kwargs = {}
            if self._embedding_fn:
                col_kwargs["embedding_function"] = self._embedding_fn

            self._collections["conversations"] = self._client.get_or_create_collection(
                name="conversations",
                metadata={"hnsw:space": "cosine"},
                **col_kwargs,
            )
            self._collections["knowledge"] = self._client.get_or_create_collection(
                name="knowledge",
                metadata={"hnsw:space": "cosine"},
                **col_kwargs,
            )
            self._collections["documents"] = self._client.get_or_create_collection(
                name="documents",
                metadata={"hnsw:space": "cosine"},
                **col_kwargs,
            )

            self._available = True
            total = sum(c.count() for c in self._collections.values())
            logger.info(f"  🧠 Semantic memory online ({total} vectors, embeddings: {embed_label})")

        except ImportError:
            logger.info("  🧠 Semantic memory unavailable (install: pip install chromadb)")
        except Exception as e:
            logger.warning(f"  🧠 Semantic memory error: {e}")

    @property
    def available(self):
        return self._available

    # ─── Conversation Memory ─────────────────────────

    def store_conversation(self, user_message, tars_response, metadata=None):
        """Store a conversation exchange for semantic recall."""
        if not self._available:
            return

        try:
            col = self._collections["conversations"]
            ts = datetime.now().isoformat()
            doc_id = hashlib.md5(f"{ts}:{user_message[:100]}".encode()).hexdigest()

            # Store user message
            col.add(
                documents=[f"User: {user_message}\nTARS: {tars_response[:500]}"],
                metadatas=[{
                    "timestamp": ts,
                    "type": "conversation",
                    "user_message": user_message[:200],
                    **(metadata or {}),
                }],
                ids=[doc_id],
            )
        except Exception as e:
            logger.debug(f"  🧠 Conversation store error: {e}")

    # ─── Knowledge Memory ────────────────────────────

    def store_knowledge(self, key, content, category="general"):
        """Store a knowledge entry for semantic retrieval."""
        if not self._available:
            return {"success": False, "error": True, "content": "Semantic memory unavailable (pip install chromadb)."}

        try:
            col = self._collections["knowledge"]
            doc_id = hashlib.md5(f"knowledge:{key}".encode()).hexdigest()

            # Upsert (add or update)
            col.upsert(
                documents=[f"{key}: {content}"],
                metadatas=[{
                    "key": key,
                    "category": category,
                    "timestamp": datetime.now().isoformat(),
                }],
                ids=[doc_id],
            )
            return {"success": True, "content": f"Stored in semantic memory: {key}"}
        except Exception as e:
            return {"success": False, "error": True, "content": f"Semantic store error: {e}"}

    # ─── Semantic Recall ─────────────────────────────

    def recall(self, query, n_results=5, collection="all"):
        """Semantic search across memory.
        
        Args:
            query: Natural language query
            n_results: Max results to return
            collection: "all", "conversations", "knowledge", or "documents"
        
        Returns:
            Standard tool result dict
        """
        if not self._available:
            return {"success": False, "error": True, "content": "Semantic memory unavailable (pip install chromadb)."}

        try:
            results = []

            collections_to_search = (
                [self._collections[collection]] if collection in self._collections
                else list(self._collections.values())
            )

            for col in collections_to_search:
                if col.count() == 0:
                    continue

                res = col.query(
                    query_texts=[query],
                    n_results=min(n_results, col.count()),
                )

                for i, doc in enumerate(res["documents"][0]):
                    meta = res["metadatas"][0][i]
                    distance = res["distances"][0][i] if res.get("distances") else None
                    relevance = f" (relevance: {1 - distance:.2f})" if distance is not None else ""

                    source = meta.get("type", col.name)
                    timestamp = meta.get("timestamp", "")
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            timestamp = dt.strftime("%b %d, %Y")
                        except Exception:
                            pass

                    results.append({
                        "source": source,
                        "timestamp": timestamp,
                        "relevance": 1 - distance if distance else 0,
                        "content": doc[:500],
                    })

            # Sort by relevance
            results.sort(key=lambda x: x["relevance"], reverse=True)
            results = results[:n_results]

            if not results:
                return {"success": True, "content": f"No semantic matches for '{query}'."}

            lines = [f"## Semantic Memory Results for: '{query}'\n"]
            for r in results:
                lines.append(f"**[{r['source']}]** {r['timestamp']} (relevance: {r['relevance']:.2f})")
                lines.append(f"  {r['content'][:300]}")
                lines.append("")

            return {"success": True, "content": "\n".join(lines)}

        except Exception as e:
            return {"success": False, "error": True, "content": f"Semantic recall error: {e}"}

    # ─── Document Ingestion (RAG) ─────────────────────

    def ingest_document(self, file_path, chunk_size=1000, chunk_overlap=200):
        """Ingest a document for RAG search.
        
        Supports: .txt, .md, .pdf, .docx, .py, .json, .csv
        
        Args:
            file_path: Path to the document
            chunk_size: Characters per chunk
            chunk_overlap: Overlap between chunks
        
        Returns:
            Standard tool result dict
        """
        if not self._available:
            return {"success": False, "error": True, "content": "Semantic memory unavailable (pip install chromadb)."}

        file_path = os.path.expanduser(file_path)
        if not os.path.exists(file_path):
            return {"success": False, "error": True, "content": f"File not found: {file_path}"}

        try:
            # Extract text based on file type
            ext = os.path.splitext(file_path)[1].lower()
            text = self._extract_text(file_path, ext)

            if not text:
                return {"success": False, "error": True, "content": f"Could not extract text from {file_path}"}

            # Chunk the text
            chunks = self._chunk_text(text, chunk_size, chunk_overlap)

            if not chunks:
                return {"success": False, "error": True, "content": "No text chunks generated."}

            # Store chunks
            col = self._collections["documents"]
            filename = os.path.basename(file_path)
            file_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]

            ids = []
            documents = []
            metadatas = []

            for i, chunk in enumerate(chunks):
                doc_id = f"doc_{file_hash}_{i}"
                ids.append(doc_id)
                documents.append(chunk)
                metadatas.append({
                    "source": filename,
                    "file_path": file_path,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "type": "document",
                    "timestamp": datetime.now().isoformat(),
                })

            col.upsert(documents=documents, metadatas=metadatas, ids=ids)

            logger.info(f"  📄 Ingested {filename}: {len(chunks)} chunks")
            return {
                "success": True,
                "content": f"Ingested '{filename}' into semantic memory: {len(chunks)} chunks ({len(text)} chars). You can now search it with recall_memory."
            }

        except Exception as e:
            return {"success": False, "error": True, "content": f"Document ingestion error: {e}"}

    def search_documents(self, query, n_results=5):
        """Search only the documents collection (RAG).
        
        Returns relevant chunks from ingested documents.
        """
        return self.recall(query, n_results=n_results, collection="documents")

    # ─── Text Extraction ─────────────────────────────

    @staticmethod
    def _extract_text(file_path, ext):
        """Extract text from various file formats."""
        if ext in (".txt", ".md", ".py", ".json", ".csv", ".yaml", ".yml",
                    ".js", ".ts", ".html", ".css", ".sh", ".bash"):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()

        elif ext == ".pdf":
            try:
                import subprocess
                # Use macOS built-in textutil or pdftotext
                result = subprocess.run(
                    ["pdftotext", "-layout", file_path, "-"],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout

                # Fallback: try python-based PDF reading
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(file_path)
                    text_parts = []
                    for page in reader.pages:
                        text_parts.append(page.extract_text() or "")
                    return "\n\n".join(text_parts)
                except ImportError:
                    pass

                return None
            except Exception as e:
                logger.warning(f"  📄 PDF extraction error: {e}")
                return None

        elif ext == ".docx":
            try:
                from docx import Document
                doc = Document(file_path)
                return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                logger.warning("  📄 DOCX needs: pip install python-docx")
                return None
            except Exception as e:
                logger.warning(f"  📄 DOCX extraction error: {e}")
                return None

        else:
            # Try as plain text
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except Exception:
                return None

    @staticmethod
    def _chunk_text(text, chunk_size=1000, overlap=200):
        """Split text into overlapping chunks."""
        if not text:
            return []

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size

            # Try to break at a sentence boundary
            if end < len(text):
                for sep in ["\n\n", "\n", ". ", "! ", "? "]:
                    last_sep = text.rfind(sep, start + chunk_size // 2, end + 100)
                    if last_sep > start:
                        end = last_sep + len(sep)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - overlap
            if start >= len(text):
                break

        return chunks

    # ─── Stats ───────────────────────────────────────

    def get_stats(self):
        """Get memory statistics."""
        if not self._available:
            return {"available": False}

        stats = {"available": True, "collections": {}}
        for name, col in self._collections.items():
            stats["collections"][name] = col.count()
        stats["total_vectors"] = sum(stats["collections"].values())
        return stats

    def clear_all(self):
        """Delete all vectors from all collections."""
        if not self._available:
            return
        for name, col in self._collections.items():
            try:
                # Get all IDs and delete them
                all_ids = col.get()["ids"]
                if all_ids:
                    col.delete(ids=all_ids)
            except Exception as e:
                logger.debug(f"  🧠 Clear {name} error: {e}")
