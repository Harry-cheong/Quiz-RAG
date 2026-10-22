import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from pathlib import Path
from pydantic import BaseModel, Field
from uuid import uuid4, UUID
from shutil import copyfileobj
from typing import List

from rag.graph import rag_workflow
from rag.ingest import ingest_pdf
from rag.config import Config

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data"
FOLDERS_PATH = UPLOAD_DIR / "folders.json"

class RAGRequest(BaseModel):
    question: str
    folder_ids: List[UUID] = Field(default_factory=list)
    document_ids: List[UUID] = Field(default_factory=list)

class FolderRequest(BaseModel):
    name: str

class Metadata(BaseModel):
    folder_id: UUID
    description: str | None = None


def get_vectorstore():
    return Config.get_chroma()

def _read_folders():
    if not FOLDERS_PATH.exists():
        return []
    try:
        return json.loads(FOLDERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Could not read folder registry")

def _write_folders(folders):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    FOLDERS_PATH.write_text(json.dumps(folders, indent=2), encoding="utf-8")

def _clean_folder_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Folder name cannot be empty")
    if len(cleaned) > 80:
        raise HTTPException(status_code=400, detail="Folder name must be 80 characters or fewer")
    return cleaned

def _folder_or_404(folder_id: str, folders=None):
    for folder in folders if folders is not None else _read_folders():
        if folder["id"] == folder_id:
            return folder
    raise HTTPException(status_code=404, detail="Folder not found")

@router.post("/question")
def rag_answer(answer: RAGRequest):
    response = rag_workflow().invoke(
        {
            "question": answer.question,
            "document_ids": answer.document_ids,
            "folder_ids": answer.folder_ids,
        }
    )
    return {"response": response}

@router.get("/folders")
def list_folders():
    return {"folders": _read_folders()}

@router.post("/folders", status_code=201)
def create_folder(folder: FolderRequest):
    name = _clean_folder_name(folder.name)
    folders = _read_folders()
    if any(item["name"].casefold() == name.casefold() for item in folders):
        raise HTTPException(status_code=409, detail="A folder with that name already exists")

    created = {"id": str(uuid4()), "name": name}
    folders.append(created)
    _write_folders(folders)
    return created

@router.patch("/folders/{folder_id}")
def rename_folder(folder_id: UUID, request: FolderRequest):
    name = _clean_folder_name(request.name)
    folders = _read_folders()
    folder = _folder_or_404(str(folder_id), folders)
    if any(
        item["id"] != folder["id"] and item["name"].casefold() == name.casefold()
        for item in folders
    ):
        raise HTTPException(status_code=409, detail="A folder with that name already exists")

    folder["name"] = name
    _write_folders(folders)
    return folder

@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: UUID, db=Depends(get_vectorstore)):
    folder_id_str = str(folder_id)
    folders = _read_folders()
    remove = _folder_or_404(folder_id_str, folders)

    # Delete the chunks
    results = db.get(
        where={
            "$or": [
                {"folder_id": folder_id_str},
                {"folder_id": folder_id.hex},
            ]
        },
        include=["metadatas"],
    )

    deleted_ids = results["ids"]
    document_ids = {
        item["document_id"]
        for item in (results.get("metadatas") or [])
        if item and item.get("document_id")
    }

    if deleted_ids:
        db.delete(ids=deleted_ids)

    # Delete the document
    for document_id in document_ids:
        pdf_path = UPLOAD_DIR / f"{document_id}.pdf"
        pdf_path.unlink(missing_ok=True)

    folders.remove(remove)
    _write_folders(folders)

    return {
        "status": "ok",
        "deleted": deleted_ids,
        "deleted_count": len(deleted_ids),
        "deleted_documents": sorted(document_ids),
    }

@router.post("/documents")
def ingest(file: UploadFile = File(...), metadata: str = Form(...)):
    # Only accepts PDF
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Please upload a PDF")

    details = Metadata.model_validate_json(metadata)
    folder_id = str(details.folder_id)
    _folder_or_404(folder_id)

    document_id = uuid4().hex
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{document_id}.pdf"

    try:
        with saved_path.open("wb") as destination:
            copyfileobj(file.file, destination)

        chunk_count = ingest_pdf(
            str(saved_path),
            document_id=document_id,
            folder_id=folder_id,
            filename=file.filename,
        )
    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Document ingestion failed: {exc}") from exc

    return {
        "document_id": document_id,
        "filename": file.filename,
        "folder_id": folder_id,
        "description": details.description,
        "chunks_added": chunk_count,
    }

@router.get("/folders/{folder_id}/documents")
def list_folder_documents(folder_id: UUID, db=Depends(get_vectorstore)):
    _folder_or_404(str(folder_id))
    data = db.get(where={"folder_id": str(folder_id)}, include=["metadatas"])

    documents = {}
    for metadata in data.get("metadatas") or []:
        if not metadata:
            continue
        document_id = metadata.get("document_id")
        if not document_id:
            continue
        document = documents.setdefault(
            document_id,
            {
                "document_id": document_id,
                "filename": metadata.get("filename") or document_id,
                "chunks": 0,
            },
        )
        document["chunks"] += 1

    return {"documents": sorted(documents.values(), key=lambda item: item["filename"].casefold())}

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

    file_deleted = pdf_path.is_file()

    if file_deleted:
        try:
            pdf_path.unlink()
        except OSError:
            raise HTTPException(status_code=500, detail="Chunks were deleted, but the uploaded PDF could not be removed")

    return {"status": "ok"}
