from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from core.db import db_manager
from core.service import RegistryService
from schemas.registry import AgentManifest, AgentCreate, SkillSchema
from typing import List

app = FastAPI(title="PACC Registry (The Brain)", description="Central Policy Engine for PACC")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "online", "role": "brain"}

# --- Agent Management ---

@app.post("/agents", response_model=None)
async def create_agent(agent: AgentCreate, db: Session = Depends(db_manager.get_db)):
    """Creates a new agent profile in the registry."""
    return RegistryService.create_agent(db, agent)

@app.get("/agents", response_model=List[AgentManifest])
async def list_agents(db: Session = Depends(db_manager.get_db)):
    """Lists all available agents in the registry."""
    return RegistryService.list_agents(db)

@app.get("/agents/{agent_id}", response_model=AgentManifest)
async def get_agent_config(agent_id: str, db: Session = Depends(db_manager.get_db)):
    """Serves the agent manifest to the Gateway."""
    manifest = RegistryService.get_agent_manifest(db, agent_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Agent not found")
    return manifest

# --- Skill Management ---

@app.post("/skills")
async def add_skill(skill: SkillSchema, db: Session = Depends(db_manager.get_db)):
    """Registers a new skill in the manifest."""
    return RegistryService.create_skill(db, skill.skill_id, skill.description, skill.exec_command, skill.args_schema)

@app.get("/skills", response_model=List[SkillSchema])
async def list_skills(db: Session = Depends(db_manager.get_db)):
    """Lists all available skills."""
    from models.database import SkillModel
    skills = db.query(SkillModel).all()
    return [SkillSchema(
        skill_id=s.skill_id,
        description=s.description,
        exec_command=s.exec_command,
        args_schema=s.args_schema or {}
    ) for s in skills]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
