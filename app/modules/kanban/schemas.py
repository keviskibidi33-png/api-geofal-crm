from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class KanbanNoteSchema(BaseModel):
    id: str
    author: str
    authorEmail: Optional[str] = None
    authorRole: Optional[str] = None
    avatar: Optional[str] = None
    content: str
    imageUrl: Optional[str] = None
    createdAt: str


class KanbanCardCreate(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    proyectoNombre: str
    codigoOt: Optional[str] = None
    columnId: str = "todo"
    assignedTo: str = "Laboratorio"
    assignedAvatar: Optional[str] = None
    priority: str = "media"
    dueDate: Optional[str] = None
    imageUrl: Optional[str] = None
    notes: Optional[List[KanbanNoteSchema]] = []
    tracingSummary: Optional[Dict[str, Any]] = None


class KanbanCardUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    proyectoNombre: Optional[str] = None
    codigoOt: Optional[str] = None
    columnId: Optional[str] = None
    assignedTo: Optional[str] = None
    assignedAvatar: Optional[str] = None
    priority: Optional[str] = None
    dueDate: Optional[str] = None
    imageUrl: Optional[str] = None


class KanbanCardMove(BaseModel):
    columnId: str


class KanbanNoteCreate(BaseModel):
    author: str
    authorEmail: Optional[str] = None
    authorRole: Optional[str] = None
    avatar: Optional[str] = None
    content: str
    imageUrl: Optional[str] = None


class KanbanCardResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    proyectoNombre: str
    codigoOt: Optional[str] = None
    columnId: str
    assignedTo: str
    assignedAvatar: Optional[str] = None
    priority: str
    dueDate: Optional[str] = None
    imageUrl: Optional[str] = None
    notes: List[KanbanNoteSchema] = []
    tracingSummary: Optional[Dict[str, Any]] = None
    createdBy: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    class Config:
        from_attributes = True
