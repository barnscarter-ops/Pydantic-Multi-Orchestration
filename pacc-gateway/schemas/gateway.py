from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class GatewayRequest(BaseModel):
    """Unified request schema for the PACC Model Gateway."""
    prompt: str
    agent_id: str  # Now the primary key for the Registry handshake
    max_tokens: Optional[int] = 1024
    temperature: float = 0.7
    stream: bool = False
    force_escalate: bool = False
    context: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class GatewayResponse(BaseModel):
    """Unified response schema for the PACC Model Gateway."""
    content: str
    model_used: str
    provider: str  # 'ollama', 'anthropic', 'openai', 'google'
    latency_ms: float
    tokens_used: Optional[int] = None
    confidence_score: Optional[float] = None
    escalated: bool = False
    error: Optional[str] = None

class AgentParams(BaseModel):
    """Model parameters supplied by the Registry manifest."""
    temperature: float = 0.7
    max_tokens: int = 1024
    context_window: int = 4096
    top_p: float = 1.0

class AgentManifest(BaseModel):
    """Agent policy returned by the Registry during the handshake."""
    agent_id: str
    name: str
    system_prompt: str
    primary_model: str
    fallback_model: str
    authorized_skills: List[str] = Field(default_factory=list)
    params: AgentParams = Field(default_factory=AgentParams)

class FileSaveRequest(BaseModel):
    """Schema for file save request payload."""
    path: str
    content: str
