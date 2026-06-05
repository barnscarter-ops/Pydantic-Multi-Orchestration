from sqlalchemy import Column, String, Text, Float, Integer, JSON, Table, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

# Association table for Agent <-> Skill (Many-to-Many)
agent_skills = Table(
    "agent_skills",
    Base.metadata,
    Column("agent_id", String, ForeignKey("agents.agent_id"), primary_key=True),
    Column("skill_id", String, ForeignKey("skills.skill_id"), primary_key=True),
)

class AgentModel(Base):
    """SQLAlchemy model for the Agent Registry."""
    __tablename__ = "agents"

    agent_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=False)
    primary_model = Column(String, nullable=False)
    fallback_model = Column(String, nullable=False)
    params = Column(JSON, nullable=True) # Stores temperature, max_tokens, etc.

    skills = relationship("SkillModel", secondary=agent_skills, back_populates="agents")

class SkillModel(Base):
    """SQLAlchemy model for the Skill Manifest."""
    __tablename__ = "skills"

    skill_id = Column(String, primary_key=True, index=True)
    description = Column(Text, nullable=False)
    exec_command = Column(String, nullable=False)
    args_schema = Column(JSON, nullable=True)

    agents = relationship("AgentModel", secondary=agent_skills, back_populates="skills")
