import os
from typing import List, Dict, Optional, Tuple, Iterable
import hashlib
from datetime import datetime
from pathlib import Path
import re
import uuid
import fitz  # PyMuPDF
import subprocess
import base64
import psutil
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from langchain_core.messages import HumanMessage
from app.utils.file_handler import DocumentLoader
import spacy
import time
import random
from spacy.cli import download
from dotenv import load_dotenv
import pdfplumber
import logging
import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.utils.locks import libreoffice_global_lock
from functools import partial
from multiprocessing import Pool

from app.logging_config import logger

# Load environment variables
load_dotenv()

# Initialize S3 client
S3_BUCKET = os.getenv("AWS_S3_BUCKET", "dev-daex-siso")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_REQUEST_TIMEOUT = int(os.getenv("S3_REQUEST_TIMEOUT", 10))

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# Image detection constants
_IMG_LIKE_THRESHOLD = 0.60
_IMG_TO_TEXT_MULTIPLIER = 2.0
_INCLUDE_DRAWINGS = True


def _iter_text_rects(rawdict) -> Iterable[Tuple[float, float, float, float]]:
    for b in rawdict.get("blocks", []):
        if b.get("type") == 0:  # text
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    bbox = s.get("bbox")
                    if bbox:
                        yield bbox


def _iter_image_rects(rawdict) -> Iterable[Tuple[float, float, float, float]]:
    for b in rawdict.get("blocks", []):
        if b.get("type") == 1:  # image
            bbox = b.get("bbox")
            if bbox:
                yield bbox


def _iter_drawing_rects(page_obj: fitz.Page) -> Iterable[Tuple[float, float, float, float]]:
    for d in page_obj.get_drawings():
        r = d.get("rect")
        if r:
            yield (r.x0, r.y0, r.x1, r.y1)


def _sum_area(rects: Iterable[Tuple[float, float, float, float]]) -> float:
    return sum(max(0.0, x1 - x0) * max(0.0, y1 - y0) for (x0, y0, x1, y1) in rects)


def _classify_bool(graphics_cov: float, text_cov: float,
                   img_like_threshold: float, img_to_text_multiplier: float) -> bool:
    return (graphics_cov >= img_like_threshold) or (
        graphics_cov >= img_to_text_multiplier * max(text_cov, 1e-9)
    )


def _process_page_detection(args):
    """Worker: process a single page for image detection."""
    pdf_path, page_num, include_drawings, img_like_threshold, img_to_text_multiplier = args
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_num]
        rect = page.rect
        page_area = float(rect.width * rect.height)

        raw = page.get_text("rawdict")
        text_area = _sum_area(_iter_text_rects(raw))
        img_area = _sum_area(_iter_image_rects(raw))
        draw_area = _sum_area(_iter_drawing_rects(page)) if include_drawings else 0.0

        text_cov = min(1.0, text_area / page_area if page_area > 0 else 0.0)
        graphics_cov = min(1.0, (img_area + draw_area) / page_area if page_area > 0 else 0.0)

        if _classify_bool(graphics_cov, text_cov,
                          img_like_threshold, img_to_text_multiplier):
            return page_num + 1  # 1-based
        return None
    finally:
        doc.close()


def detect_pdf_image_like_pages(
    pdf_path: str,
    *,
    include_drawings: bool = _INCLUDE_DRAWINGS,
    img_like_threshold: float = _IMG_LIKE_THRESHOLD,
    img_to_text_multiplier: float = _IMG_TO_TEXT_MULTIPLIER,
    workers: int = 10,
) -> List[int]:
    """Process each page independently in parallel. Returns 1-based page numbers that are image-like."""
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    doc.close()

    args = [
        (pdf_path, p, include_drawings, img_like_threshold, img_to_text_multiplier)
        for p in range(num_pages)
    ]

    with Pool(processes=workers) as pool:
        results = pool.map(_process_page_detection, args)

    # Filter Nones + sort
    return sorted([p for p in results if p is not None])


# Pydantic model for chunk validation
class DocumentChunk(BaseModel):
    text: str = Field(..., min_length=1, description="Cleaned text content of the chunk")
    filename: str = Field(..., description="Name of the source file")
    document_name: str = Field(..., description="Base name of the document without extension")
    page_numbers: List[int] = Field(..., min_items=1, description="List of page numbers associated with the chunk")
    original_texts: Dict[int, str] = Field(..., description="Original text for each page in page_numbers")
    chunk_number: int = Field(..., ge=0, description="Sequential chunk number")
    filepath: str = Field(..., description="File path or identifier (e.g., S3 path)")
    file_hash: str = Field(..., pattern=r'^[a-f0-9]{64}$', description="SHA256 hash of the file content")
    chunk_hash: str = Field(..., pattern=r'^[a-f0-9]{64}$', description="SHA256 hash of the chunk text")
    upload_timestamp: str = Field(..., description="ISO timestamp of when the chunk was created")
    section_title: Optional[str] = Field(None, description="Extracted section title, if any")
    section_type: Optional[str] = Field(None, description="Type of section (e.g., heading, numbered)")
    key_terms: List[str] = Field(default_factory=list, description="Key terms extracted from the chunk")
    content_type: str = Field(..., description="Type of content (text or text_with_image_summary)")

class EmbeddingService:
    def __init__(
        self,
        embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
        api_key: Optional[str] = None,
        llm_model: str = os.getenv("LLM_MODEL_GPT_5", "gpt-5"),
        min_chunk_size: int = int(os.getenv("MIN_CHUNK_SIZE", 100)),
        max_completion_tokens: int = int(os.getenv("MAX_RESPONSE_TOKENS", 500)),
        chunk_size: int = int(os.getenv("CHUNK_SIZE", 1000)),
        chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", 200)),
        max_concurrent_image_summarization: int = int(os.getenv("MAX_CONCURRENT_PROMPTS", 4)),
        max_concurrent_embeddings: int = int(os.getenv("MAX_CONCURRENT_EMBEDDINGS", 4)),
    ):
        self.api_key = api_key or os.getenv("LITELLM_MASTER_KEY")
        if not self.api_key:
            raise ValueError("LiteLLM Master Key is required")
        
        self.min_chunk_size = min_chunk_size
        self.llm_model = llm_model
        self.document_loader = DocumentLoader()
        self.max_completion_tokens = max_completion_tokens
        self.max_concurrent_image_summarization = max_concurrent_image_summarization
        self.max_concurrent_embeddings = max_concurrent_embeddings

        # Main embeddings client for single requests
        self.embeddings = OpenAIEmbeddings(
            model=embedding_model,
            openai_api_key=self.api_key,
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:4000")
        )
        
        # RecursiveCharacterTextSplitter optimized for legal documents
        # Using separators that respect document structure
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=[
                "\n\n\n",  # Multiple line breaks (section boundaries)
                "\n\n",    # Paragraph breaks
                "\n",      # Line breaks
                ". ",      # Sentence endings
                ", ",      # Clause breaks
                " ",       # Word boundaries
                ""         # Character level (fallback)
            ],
            is_separator_regex=False,
        )
        
        self.chat_client = ChatOpenAI(
            model=llm_model,
            api_key=self.api_key,
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:4000"),
            max_tokens=max_completion_tokens
        )
        
        # Initialize spaCy model
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")
        
        # Thread pool executors
        self.image_executor = ThreadPoolExecutor(max_workers=max_concurrent_image_summarization)
        self.embedding_executor = ThreadPoolExecutor(max_workers=max_concurrent_embeddings)

    def _create_embedding_client(self):
        """Create a new OpenAIEmbeddings client for thread-safe concurrent operations."""
        return OpenAIEmbeddings(
            model=self.embeddings.model,
            openai_api_key=self.api_key,
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:4000")
        )

    def _create_chat_client(self):
        """Create a new ChatOpenAI client for thread-safe concurrent operations."""
        return ChatOpenAI(
            model=self.llm_model,
            api_key=self.api_key,
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:4000"),
            max_tokens=self.max_completion_tokens
        )

    def _generate_single_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text using a fresh client instance with retries."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = self._create_embedding_client()
                return client.embed_query(text)
            except Exception as e:
                error_str = str(e).lower()
                if '429' in error_str or 'rate limit' in error_str or 'throttling' in error_str:
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Rate limit hit for single embedding (text length: {len(text)}), retrying attempt {attempt+1}/{max_retries} after {sleep_time:.2f} seconds")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Error generating embedding for text (length: {len(text)}): {str(e)}")
                    raise
        raise Exception("Max retries exceeded due to rate limiting for single embedding")

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts concurrently."""
        if not texts:
            return []
        
        if len(texts) == 1:
            # For single text, use the main client directly
            return [self.embeddings.embed_query(texts[0])]
        
        logger.info(f"Generating embeddings for {len(texts)} texts using {self.max_concurrent_embeddings} concurrent workers")
        start_time = time.time()
        
        embeddings_results = [None] * len(texts)  # Preserve order
        futures_to_index = {}
        
        with ThreadPoolExecutor(max_workers=self.max_concurrent_embeddings) as executor:
            # Submit all embedding tasks
            for i, text in enumerate(texts):
                future = executor.submit(self._generate_single_embedding, text)
                futures_to_index[future] = i
            
            # Collect results as they complete
            completed_count = 0
            for future in as_completed(futures_to_index):
                index = futures_to_index[future]
                completed_count += 1
                
                try:
                    embedding = future.result()
                    embeddings_results[index] = embedding
                    logger.debug(f"Completed embedding {completed_count}/{len(texts)} (index: {index})")
                except Exception as e:
                    logger.error(f"Failed to generate embedding for text at index {index}: {str(e)}")
                    raise
        
        total_time = time.time() - start_time
        logger.info(f"Generated {len(texts)} embeddings in {total_time:.2f}s (avg: {total_time/len(texts):.3f}s per embedding)")
        
        # Performance comparison logging
        estimated_sequential_time = total_time * self.max_concurrent_embeddings
        speedup = estimated_sequential_time / total_time if total_time > 0 else 1
        logger.info(f"Embedding speedup: ~{speedup:.1f}x faster than sequential processing")
        
        return embeddings_results

    def summarize_image(self, image_path: str, page_number: int = None) -> str:
        """Summarize image content using ChatOpenAI with retry logic."""
        max_retries = 10
        initial_delay = 2
        max_delay = 60
        
        for attempt in range(max_retries):
            try:
                # Create a fresh client for this request
                client = self._create_chat_client()
                
                with open(image_path, "rb") as image_file:
                    image_data = image_file.read()

                image_base64 = base64.b64encode(image_data).decode("utf-8")

                message = HumanMessage(
                    content=[
                        {"type": "text", "text": "Summarize the image content in simple terms. If it's a chart or flow, describe it clearly."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                    ]
                )

                response = client.invoke([message])
                
                page_info = f" (page {page_number})" if page_number else ""
                logger.info(f"Successfully summarized image: {image_path}{page_info}")
                return response.content

            except Exception as e:
                if "rate_limit_exceeded" in str(e).lower() or "429" in str(e):
                    jitter = random.uniform(0.5, 1)
                    delay = min(initial_delay * (2 ** attempt) + jitter, max_delay)
                    page_info = f" (page {page_number})" if page_number else ""
                    logger.warning(f"Rate limit hit for {image_path}{page_info}. Retry {attempt + 1}/{max_retries} after {delay:.2f}s")
                    time.sleep(delay)
                else:
                    page_info = f" (page {page_number})" if page_number else ""
                    logger.error(f"Error summarizing image {image_path}{page_info}: {str(e)}")
                    return f"Error summarizing image: {str(e)}"
        
        page_info = f" (page {page_number})" if page_number else ""
        logger.error(f"Failed to summarize {image_path}{page_info} after {max_retries} attempts due to rate limit errors.")
        return "Failed to summarize due to repeated rate limit errors."

    def _process_single_image_task(self, page_num: int, pdf_path: str, output_folder: str) -> tuple:
        """Process a single page's images."""
        start_time = time.time()
        
        try:
            logger.info(f"Processing page {page_num} starting")
            
            doc = fitz.open(pdf_path)
            page = doc[page_num - 1]  # page_num is 1-indexed

            # Generate unique filename with timestamp to avoid conflicts
            unique_id = uuid.uuid4().hex
            timestamp = int(time.time() * 1000000)  # microseconds
            image_path = os.path.join(output_folder, f"page_{page_num}_{timestamp}_{unique_id}.png")
            
            # Extract and save page as image
            pix = page.get_pixmap(dpi=200)
            pix.save(image_path)
            doc.close()
            
            logger.info(f"Image extracted page {page_num}, starting API call")
            
            # Summarize the image
            api_start_time = time.time()
            summary = self.summarize_image(image_path, page_num)
            api_time = time.time() - api_start_time
            
            # Clean up the image file
            if os.path.exists(image_path):
                os.remove(image_path)
            
            total_time = time.time() - start_time
            logger.info(f"Summary ready page {page_num} - Total: {total_time:.2f}s, API: {api_time:.2f}s")
            
            return page_num, summary, None
            
        except Exception as e:
            total_time = time.time() - start_time
            error_msg = f"Error processing page {page_num}: {str(e)}"
            logger.error(f"Error page {page_num} after {total_time:.2f}s: {error_msg}")
            return page_num, None, error_msg

    def detect_images_in_pdf_concurrent(self, pdf_path: str, output_folder: str = "temp_image_summaries") -> Dict:
        """Detect image-like pages in PDF using area-based classification and generate summaries concurrently."""
        # Use the new detection function to find image-like pages
        workers = int(os.getenv("IMAGE_DETECTION_WORKERS", 10))
        image_like_pages = detect_pdf_image_like_pages(pdf_path, workers=workers)
        
        if not image_like_pages:
            logger.info(f"No image-like pages found in {pdf_path}")
            return {}
        
        # Create output directory
        os.makedirs(output_folder, exist_ok=True)
        
        logger.info(f"Found {len(image_like_pages)} image-like pages in {pdf_path}. Processing concurrently with max {self.max_concurrent_image_summarization} workers...")
        
        summaries = {}
        
        # Process images concurrently
        with ThreadPoolExecutor(max_workers=self.max_concurrent_image_summarization) as executor:
            # Submit all tasks
            start_time = time.time()
            futures_to_page = {}
            
            for page_num in image_like_pages:
                future = executor.submit(self._process_single_image_task, page_num, pdf_path, output_folder)
                futures_to_page[future] = page_num
                logger.info(f"Started processing page {page_num}")
            
            logger.info(f"Concurrent status: {min(len(image_like_pages), self.max_concurrent_image_summarization)} tasks running simultaneously")
            
            # Collect results as they complete
            completed_count = 0
            for future in as_completed(futures_to_page):
                page_num, summary, error = future.result()
                completed_count += 1
                
                if error:
                    summaries[page_num] = f"Error processing image: {error}"
                    logger.error(f"Failed page {page_num}: {error}")
                elif summary:
                    summaries[page_num] = summary
                    logger.info(f"Completed page {page_num} ({completed_count}/{len(image_like_pages)})")
                else:
                    logger.warning(f"No summary for page {page_num}")
                
                # Show remaining active tasks
                remaining = len(image_like_pages) - completed_count
                if remaining > 0:
                    active_workers = min(remaining, self.max_concurrent_image_summarization)
                    logger.info(f"Concurrent status: {active_workers} workers still active, {remaining} tasks remaining")
            
            total_time = time.time() - start_time
            logger.info(f"Finished all {len(image_like_pages)} images in {total_time:.2f}s (avg: {total_time/len(image_like_pages):.2f}s per image)")
        
        # Clean up output folder if empty
        if os.path.exists(output_folder) and not os.listdir(output_folder):
            os.rmdir(output_folder)
        
        # Performance summary
        if len(summaries) > 0:
            logger.info(f"Performance: Generated {len(summaries)} summaries using {self.max_concurrent_image_summarization} concurrent workers")
            estimated_sequential_time = total_time * self.max_concurrent_image_summarization
            speedup = estimated_sequential_time / total_time if total_time > 0 else 1
            logger.info(f"Speedup: ~{speedup:.1f}x faster than sequential processing")
        
        return summaries

    def detect_images_in_pdf(self, pdf_path: str, output_folder: str = "temp_image_summaries") -> Dict:
        """Detect images in PDF, save them, and generate summaries - now uses concurrent processing."""
        return self.detect_images_in_pdf_concurrent(pdf_path, output_folder)

    def convert_to_pdf(self, file_content: bytes, filename: str) -> str:
        """Convert PPT/PPTX/DOCX to PDF, preferring HTML method for DOCX, with fallback to LibreOffice."""
        file_extension = Path(filename).suffix.lower()
        temp_dir = Path("temp_files")
        temp_dir.mkdir(exist_ok=True)
        root_path_app = '/app'

        # Sanitize filename (LibreOffice can choke on spaces/brackets)
        unique_id = uuid.uuid4().hex
        safe_filename = f"{re.sub(r'[^a-zA-Z0-9_.-]', '_', Path(filename).stem)}_{unique_id}{file_extension}" 
        pdf_filename = f"{re.sub(r'[^a-zA-Z0-9_.-]', '_', Path(filename).stem)}_{unique_id}"   
        temp_file = temp_dir / safe_filename
        output_path = root_path_app / temp_dir / f"{pdf_filename}.pdf"

        # Write input file
        with open(temp_file, "wb") as f:
            f.write(file_content)

        if file_extension == ".pdf":
            logger.info(f"{filename} is already a PDF, skipping conversion")
            return str(temp_file)

        logger.info(f"Converting {filename} to PDF...")

        # Check if libreoffice is available
        if subprocess.run(["which", "libreoffice"], capture_output=True).returncode != 0:
            logger.warning("LibreOffice not found, falling back to direct processing")
            return str(temp_file)  # return original path

        try:
            with libreoffice_global_lock():
                logger.info("Acquired LibreOffice lock; starting conversion")
            
                result = subprocess.run(
                    [
                        "libreoffice", "--headless", "--invisible", "--nologo", "--nodefault",
                        "--nolockcheck", "--norestore",
                        "--convert-to", "pdf:writer_pdf_Export:FilterOptions=EmbedStandardFonts=true;ExportImages=false;ExportFormFields=false;ExportNotes=false;UseTaggedPDF=false;ExportBookmarks=false;ExportDrawing=false;ExportGraphics=false",
                        str(temp_file), "--outdir", str(temp_dir)
                    ],
                    check=True,
                    timeout=300,
                    capture_output=True,
                    text=True
                )
            logger.info(f"LibreOffice stdout: {result.stdout.strip()}")
            logger.info(f"LibreOffice stderr: {result.stderr.strip()}")

            if not output_path.exists():
                logger.error(f"Expected PDF not created at {output_path}, keeping original file")
                return str(temp_file)  # fallback to original file

            logger.info(f"Successfully converted {filename} to {output_path} via LibreOffice")

            # Conversion worked → safe to delete the temp input file
            try:
                os.remove(temp_file)
            except Exception as e:
                logger.warning(f"Could not remove temp file {temp_file}: {e}")

            return str(output_path)

        except subprocess.CalledProcessError as e:
            logger.warning(f"LibreOffice conversion failed: {e.stderr}")
            return str(temp_file)
        except Exception as e:
            logger.error(f"Unexpected error during conversion: {e}")
            return str(temp_file)

    def clean_text(self, text: str) -> str:
        """Remove HTML tags and excessive whitespace from text."""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text

    def _extract_pages_with_positions(self, pdf_path: str) -> List[Dict]:
        """
        Extract text from PDF with precise character positions using pdfplumber.
        Returns list of page data with text and character positions.
        """
        pages_data = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                try:
                    chars = page.chars
                    page_text = page.extract_text() or ""
                    
                    char_positions = []
                    for char_data in chars:
                        char_positions.append({
                            'char': char_data.get('text', ''),
                            'x0': char_data.get('x0', 0),
                            'y0': char_data.get('y0', 0),
                            'x1': char_data.get('x1', 0),
                            'y1': char_data.get('y1', 0),
                        })
                    
                    pages_data.append({
                        'page_number': page_num,
                        'text': page_text,
                        'char_positions': char_positions,
                        'text_length': len(page_text)
                    })
                    
                except Exception as e:
                    logger.warning(f"Error extracting page {page_num}: {e}")
                    pages_data.append({
                        'page_number': page_num,
                        'text': "",
                        'char_positions': [],
                        'text_length': 0
                    })
        
        return pages_data

    def _find_chunk_page_numbers(self, chunk_text: str, pages_data: List[Dict], similarity_threshold: float = 0.3) -> List[int]:
        """
        Find all relevant page numbers for a chunk using advanced text matching.
        Returns a list of page numbers with similarity above the threshold.
        """
        clean_chunk = self.clean_text(chunk_text).lower()
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should'}
        chunk_words = [word for word in clean_chunk.split() if word not in stop_words and len(word) > 2]
        
        if not chunk_words:
            return [1]
        
        page_numbers = []
        page_scores = []
        
        for page_data in pages_data:
            page_text = self.clean_text(page_data['text']).lower()
            
            if not page_text:
                continue
            
            if clean_chunk in page_text:
                page_numbers.append(page_data['page_number'])
                page_scores.append((page_data['page_number'], 1.0))
                continue
            
            page_words = [word for word in page_text.split() if word not in stop_words and len(word) > 2]
            
            if not page_words:
                continue
            
            chunk_set = set(chunk_words)
            page_set = set(page_words)
            intersection = len(chunk_set.intersection(page_set))
            union = len(chunk_set.union(page_set))
            
            if union > 0:
                jaccard_score = intersection / union
                order_score = 0
                if intersection > 0:
                    for i in range(len(chunk_words) - 1):
                        if chunk_words[i] in page_words and chunk_words[i + 1] in page_words:
                            chunk_idx = page_words.index(chunk_words[i])
                            if chunk_idx < len(page_words) - 1 and page_words[chunk_idx + 1] == chunk_words[i + 1]:
                                order_score += 1
                    order_score = order_score / max(1, len(chunk_words) - 1)
                
                final_score = jaccard_score * 0.7 + order_score * 0.3
                
                if final_score >= similarity_threshold:
                    page_numbers.append(page_data['page_number'])
                    page_scores.append((page_data['page_number'], final_score))
        
        if not page_numbers:
            page_numbers = [1]
            page_scores = [(1, 0.0)]
        
        logger.debug(f"Chunk mapped to pages {page_numbers} with scores {[f'page {p}: {s:.3f}' for p, s in page_scores]}")
        return sorted(page_numbers)

    def _create_overlapped_page_block(self, pages_data: List[Dict], current_page_idx: int, page_text_map: Dict[int, str], overlap_chars: int = 100) -> tuple[str, List[int]]:
        current_page = pages_data[current_page_idx]
        page_number = current_page['page_number']
        page_text = page_text_map.get(page_number, current_page['text'])
        page_numbers = [page_number]
        combined_text = page_text

        # Backward overlap (for splitting only)
        if current_page_idx > 0:
            prev_page_num = pages_data[current_page_idx - 1]['page_number']
            prev_text = page_text_map.get(prev_page_num, "")
            if prev_text:
                overlap_text = prev_text[-overlap_chars:] if len(prev_text) > overlap_chars else prev_text
                combined_text = overlap_text + "\n Current Page Text Starts: \n" + combined_text
                logger.debug(f"Added backward overlap from page {prev_page_num} for splitting ({len(overlap_text)} chars), but not stored in page_numbers")

        # Forward overlap (for splitting only)
        if current_page_idx < len(pages_data) - 1:
            next_page_num = pages_data[current_page_idx + 1]['page_number']
            next_text = page_text_map.get(next_page_num, "")
            if next_text:
                overlap_text = next_text[:overlap_chars] if len(next_text) > overlap_chars else next_text
                combined_text = combined_text + "\n Current Page Text End \n" + overlap_text
                logger.debug(f"Added forward overlap from page {next_page_num} for splitting ({len(overlap_text)} chars), but not stored in page_numbers")

        logger.debug(f"Created overlapped block for page {page_number} with splitting pages [prev/current/next], but stored page_numbers={page_numbers}")
        return combined_text, page_numbers

    def _process_single_page(self, idx: int, page_data: Dict, pages_data: List[Dict], page_text_map: Dict[int, str], 
                            original_page_text_map: Dict[int, str], filename: str, file_content: bytes) -> List[Dict]:
        """Process a single page, creating thread-safe resources and returning unvalidated chunk dictionaries."""
        # Create thread-safe text splitter instance
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.text_splitter._chunk_size,
            chunk_overlap=self.text_splitter._chunk_overlap,
            length_function=len,
            separators=self.text_splitter._separators,
            is_separator_regex=False,
        )
        
        block_text, block_page_numbers = self._create_overlapped_page_block(
            pages_data, idx, page_text_map, overlap_chars=50
        )
        if not block_text:
            logger.debug(f"Skipping empty block for pages {block_page_numbers}")
            return []
        
        text_chunks = text_splitter.split_text(block_text)
        logger.info(f"Split block for pages {block_page_numbers} into {len(text_chunks)} chunks")
        current_page_num = page_data['page_number']
        page_chunks = []
        for chunk_idx, chunk_text in enumerate(text_chunks):
            if len(chunk_text) < self.min_chunk_size:
                logger.debug(f"Skipping chunk {chunk_idx} due to length {len(chunk_text)}")
                continue
            cleaned_text = self.clean_text(chunk_text)
            if not cleaned_text:
                logger.debug(f"Skipping chunk {chunk_idx} due to empty cleaned text")
                continue
            contains_image_summary = "[Image Summary]" in chunk_text
            content_type = "text_with_image_summary" if contains_image_summary else "text"
            page_numbers = [current_page_num]
            original_texts = {
                current_page_num: original_page_text_map.get(current_page_num, "")
            }
            semantic_metadata = self._extract_semantic_metadata(cleaned_text)
            chunk_data = {
                "text": cleaned_text,
                "filename": filename,
                "document_name": Path(filename).stem,
                "page_numbers": page_numbers,
                "original_texts": original_texts,
                "chunk_number": None,  # Will be assigned later
                "filepath": filename,
                "file_hash": hashlib.sha256(file_content).hexdigest(),
                "chunk_hash": self._hash_text(cleaned_text),
                "upload_timestamp": datetime.now().isoformat(),
                "section_title": semantic_metadata["section_title"],
                "section_type": semantic_metadata["section_type"],
                "key_terms": semantic_metadata["key_terms"],
                "content_type": content_type,
            }
            page_chunks.append(chunk_data)

        return page_chunks

    def process_document_from_content(self, file_content: bytes, filename: str) -> List[Dict]:
        """Process a document from content bytes, using page-wise chunking with overlap and Pydantic validation."""
        file_extension = Path(filename).suffix.lower()
        chunks = []

        temp_dir = Path("temp_files")
        temp_dir.mkdir(exist_ok=True)
        temp_file = temp_dir / filename
        try:
            with open(temp_file, "wb") as f:
                f.write(file_content)
            
            if file_extension in [".pdf", ".ppt", ".pptx", ".docx", ".doc"]:
                if file_extension == ".pdf":
                    pdf_path = str(temp_file)
                    cleanup_pdf = False
                else:
                    pdf_path = self.convert_to_pdf(file_content, filename)
                    cleanup_pdf = pdf_path != str(temp_file)

                if pdf_path == str(temp_file) and file_extension in [".docx", ".doc"]:
                    logger.info(f"Processing {file_extension} file {filename} directly")
                    chunks = self._process_document_fallback(file_content, filename)
                else:
                    try:
                        pages_data = self._extract_pages_with_positions(pdf_path)
                        if not pages_data:
                            logger.warning(f"No pages extracted from {pdf_path}")
                            return []
                        
                        original_page_text_map = {page['page_number']: page['text'] for page in pages_data}
                        logger.debug(f"Original page text map created with {len(original_page_text_map)} pages")
                        
                        # Use concurrent image processing
                        image_summaries = self.detect_images_in_pdf_concurrent(pdf_path)
                        logger.info(f"Image summaries generated for {len(image_summaries)} pages using concurrent processing")
                        
                        # Create page text map with image summaries
                        page_text_map = original_page_text_map.copy()
                        for page_number, summary in image_summaries.items():
                            if not summary.startswith("Error") and not summary.startswith("Failed"):
                                cleaned_summary = self.clean_text(summary)
                                if cleaned_summary:
                                    page_text_map[page_number] = (
                                        page_text_map.get(page_number, "") + 
                                        "\n\n[Image Summary]\n" + cleaned_summary
                                    )
                        
                        # Process each page with overlap
                        all_chunks = []
                        max_concurrent_pages = int(os.getenv("MAX_CONCURRENT_PROMPTS", 4))
                        with ThreadPoolExecutor(max_workers=max_concurrent_pages) as executor:
                            futures = {
                                executor.submit(
                                    self._process_single_page,
                                    idx, page_data, pages_data, page_text_map, original_page_text_map, filename, file_content
                                ): idx for idx, page_data in enumerate(pages_data)
                            }
                            for future in as_completed(futures):
                                try:
                                    page_chunks = future.result()
                                    all_chunks.extend(page_chunks)
                                except Exception as e:
                                    logger.error(f"Error processing page {futures[future]}: {e}")
                                    continue
                        # Assign chunk_number and validate chunks
                        for i, chunk_data in enumerate(all_chunks):
                            chunk_data["chunk_number"] = i
                            try:
                                validated_chunk = DocumentChunk(**chunk_data)
                                chunks.append(validated_chunk.dict())
                                logger.debug(f"Validated chunk {i} for page {chunk_data['page_numbers']}")
                            except ValueError as e:
                                logger.error(f"Chunk validation failed for chunk {i}: {e}")
                                continue
                        logger.info(f"Processed {filename}: {len(chunks)} chunks created with single-page assignment")
                    
                    except Exception as e:
                        logger.error(f"Error processing PDF {pdf_path}: {e}")
                        if file_extension in [".docx", ".doc"]:
                            logger.info(f"Falling back to direct {file_extension} processing for {filename}")
                            chunks = self._process_document_fallback(file_content, filename)
                        else:
                            return []
                    finally:
                        if cleanup_pdf and os.path.exists(pdf_path):
                            os.remove(pdf_path)
            else:
                logger.warning(f"Unsupported format {file_extension}, using fallback method")
                chunks = self._process_document_fallback(file_content, filename)

        finally:
            if temp_file.exists():
                os.remove(temp_file)
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                os.rmdir(temp_dir)

        # Add page distribution logging
        page_distribution = {}
        for chunk in chunks:
            for page_num in chunk["page_numbers"]:
                page_distribution[page_num] = page_distribution.get(page_num, 0) + 1
        
        logger.info(f"Page distribution for {filename}: {dict(sorted(page_distribution.items()))}")
        
        logger.info(f"Processed {filename}: {len(chunks)} chunks created")
        return chunks

    def _process_document_fallback(self, file_content: bytes, filename: str) -> List[Dict]:
        """Fallback method for unsupported document formats using in-memory content."""
        temp_dir = Path("temp_files")
        temp_dir.mkdir(exist_ok=True)
        temp_file = temp_dir / filename
        try:
            with open(temp_file, "wb") as f:
                f.write(file_content)
            
            docs = self.document_loader.load_document(temp_file)
            if not docs:
                logger.warning(f"No content loaded from {filename}")
                return []

            chunks = []
            all_content = ""
            page_contents = []
            
            for doc_idx, doc in enumerate(docs):
                if not doc.page_content:
                    continue
                
                page_number = self._get_page_number(doc, doc_idx)
                page_contents.append({'page_number': page_number, 'text': doc.page_content})
                all_content += doc.page_content + "\n\n"
            
            page_text_map = {page['page_number']: page['text'] for page in page_contents}
            
            if all_content:
                text_chunks = self.text_splitter.split_text(all_content)
                
                for chunk_idx, chunk_text in enumerate(text_chunks):
                    if len(chunk_text) < self.min_chunk_size:
                        continue

                    cleaned_text = self.clean_text(chunk_text)
                    
                    if not cleaned_text:
                        continue
                    
                    page_numbers = self._find_chunk_page_numbers(cleaned_text, page_contents)
                    
                    original_texts = {
                        page_num: page_text_map.get(page_num, "") for page_num in page_numbers
                    }
                    
                    semantic_metadata = self._extract_semantic_metadata(cleaned_text)

                    chunk_data = {
                        "text": cleaned_text,
                        "filename": filename,
                        "document_name": Path(filename).stem,
                        "page_numbers": page_numbers,
                        "original_texts": original_texts,
                        "chunk_number": chunk_idx,
                        "filepath": filename,
                        "file_hash": hashlib.sha256(file_content).hexdigest(),
                        "chunk_hash": self._hash_text(cleaned_text),
                        "upload_timestamp": datetime.now().isoformat(),
                        "section_title": semantic_metadata["section_title"],
                        "section_type": semantic_metadata["section_type"],
                        "key_terms": semantic_metadata["key_terms"],
                        "content_type": "text",
                    }

                    # Validate chunk using Pydantic
                    try:
                        validated_chunk = DocumentChunk(**chunk_data)
                        chunks.append(validated_chunk.dict())
                    except ValueError as e:
                        logger.error(f"Chunk validation failed for chunk {chunk_idx} in fallback: {e}")
                        continue

            # Add page distribution logging
            page_distribution = {}
            for chunk in chunks:
                for page_num in chunk["page_numbers"]:
                    page_distribution[page_num] = page_distribution.get(page_num, 0) + 1
            
            logger.info(f"Page distribution for {filename} (fallback): {dict(sorted(page_distribution.items()))}")
            
            logger.info(f"Processed {filename} (fallback): {len(chunks)} chunks created")
            return chunks
        finally:
            if temp_file.exists():
                os.remove(temp_file)
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                os.rmdir(temp_dir)

    def generate_prompt_embedding(self, prompt: str) -> List[float]:
        """Generate embedding for a prompt."""
        return self.embeddings.embed_query(self.clean_text(prompt))

    def _extract_semantic_metadata(self, text: str) -> Dict[str, Optional[str]]:
        """Extract semantic metadata from text chunk."""
        metadata = {
            "section_title": None,
            "section_type": None,
            "key_terms": []
        }

        title_patterns = [
            r'^(#+)\s+([^\n]*)',
            r'^\d+\.\s+([^\n]*)',
            r'^\b[A-Z][A-Z\s]+:([^\n]*)',
            r'^\b[A-Z][a-zA-Z\s]+(?:\n\s*[-=]+)?\s*$',
        ]
        
        for pattern in title_patterns:
            title_match = re.search(pattern, text, re.MULTILINE)
            if title_match:
                metadata["section_title"] = title_match.group(1) if title_match.lastindex else title_match.group(0)
                if pattern.startswith(r'^(#+)'):
                    metadata["section_type"] = "heading"
                elif pattern.startswith(r'^\d+\.\s+'):
                    metadata["section_type"] = "numbered"
                elif pattern.startswith(r'^\b[A-Z][A-Z\s]+:'):
                    metadata["section_type"] = "label"
                elif pattern.startswith(r'^\b[A-Z][a-zA-Z\s]+'):
                    metadata["section_type"] = "title_case"
                break

        doc = self.nlp(text)
        key_terms = [
            ent.text for ent in doc.ents
            if ent.label_ in ["ORG", "PERSON", "GPE", "LAW", "PRODUCT"]
            and len(ent.text.split()) <= 3
        ]
        metadata["key_terms"] = list(set(key_terms))[:5]

        return metadata

    @staticmethod
    def _get_page_number(doc: Document, doc_idx: int) -> int:
        """Get page number from document metadata."""
        try:
            page_keys = ["page", "page_number", "source_page", "page_num"]
            for key in page_keys:
                if key in doc.metadata and doc.metadata[key] is not None:
                    return int(doc.metadata[key])
            return doc_idx + 1
        except (ValueError, TypeError):
            return doc_idx + 1

    @staticmethod
    def _hash_file(file_content: bytes) -> str:
        """Calculate SHA256 hash of file content to align with main code."""
        return hashlib.sha256(file_content).hexdigest()

    @staticmethod
    def _hash_text(text: str) -> str:
        """Calculate SHA256 hash of text to align with main code."""
        return hashlib.sha256(text.encode()).hexdigest()

    def __del__(self):
        """Clean up the thread pool executors when the service is destroyed."""
        if hasattr(self, 'image_executor'):
            self.image_executor.shutdown(wait=True)
        if hasattr(self, 'embedding_executor'):
            self.embedding_executor.shutdown(wait=True)