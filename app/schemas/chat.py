from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

QUESTION_MAX_LENGTH = 2000

class Citation(BaseModel):
    doc_name: str
    pdf_page: int
    report_year: str
    chunk_type: str
    url: str

class AskRequest(BaseModel):
    # Spaces at the start and end are removed before the length check
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=QUESTION_MAX_LENGTH)

class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime

class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    citations: list[Citation] | None = None
    created_at: datetime

class ChatDetailResponse(BaseModel):
    chat: ChatResponse
    messages: list[MessageResponse]