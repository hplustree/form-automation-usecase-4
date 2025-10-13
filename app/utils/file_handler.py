from typing import List
from pathlib import Path
from fuzzywuzzy import fuzz, process
import weaviate
import re
from langchain_community.document_loaders import (
    PyMuPDFLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredPowerPointLoader,
)
from langchain.docstore.document import Document
from io import BytesIO
import tempfile
from app.logging_config import logger

class DocumentLoader:
    SUPPORTED_EXTENSIONS = {
        ".pdf": PyMuPDFLoader,
        ".docx": UnstructuredWordDocumentLoader,
        ".doc": UnstructuredWordDocumentLoader,
        ".pptx": UnstructuredPowerPointLoader,
        ".ppt": UnstructuredPowerPointLoader,
        ".txt": None,  # Plain text support
    }

    def load_document(self, file_path: Path) -> List[Document]:
        """Load documents from a local file path."""
        ext = file_path.suffix.lower()
        loader_class = self.SUPPORTED_EXTENSIONS.get(ext)
        if loader_class is None and ext != ".txt":
            logger.error(f"Unsupported file type: {ext}")
            raise ValueError(f"Unsupported file type: {ext}")
        try:
            if ext == ".txt":
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                documents = [Document(page_content=content, metadata={"source": str(file_path)})]
            else:
                documents = loader_class(str(file_path)).load()
            logger.info(f"Loaded {len(documents)} documents from {file_path}")
            return documents
        except Exception as e:
            logger.error(f"Failed to load document from {file_path}: {str(e)}")
            raise

    def load_document_from_content(self, file_content: bytes, filename: str) -> List[Document]:
        """Load documents from raw file content (bytes)."""
        ext = Path(filename).suffix.lower()
        loader_class = self.SUPPORTED_EXTENSIONS.get(ext)
        if loader_class is None and ext != ".txt":
            logger.error(f"Unsupported file type for {filename}: {ext}")
            raise ValueError(f"Unsupported file type: {ext}")
        try:
            if ext == ".txt":
                content = file_content.decode('utf-8')
                documents = [Document(page_content=content, metadata={"source": filename})]
                logger.info(f"Loaded text document from content for {filename}")
                return documents
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            documents = loader_class(temp_file_path).load()
            logger.info(f"Loaded {len(documents)} documents from content for {filename}")
            Path(temp_file_path).unlink()  # Clean up temporary file
            return documents
        except Exception as e:
            logger.error(f"Failed to load document from content for {filename}: {str(e)}")
            if 'temp_file_path' in locals():
                Path(temp_file_path).unlink(missing_ok=True)
            raise

    def is_supported_file(self, filename: str) -> bool:
        """Check if the file extension is supported."""
        ext = Path(filename).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """Return list of supported file extensions."""
        return list(cls.SUPPORTED_EXTENSIONS.keys())
