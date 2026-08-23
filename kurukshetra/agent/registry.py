"""
Agent Registry & Lifecycle
==========================

Manages the registration, lifecycle, and domain scope of agents:
- Agent registration with capabilities
- Domain-specific knowledge scoping
- Lifecycle management (created → training → active → deprecated)
- Inter-agent communication routing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from kurukshetra.registry.database import get_connection


class AgentStatus(Enum):
    """Agent lifecycle status."""
    CREATED = "created"
    TRAINING = "training"
    ACTIVE = "active"
    PAUSED = "paused"
    DEPRECATED = "deprecated"


class AgentRole(Enum):
    """Roles an agent can play in the swarm."""
    PLANNER = "planner"           # SANJAYA - orchestrator
    SPECIALIST = "specialist"     # Domain-specific worker
    MONITOR = "monitor"           # Observability agent
    LEARNER = "learner"           # SEAL - learning agent
    RETRIEVER = "retriever"       # Knowledge retrieval


@dataclass(slots=True)
class AgentCapability:
    """A specific capability of an agent."""
    name: str
    description: str
    tool_required: Optional[str] = None  # Tool needed (e.g., "datadog", "sql")
    confidence_threshold: float = 0.5


@dataclass(slots=True)
class AgentRegistration:
    """Full registration record for an agent."""
    agent_id: str
    name: str
    description: str
    role: AgentRole
    status: AgentStatus
    domain: str                     # e.g., "spm", "sdops", "installation"
    team_owner: str                 # Organizational team
    capabilities: list[AgentCapability]
    knowledge_scope: list[str]      # Document types this agent can access
    version: str = "1.0.0"
    parent_agent: Optional[str] = None  # SANJAYA for all workers


class AgentRegistry:
    """
    Central registry for all agents in the KURUKSHETRA swarm.

    Stores agent metadata in DuckDB and provides lookup/routing.
    """

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create agent registry table."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_registry (
                agent_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                role TEXT,
                status TEXT,
                domain TEXT,
                team_owner TEXT,
                capabilities TEXT,
                knowledge_scope TEXT,
                version TEXT,
                parent_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.close()

    def register(
        self,
        agent_id: str,
        name: str,
        description: str,
        role: AgentRole = AgentRole.SPECIALIST,
        domain: str = "general",
        team_owner: str = "UNKNOWN",
        capabilities: Optional[list[AgentCapability]] = None,
        knowledge_scope: Optional[list[str]] = None,
        version: str = "1.0.0",
        parent_agent: Optional[str] = None,
    ) -> AgentRegistration:
        """
        Register a new agent in the swarm.

        Returns the full AgentRegistration record.
        """
        import json

        reg = AgentRegistration(
            agent_id=agent_id,
            name=name,
            description=description,
            role=role,
            status=AgentStatus.CREATED,
            domain=domain,
            team_owner=team_owner,
            capabilities=capabilities or [],
            knowledge_scope=knowledge_scope or ["general"],
            version=version,
            parent_agent=parent_agent,
        )

        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO agent_registry
            (agent_id, name, description, role, status, domain, team_owner,
             capabilities, knowledge_scope, version, parent_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                reg.agent_id,
                reg.name,
                reg.description,
                reg.role.value,
                reg.status.value,
                reg.domain,
                reg.team_owner,
                json.dumps([{"name": c.name, "description": c.description,
                           "tool_required": c.tool_required,
                           "confidence_threshold": c.confidence_threshold}
                          for c in reg.capabilities]),
                json.dumps(reg.knowledge_scope),
                reg.version,
                reg.parent_agent,
            ),
        )
        conn.close()

        return reg

    def get(self, agent_id: str) -> Optional[AgentRegistration]:
        """Get an agent registration by ID."""
        import json

        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM agent_registry WHERE agent_id = ?",
            (agent_id,),
        ).fetchone()
        conn.close()

        if row is None:
            return None

        caps_raw = json.loads(row[7]) if row[7] else []
        capabilities = [
            AgentCapability(
                name=c["name"],
                description=c["description"],
                tool_required=c.get("tool_required"),
                confidence_threshold=c.get("confidence_threshold", 0.5),
            )
            for c in caps_raw
        ]

        return AgentRegistration(
            agent_id=row[0],
            name=row[1],
            description=row[2],
            role=AgentRole(row[3]),
            status=AgentStatus(row[4]),
            domain=row[5],
            team_owner=row[6],
            capabilities=capabilities,
            knowledge_scope=json.loads(row[8]) if row[8] else [],
            version=row[9],
            parent_agent=row[10],
        )

    def update_status(self, agent_id: str, status: AgentStatus) -> None:
        """Update an agent's lifecycle status."""
        conn = get_connection()
        conn.execute(
            "UPDATE agent_registry SET status = ? WHERE agent_id = ?",
            (status.value, agent_id),
        )
        conn.close()

    def list_agents(
        self,
        status: Optional[AgentStatus] = None,
        domain: Optional[str] = None,
        role: Optional[AgentRole] = None,
    ) -> list[AgentRegistration]:
        """List agents with optional filters."""
        import json

        conn = get_connection()
        query = "SELECT * FROM agent_registry WHERE 1=1"
        params: list = []

        if status:
            query += " AND status = ?"
            params.append(status.value)
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if role:
            query += " AND role = ?"
            params.append(role.value)

        rows = conn.execute(query, params).fetchall()
        conn.close()

        agents = []
        for row in rows:
            caps_raw = json.loads(row[7]) if row[7] else []
            capabilities = [
                AgentCapability(
                    name=c["name"],
                    description=c["description"],
                    tool_required=c.get("tool_required"),
                    confidence_threshold=c.get("confidence_threshold", 0.5),
                )
                for c in caps_raw
            ]
            agents.append(
                AgentRegistration(
                    agent_id=row[0],
                    name=row[1],
                    description=row[2],
                    role=AgentRole(row[3]),
                    status=AgentStatus(row[4]),
                    domain=row[5],
                    team_owner=row[6],
                    capabilities=capabilities,
                    knowledge_scope=json.loads(row[8]) if row[8] else [],
                    version=row[9],
                    parent_agent=row[10],
                )
            )

        return agents

    def route_query(self, query: str) -> Optional[AgentRegistration]:
        """
        Route a query to the best-matching active agent.

        Matches query against agent domains and capabilities.
        """
        active_agents = self.list_agents(status=AgentStatus.ACTIVE)

        if not active_agents:
            return None

        query_lower = query.lower()
        best_match: Optional[AgentRegistration] = None
        best_score = 0.0

        for agent in active_agents:
            score = 0.0

            # Domain match
            if agent.domain.lower() in query_lower:
                score += 0.5

            # Capability keyword match
            for cap in agent.capabilities:
                cap_words = set(cap.name.lower().split())
                query_words = set(query_lower.split())
                overlap = len(cap_words & query_words)
                if overlap:
                    score += 0.3 * (overlap / len(cap_words))

            if score > best_score:
                best_score = score
                best_match = agent

        return best_match if best_score > 0.3 else None
