import os
import json
import re
import time
import asyncio
import multiprocessing
import requests
from pathlib import Path
from dotenv import load_dotenv
from markdownify import markdownify as md
# from pyhtml2pdf import converter
# from docling.document_converter import DocumentConverter, PdfFormatOption
# from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions
# from docling.datamodel.base_models import InputFormat
# from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken
from openai import AsyncOpenAI
from json_repair import repair_json
# import torch

load_dotenv()

# SEC requires proper User-Agent
SEC_HEADERS = {"User-Agent": "YourCompany your-email@example.com"}

OPENAI_MODEL = "gpt-5-nano"

# Base output directory
OUTPUT_DIR = Path("sec_documents")


def get_file_prefix(company_name: str, symbol: str, cik: str) -> str:
    """Generate file prefix: companyname_symbol_fullcik (sanitized for filesystem)."""
    # Sanitize company name: remove special chars, replace spaces with underscores
    safe_name = re.sub(r'[^\w\s-]', '', company_name).strip().replace(' ', '_')
    # Ensure CIK is padded to 10 digits
    full_cik = cik.lstrip("0").zfill(10)
    return f"{safe_name}_{symbol}_{full_cik}"

# # Detect GPU availability
# if torch.cuda.is_available():
#     DEVICE = "cuda"
# elif torch.backends.mps.is_available():
#     DEVICE = "mps"
# else:
#     DEVICE = "cpu"

# print(f"Using device: {DEVICE}")

# # Initialize DocumentConverter once with GPU acceleration (reuse across all files)
# _doc_converter = None


# def get_doc_converter():
#     """Get or create a reusable DocumentConverter with optimized settings."""
#     global _doc_converter
#     if _doc_converter is None:
#         num_threads = multiprocessing.cpu_count()
#         print(f"Initializing Docling with {DEVICE} acceleration ({num_threads} threads)...")
        
#         accelerator_options = AcceleratorOptions(
#             num_threads=num_threads,
#             device=DEVICE,
#         )
        
#         pipeline_options = PdfPipelineOptions(
#             accelerator_options=accelerator_options,
#             do_ocr=False,  # Disable OCR for text-based PDFs (faster)
#             do_table_structure=True,
#             # Performance optimizations
#             images_scale=1.0,  # Lower scale = faster processing
#             generate_page_images=False,  # Disable page image generation
#             generate_picture_images=False,  # Disable picture extraction
#         )
        
#         _doc_converter = DocumentConverter(
#             format_options={
#                 InputFormat.PDF: PdfFormatOption(
#                     pipeline_options=pipeline_options,
#                     backend=PyPdfiumDocumentBackend,  # Faster PDF backend
#                 )
#             }
#         )
#     return _doc_converter


def setup_directories():
    """Create the directory structure for output files."""
    subdirs = ["html", "pdf", "md", "chunks", "clean_chunks"]
    for subdir in subdirs:
        (OUTPUT_DIR / subdir).mkdir(parents=True, exist_ok=True)


def get_10k_url(cik: str):
    """Get the URL for the latest 10-K filing from SEC EDGAR."""
    # Normalize CIK to 10 digits with leading zeros
    cik_padded = cik.lstrip("0").zfill(10)
    
    print(f"Finding latest 10-K for CIK {cik}...")
    
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    response = requests.get(url, headers=SEC_HEADERS)
    response.raise_for_status()
    data = response.json()
    
    filings = data["filings"]["recent"]
    for i, form in enumerate(filings["form"]):
        if form == "10-K":
            accession = filings["accessionNumber"][i].replace("-", "")
            primary_doc = filings["primaryDocument"][i]
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_padded}/{accession}/{primary_doc}"
            return filing_url
    
    raise FileNotFoundError(f"No 10-K filing found for CIK {cik}")


def download_html(url: str, file_prefix: str):
    """Download HTML from SEC with proper headers."""
    output_path = OUTPUT_DIR / "html" / f"{file_prefix}_10k.html"
    
    print(f"Downloading HTML...")
    response = requests.get(url, headers=SEC_HEADERS)
    response.raise_for_status()
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(response.text)
    
    print(f"Saved: {output_path}")
    return output_path


def convert_html_to_markdown(html_path: Path, file_prefix: str):
    """Convert HTML directly to Markdown using markdownify."""
    output_path = OUTPUT_DIR / "md" / f"{file_prefix}_10k.md"
    
    print(f"Converting HTML to Markdown...")
    
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    markdown = md(html_content, heading_style="ATX", strip=['script', 'style'])
    
    # Clean excessive whitespace: collapse 3+ newlines to 2, strip lines
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    markdown = '\n'.join(line.rstrip() for line in markdown.splitlines())
    markdown = markdown.strip()
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    
    print(f"Saved: {output_path}")
    return output_path


# def convert_html_to_pdf(html_path: Path, cik: str):
#     """Convert local HTML file to PDF using pyhtml2pdf."""
#     output_path = OUTPUT_DIR / "pdf" / f"{cik}_10k.pdf"
    
#     print(f"Converting to PDF...")
#     file_url = f"file:///{os.path.abspath(html_path)}"
#     converter.convert(file_url, str(output_path), timeout=10)
#     print(f"Saved: {output_path}")
#     return output_path


# def convert_pdf_to_markdown(pdf_path: Path, cik: str):
#     """Convert PDF to Markdown using Docling with GPU acceleration."""
#     output_path = OUTPUT_DIR / "md" / f"{cik}_10k.md"
    
#     print(f"Converting PDF to Markdown (using {DEVICE})...")
    
#     doc_converter = get_doc_converter()
#     result = doc_converter.convert(str(pdf_path))
    
#     markdown = result.document.export_to_markdown()
    
#     with open(output_path, "w", encoding="utf-8") as f:
#         f.write(markdown)
    
#     print(f"Saved: {output_path}")
#     return output_path


def chunk_markdown(md_path: Path, file_prefix: str):
    """Chunk markdown into JSON array using recursive text splitter with tiktoken."""
    output_path = OUTPUT_DIR / "chunks" / f"{file_prefix}_10k_chunks.json"
    
    print(f"Chunking markdown...")
    
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    tokenizer = tiktoken.get_encoding("cl100k_base")
    
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=5000,
        chunk_overlap=500,
    )
    
    chunks = splitter.split_text(text)
    
    chunks_json = [
        {"id": i, "text": chunk, "tokens": len(tokenizer.encode(chunk))}
        for i, chunk in enumerate(chunks)
    ]
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks_json, f, indent=2, ensure_ascii=False)
    
    print(f"Saved: {output_path} ({len(chunks_json)} chunks)")
    return output_path




async def process_single_chunk(client: AsyncOpenAI, instructions: str, chunk: dict, total_chunks: int):
    """Process a single chunk with OpenAI asynchronously."""
    chunk_id = chunk["id"]
    chunk_text = chunk["text"]
    
    try:
        completion = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": chunk_text}
            ]
        )
        response_text = completion.choices[0].message.content.strip()
        
        # Remove markdown code fences if present
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
        if response_text.endswith("```"):
            response_text = response_text.rsplit("```", 1)[0]
        response_text = response_text.strip()
        
        # Repair and parse JSON
        parsed = json.loads(repair_json(response_text))
        
        # Handle response - expecting {"info": "...", "data": {...}}
        if isinstance(parsed, dict):
            info = parsed.get("info", "").strip().lower()
            data = parsed.get("data", {})
            # Skip empty or useless responses
            is_useless_info = info == "" or "no relevant" in info or "not found" in info
            if is_useless_info and data == {}:
                print(f"  Chunk {chunk_id + 1}/{total_chunks}: Skipped (empty response)")
                return None
            else:
                parsed["chunk_id"] = chunk_id
                print(f"  Chunk {chunk_id + 1}/{total_chunks}: Added 1 item")
                return parsed
        elif isinstance(parsed, list):
            for item in parsed:
                item["chunk_id"] = chunk_id
            print(f"  Chunk {chunk_id + 1}/{total_chunks}: Added {len(parsed)} items")
            return parsed
        else:
            print(f"  Chunk {chunk_id + 1}/{total_chunks}: Warning: Unexpected response type: {type(parsed)}")
            return None
            
    except json.JSONDecodeError as e:
        print(f"  Chunk {chunk_id + 1}/{total_chunks}: Warning: Failed to parse JSON: {e}")
        return None
    except Exception as e:
        print(f"  Chunk {chunk_id + 1}/{total_chunks}: Error: {e}")
        return None


async def clean_chunks_with_groq_async(chunks_path: Path, file_prefix: str, batch_size: int = 10):
    """Process chunks through OpenAI to extract structured JSON (async with batching)."""
    output_path = OUTPUT_DIR / "clean_chunks" / f"{file_prefix}_10k_clean.json"
    
    print(f"Cleaning chunks with OpenAI ({OPENAI_MODEL}) - batch size {batch_size}...")
    
    # Load instructions prompt
    with open("prompt_extract.md", "r", encoding="utf-8") as f:
        instructions = f.read()
    
    # Load chunks
    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    
    # Initialize async OpenAI client
    client = AsyncOpenAI()
    
    all_cleaned = []
    total_chunks = len(chunks)
    
    # Process in batches of batch_size
    for i in range(0, total_chunks, batch_size):
        batch = chunks[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_chunks + batch_size - 1) // batch_size
        
        print(f"\nProcessing batch {batch_num}/{total_batches} (chunks {i + 1}-{min(i + batch_size, total_chunks)})...")
        
        # Create tasks for all chunks in this batch
        tasks = [
            process_single_chunk(client, instructions, chunk, total_chunks)
            for chunk in batch
        ]
        
        # Wait for all tasks in this batch to complete
        results = await asyncio.gather(*tasks)
        
        # Collect results
        for result in results:
            if result is not None:
                if isinstance(result, list):
                    all_cleaned.extend(result)
                else:
                    all_cleaned.append(result)
        
        # Small delay between batches for rate limiting
        if i + batch_size < total_chunks:
            await asyncio.sleep(0.5)
    
    # Save merged clean chunks
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_cleaned, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved: {output_path} ({len(all_cleaned)} items)")
    return output_path


def clean_chunks_with_groq(chunks_path: Path, file_prefix: str):
    """Wrapper to run async clean_chunks_with_openai."""
    return asyncio.run(clean_chunks_with_groq_async(chunks_path, file_prefix, batch_size=5))


def process_10k(company_name: str, symbol: str, cik: str):
    """Process a 10-K filing for a given company."""
    file_prefix = get_file_prefix(company_name, symbol, cik)
    
    print(f"\n{'='*60}")
    print(f"Processing 10-K for: {company_name} ({symbol})")
    print(f"CIK: {cik} | File prefix: {file_prefix}")
    print(f"{'='*60}\n")
    
    # Setup directory structure
    setup_directories()
    
    # Step 1: Get SEC filing URL
    url = get_10k_url(cik)
    print(f"Found 10-K URL: {url}")
    
    # Step 2: Download HTML with proper headers
    html_path = download_html(url, file_prefix)
    
    # Step 3: Convert HTML directly to Markdown (temporary - skipping PDF/docling)
    md_path = convert_html_to_markdown(html_path, file_prefix)
    
    # # Step 3: Convert local HTML to PDF
    # pdf_path = convert_html_to_pdf(html_path, file_prefix)
    
    # # Step 4: Convert PDF to Markdown using Docling
    # md_path = convert_pdf_to_markdown(pdf_path, file_prefix)
    
    # Step 4: Chunk markdown and save to JSON
    chunks_path = chunk_markdown(md_path, file_prefix)
    
    # Step 5: Clean chunks with Groq (async with batch size 10)
    clean_chunks_with_groq(chunks_path, file_prefix)
    
    print(f"\nDone processing {company_name} ({symbol})!")


def main():
    # Example: Process Apple's 10-K
    process_10k("Apple Inc.", "AAPL", "0000320193")


if __name__ == "__main__":
    main()
