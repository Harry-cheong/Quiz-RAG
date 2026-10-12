from fastapi import APIRouter, File, HTTPException, UploadFile, Depends

from pathlib import Path
from pydantic import BaseModel
from uuid import uuid4, UUID
from shutil import copyfileobj

from rag.graph import rag_workflow
from rag.ingest import ingest_pdf
from rag.retrieve import get_retriever
from rag.config import Config

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data"

class RAGRequest(BaseModel):
    question: str

def get_vectorstore():
    return Config.get_chroma()

@router.post("/question")
def rag_answer(answer: RAGRequest):
    response = rag_workflow().invoke({"question": answer.question})
    return {"response": response}

@router.post("/documents")
def ingest(file: UploadFile = File(...)):
    # Only accepts PDF
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Please upload a PDF")

    document_id = uuid4().hex
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{document_id}.pdf"

    with saved_path.open("wb") as destination:
        copyfileobj(file.file, destination)

    chunk_count = ingest_pdf(str(saved_path), document_id=document_id)
    get_retriever.cache_clear()

    return {
        "document_id": document_id,
        "filename": file.filename,
        "chunks_added": chunk_count,
    }

@router.get("/document_ids")
def get_ids(db=Depends(get_vectorstore)):
    data = db.get(include=["metadatas"])

    sources = sorted({
        metadata["document_id"] for metadata in data["metadatas"] if metadata and metadata.get("document_id")
    })

    return {"ids": sources}


@router.delete("/documents/{document_id}")
def delete_document(document_id: UUID, db=Depends(get_vectorstore)):

    document_key = document_id.hex
    pdf_path = UPLOAD_DIR / f"{document_key}.pdf"

    where = {"document_id": document_key}

    matches = db.get(where=where, include=["metadatas"])

    chunk_count = len(matches["ids"])

    if chunk_count == 0 and not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found")

    if chunk_count:
        db.delete(where=where)
        get_retriever.cache_clear()

    file_deleted = pdf_path.is_file()

    if file_deleted:
        try:
            pdf_path.unlink()
        except OSError:
            raise HTTPException(status_code=500, detail="Chunks were deleted, but the uploaded PDF could not be removed")

    return {"status": "ok"}
