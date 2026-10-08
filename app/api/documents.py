from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.adapters.logger.logger import logger
from app.core.config import settings

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{doc_name}")
async def get_document(doc_name: str):
    """Send a PDF from the docs folder: Public"""
    # Only PDFs that really exist in the docs folder can be opened.
    available = {path.name: path for path in settings.PDF_DIR.glob("*.pdf")}

    path = available.get(doc_name)
    if path is None:
        logger.warning(f"Document not found: {doc_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )