from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime

class MeetingNote(BaseModel):
    title: str
    content: str
    project: Optional[str] = None
    department: Optional[str] = None
    date: datetime = datetime.now()
    participants: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict] = None

class FolderStructure(BaseModel):
    name: str
    parent_id: Optional[str] = None
    description: Optional[str] = None

class NoteResponse(BaseModel):
    note_id: str
    title: str
    folder_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    status: str
    message: Optional[str] = None

class FolderResponse(BaseModel):
    folder_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    status: str
    message: Optional[str] = None
    parent_id: Optional[str] = None
