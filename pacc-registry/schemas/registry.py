from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class SkillSchema(BaseModel):
    """Schema for skill definition."""
    skill_id: str
    description: str
    exec_command: str
    args_schema: Dict[str, Any] = Field(default_factory=dict)

class AgentParams(BaseModel):
    """Model parameters for the agent."""
    temperature: float = 0.7
    max_tokens: int = 1024
    context_window: int = 4096
    top_p: float = 1.0

class AgentManifest(BaseModel):
    """The complete policy for an agent."""
    agent_id: str
    name: str
    system_prompt: str
    primary_model: str
    fallback_model: str
    authorized_skills: List[str] = Field(default_factory=list)
    params: AgentParams = Field(default_factory=AgentParams)

class AgentCreate(BaseModel):
    """Schema for creating a new agent."""
    name: str
    system_prompt: str
    primary_model: str
    fallback_model: str
    skill_ids: List[str] = Field(default_factory=list)
    params: Optional[Dict[str, Any]] = None
