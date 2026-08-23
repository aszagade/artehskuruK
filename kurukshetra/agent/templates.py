"""
Domain-Specific Agent Templates
================================

Pre-configured agent templates for different teams and domains.
Each template includes domain-specific capabilities, knowledge scope,
and retrieval strategies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .registry import AgentCapability, AgentRole, AgentStatus


@dataclass(slots=True)
class AgentTemplate:
    """A pre-configured agent template for a specific domain."""
    template_id: str
    name: str
    description: str
    domain: str
    team_owner: str
    role: AgentRole
    capabilities: list[AgentCapability]
    knowledge_scope: list[str]
    retrieval_strategies: list[str]  # Which retrieval strategies to prioritize
    system_prompt_addendum: str      # Additional system prompt for this domain


# -----------------------------------------------------------------------
# Pre-built templates
# -----------------------------------------------------------------------

SPM_AGENT = AgentTemplate(
    template_id="spm-agent",
    name="SPM Knowledge Agent",
    description="Handles G3 RMS process queries, troubleshooting, and SPM team workflows",
    domain="spm",
    team_owner="Service Delivery",
    role=AgentRole.SPECIALIST,
    capabilities=[
        AgentCapability(
            name="G3 RMS Troubleshooting",
            description="Diagnose and resolve G3 RMS processing failures",
            tool_required=None,
            confidence_threshold=0.6,
        ),
        AgentCapability(
            name="Property Management",
            description="Property installation, migration, and configuration",
            tool_required=None,
            confidence_threshold=0.6,
        ),
        AgentCapability(
            name="Decision Upload Investigation",
            description="Investigate decision upload failures and data flow issues",
            tool_required=None,
            confidence_threshold=0.6,
        ),
    ],
    knowledge_scope=[
        "Process Guide", "Troubleshooting", "Configuration",
        "Error Resolution", "Monitoring",
    ],
    retrieval_strategies=["hybrid", "parent_child", "cross_verified"],
    system_prompt_addendum=(
        "You are an SPM specialist for IDeaS G3 RMS. "
        "Focus on operational procedures, troubleshooting, and property management. "
        "Always reference specific G3 job steps and configuration parameters."
    ),
)

SDOPS_AGENT = AgentTemplate(
    template_id="sdops-agent",
    name="SDOPS Operations Agent",
    description="Handles deployment monitoring, operational health, and incident response",
    domain="sdops",
    team_owner="SDOPS",
    role=AgentRole.SPECIALIST,
    capabilities=[
        AgentCapability(
            name="Deployment Monitoring",
            description="Track and investigate deployment issues",
            tool_required="datadog",
            confidence_threshold=0.7,
        ),
        AgentCapability(
            name="Incident Response",
            description="Guide incident investigation and resolution",
            tool_required="datadog",
            confidence_threshold=0.7,
        ),
    ],
    knowledge_scope=[
        "Monitoring", "Configuration", "Best Practice",
    ],
    retrieval_strategies=["hybrid", "multi_query"],
    system_prompt_addendum=(
        "You are an SDOPS specialist. Focus on operational health, "
        "deployment monitoring, and incident response procedures."
    ),
)

ICS_AGENT = AgentTemplate(
    template_id="ics-agent",
    name="ICS Integration Agent",
    description="Handles integration support, migration management, and system connectivity",
    domain="ics",
    team_owner="Support",
    role=AgentRole.SPECIALIST,
    capabilities=[
        AgentCapability(
            name="Integration Troubleshooting",
            description="Diagnose integration connectivity and data flow issues",
            tool_required=None,
            confidence_threshold=0.6,
        ),
        AgentCapability(
            name="Migration Support",
            description="Guide PMS and agent migration processes",
            tool_required=None,
            confidence_threshold=0.6,
        ),
    ],
    knowledge_scope=[
        "Installation", "Migration", "Configuration", "Troubleshooting",
    ],
    retrieval_strategies=["hybrid", "hyde", "cross_verified"],
    system_prompt_addendum=(
        "You are an ICS integration specialist. Focus on system connectivity, "
        "data flow, migration processes, and integration troubleshooting."
    ),
)

# Template registry
AGENT_TEMPLATES: dict[str, AgentTemplate] = {
    "spm": SPM_AGENT,
    "sdops": SDOPS_AGENT,
    "ics": ICS_AGENT,
}


def get_template(domain: str) -> Optional[AgentTemplate]:
    """Get an agent template by domain."""
    return AGENT_TEMPLATES.get(domain.lower())


def list_templates() -> list[AgentTemplate]:
    """List all available agent templates."""
    return list(AGENT_TEMPLATES.values())


def create_agent_from_template(
    template: AgentTemplate,
    agent_id: str,
    version: str = "1.0.0",
    parent_agent: str = "SANJAYA",
) -> dict:
    """
    Create agent registration data from a template.

    Returns a dict suitable for AgentRegistry.register().
    """
    return {
        "agent_id": agent_id,
        "name": template.name,
        "description": template.description,
        "role": template.role,
        "domain": template.domain,
        "team_owner": template.team_owner,
        "capabilities": template.capabilities,
        "knowledge_scope": template.knowledge_scope,
        "version": version,
        "parent_agent": parent_agent,
    }
