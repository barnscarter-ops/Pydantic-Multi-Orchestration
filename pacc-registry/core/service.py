from sqlalchemy.orm import Session
from models.database import AgentModel, SkillModel
from schemas.registry import AgentManifest, AgentParams, AgentCreate
from typing import List, Optional

class RegistryService:
    """Business logic for managing agents and skills."""

    @staticmethod
    def create_agent(db: Session, agent_data: AgentCreate):
        # Generate a simple ID based on name
        agent_id = agent_data.name.lower().replace(" ", "_")

        new_agent = db.query(AgentModel).filter(AgentModel.agent_id == agent_id).first()
        if new_agent:
            new_agent.name = agent_data.name
            new_agent.system_prompt = agent_data.system_prompt
            new_agent.primary_model = agent_data.primary_model
            new_agent.fallback_model = agent_data.fallback_model
            new_agent.params = agent_data.params
        else:
            new_agent = AgentModel(
                agent_id=agent_id,
                name=agent_data.name,
                system_prompt=agent_data.system_prompt,
                primary_model=agent_data.primary_model,
                fallback_model=agent_data.fallback_model,
                params=agent_data.params
            )
            db.add(new_agent)

        # Link skills
        if agent_data.skill_ids:
            skills = db.query(SkillModel).filter(SkillModel.skill_id.in_(agent_data.skill_ids)).all()
            new_agent.skills = skills
        else:
            new_agent.skills = []

        db.commit()
        db.refresh(new_agent)
        return new_agent

    @staticmethod
    def get_agent_manifest(db: Session, agent_id: str) -> Optional[AgentManifest]:
        agent = db.query(AgentModel).filter(AgentModel.agent_id == agent_id).first()
        if not agent:
            return None

        return AgentManifest(
            agent_id=agent.agent_id,
            name=agent.name,
            system_prompt=agent.system_prompt,
            primary_model=agent.primary_model,
            fallback_model=agent.fallback_model,
            authorized_skills=[s.skill_id for s in agent.skills],
            params=AgentParams(**(agent.params or {}))
        )

    @staticmethod
    def list_agents(db: Session) -> List[AgentManifest]:
        agents = db.query(AgentModel).all()
        return [
            AgentManifest(
                agent_id=agent.agent_id,
                name=agent.name,
                system_prompt=agent.system_prompt,
                primary_model=agent.primary_model,
                fallback_model=agent.fallback_model,
                authorized_skills=[s.skill_id for s in agent.skills],
                params=AgentParams(**(agent.params or {}))
            )
            for agent in agents
        ]

    @staticmethod
    def create_skill(db: Session, skill_id: str, description: str, exec_command: str, args_schema: dict):
        skill = SkillModel(
            skill_id=skill_id,
            description=description,
            exec_command=exec_command,
            args_schema=args_schema
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)
        return skill
