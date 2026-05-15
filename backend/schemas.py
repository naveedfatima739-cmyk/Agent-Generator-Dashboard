from pydantic import BaseModel
from typing import Optional

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None

class TrainRequest(BaseModel):
    url: str
    prompt: str
    description: Optional[str] = None

class AgentUpdate(AgentCreate):
    pass