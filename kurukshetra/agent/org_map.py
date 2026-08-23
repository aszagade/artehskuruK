"""
Organizational Map (OrgMap)
===========================

Defines the full organizational hierarchy:
  Organization → Teams → Sub-teams → Agents

Each team has:
- Domain expertise keywords
- Product scope
- Sub-teams with specific competencies
- Agent templates for knowledge workers
- Cross-team relationship mapping

This is the backbone for:
- Auto-classifying documents to teams
- Routing queries to the right team's agent
- Detecting cross-team knowledge overlap
- Building the agent swarm hierarchy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TeamType(Enum):
    """Types of teams in the organization."""
    CORE = "core"           # Core operational team
    SUPPORT = "support"     # Support/shared services
    LEARNING = "learning"   # Training and development
    GOVERNANCE = "governance"  # Compliance and governance


@dataclass(slots=True)
class SubTeam:
    """A sub-team within a team."""
    sub_team_id: str
    name: str
    competencies: list[str]    # Specific skills/topics
    keywords: list[str]        # For document classification
    agent_focus: str           # What the sub-team's agent focuses on


@dataclass(slots=True)
class TeamDefinition:
    """Full definition of a team in the organization."""
    team_id: str
    name: str
    full_name: str
    team_type: TeamType
    description: str

    # Classification signals
    keywords: list[str]             # Primary keywords for doc matching
    product_scope: list[str]        # Products this team handles
    document_patterns: list[str]    # Filename patterns (e.g., "G3_*", "HLTN_*")
    content_signals: list[str]      # Content phrases that indicate this team

    # Hierarchy
    sub_teams: list[SubTeam] = field(default_factory=list)

    # Cross-team relationships
    related_teams: list[str] = field(default_factory=list)  # team_ids
    shared_documents: list[str] = field(default_factory=list)  # doc patterns shared

    # Agent configuration
    agent_capabilities: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)


# =========================================================================
# ORGANIZATIONAL HIERARCHY
# =========================================================================

ORG_STRUCTURE = {
    # ------------------------------------------------------------------
    # SPM — Service Performance Management
    # ------------------------------------------------------------------
    "spm": TeamDefinition(
        team_id="spm",
        name="SPM",
        full_name="Service Performance Management",
        team_type=TeamType.CORE,
        description="G3 RMS operations, property management, decision uploads, monitoring, troubleshooting",
        keywords=[
            "spm", "service performance", "g3 rms", "g3-rms", "decision upload",
            "full upload", "first decision", "catchup", "property configuration",
            "rms monitoring", "monitor by exception", "g3 installation",
            "g3 property", "g3 job", "g3 monitoring", "g3 data feed",
            "g3 rollback", "g3 migration", "g3 deinstall",
        ],
        product_scope=["G3 RMS", "Opera Agent", "OHIP", "FOLS"],
        document_patterns=[
            "G3_*", "G3RMS_*", "HLTN_*", "Hilton_*", "FOLS_*",
            "ESA_*", "Decision*", "Component*", "Room*",
            "Benefit Measurement*", "Demand 360*",
        ],
        content_signals=[
            "decision upload", "full upload", "first decision", "catchup",
            "property installation", "monitor by exception", "job failure",
            "optimization step", "forecasting", "rate shopping",
            "pull extract", "data feed", "rollback", "property rebuild",
            "continuous pricing", "bar upload", "restriction level",
        ],
        sub_teams=[
            SubTeam(
                sub_team_id="spm-installation",
                name="Installation",
                competencies=["property installation", "new property setup", "FOLS", "HTNG", "Opera Agent"],
                keywords=["install", "add property", "new property", "setup", "fols", "htng", "opera agent"],
                agent_focus="Property installation and onboarding procedures",
            ),
            SubTeam(
                sub_team_id="spm-monitoring",
                name="Monitoring",
                competencies=["job monitoring", "alert handling", "exception management"],
                keywords=["monitor", "alert", "exception", "job", "email framework", "monitoring"],
                agent_focus="G3 monitoring, job status, and alert management",
            ),
            SubTeam(
                sub_team_id="spm-troubleshooting",
                name="Troubleshooting",
                competencies=["error resolution", "failure investigation", "step failures"],
                keywords=["error", "failure", "troubleshoot", "resolution", "step failure", "exception"],
                agent_focus="Diagnosing and resolving G3 processing failures",
            ),
            SubTeam(
                sub_team_id="spm-migration",
                name="Migration",
                competencies=["PMS migration", "agent migration", "OXI to Agent"],
                keywords=["migration", "migrate", "oxi to agent", "htng to", "transition"],
                agent_focus="System and PMS migration procedures",
            ),
            SubTeam(
                sub_team_id="spm-configuration",
                name="Configuration",
                competencies=["property config", "parameter setup", "CP config"],
                keywords=["configuration", "parameter", "setup", "cp config", "activation"],
                agent_focus="G3 configuration and parameter management",
            ),
        ],
        related_teams=["ics", "sdops", "cpm"],
        shared_documents=["monitoring", "error resolution", "property management"],
        agent_capabilities=[
            "G3 RMS Process Knowledge", "Property Installation", "Job Monitoring",
            "Decision Upload", "Troubleshooting", "Migration", "Configuration",
        ],
        tools_used=["knowledge", "sql"],
    ),

    # ------------------------------------------------------------------
    # ICS — Integration & Client Support
    # ------------------------------------------------------------------
    "ics": TeamDefinition(
        team_id="ics",
        name="ICS",
        full_name="Integration & Client Support",
        team_type=TeamType.CORE,
        description="System integration, data flow, connectivity, PMS integration, Opera to OXI migrations",
        keywords=[
            "ics", "integration", "client support", "data flow", "connectivity",
            "opera to", "oxi installation", "htng integration", "ohip",
            "pms integration", "agent to agent", "migration", "ohip emulator",
            "opera cloud", "ngi agent", "opera rest", "mews",
        ],
        product_scope=["Opera Cloud", "NGI", "OXI", "OHIP", "Mews"],
        document_patterns=[
            "ICS_*", "Opera*", "OPERA*", "NGI*", "OXI*", "OHIP*",
            "MEWS*", "Integration*", "Connectivity*",
        ],
        content_signals=[
            "integration", "data flow", "connectivity", "pms",
            "opera agent", "oxi", "ohip", "htng", "ngi",
            "opera cloud", "migration", "emulator", "rest calls",
        ],
        sub_teams=[
            SubTeam(
                sub_team_id="ics-opera",
                name="Opera Integration",
                competencies=["Opera Agent", "Opera Cloud", "Opera REST", "OHIP"],
                keywords=["opera", "opera agent", "opera cloud", "ohip", "rest"],
                agent_focus="Opera system integration and troubleshooting",
            ),
            SubTeam(
                sub_team_id="ics-oxi",
                name="OXI Integration",
                competencies=["OXI installation", "OXI migration", "OXI troubleshooting"],
                keywords=["oxi", "oxi installation", "oxi migration", "oxi to agent"],
                agent_focus="OXI system integration and migration",
            ),
            SubTeam(
                sub_team_id="ics-dataflow",
                name="Data Flow",
                competencies=["data flow", "extracts", "data feeds", "REST APIs"],
                keywords=["data flow", "extract", "rest", "api", "download"],
                agent_focus="Data flow management and API integration",
            ),
        ],
        related_teams=["spm", "sdops"],
        shared_documents=["installation", "migration", "data flow"],
        agent_capabilities=[
            "Integration Troubleshooting", "PMS Migration", "Data Flow",
            "Opera Systems", "OXI Systems", "OHIP Systems",
        ],
        tools_used=["knowledge", "datadog"],
    ),

    # ------------------------------------------------------------------
    # SDOPS — Service Delivery Operations
    # ------------------------------------------------------------------
    "sdops": TeamDefinition(
        team_id="sdops",
        name="SDOPS",
        full_name="Service Delivery Operations",
        team_type=TeamType.CORE,
        description="Deployment monitoring, operational health, incident response, production operations",
        keywords=[
            "sdops", "service delivery operations", "deployment", "release",
            "production", "operational health", "incident", "escalation",
            "on-call", "runbook", "sre", "site reliability",
        ],
        product_scope=["Operations", "Infrastructure", "Monitoring"],
        document_patterns=[
            "SDOPS_*", "Deployment*", "Incident*", "Operational*",
        ],
        content_signals=[
            "deployment", "production", "incident", "escalation",
            "operational health", "runbook", "on-call", "sre",
            "monitoring framework", "alert handling",
        ],
        sub_teams=[
            SubTeam(
                sub_team_id="sdops-deployment",
                name="Deployment",
                competencies=["release management", "deployment monitoring", "rollback"],
                keywords=["deployment", "release", "rollback", "deploy"],
                agent_focus="Deployment and release management",
            ),
            SubTeam(
                sub_team_id="sdops-incident",
                name="Incident Response",
                competencies=["incident management", "escalation", "RCA"],
                keywords=["incident", "escalation", "rca", "post-mortem"],
                agent_focus="Incident detection, response, and resolution",
            ),
        ],
        related_teams=["spm", "ics", "it"],
        shared_documents=["monitoring", "alert handling", "operational procedures"],
        agent_capabilities=[
            "Deployment Monitoring", "Incident Response", "Operational Health",
            "Escalation Management",
        ],
        tools_used=["knowledge", "datadog", "smartsheet"],
    ),

    # ------------------------------------------------------------------
    # CPM — Client Project Management
    # ------------------------------------------------------------------
    "cpm": TeamDefinition(
        team_id="cpm",
        name="CPM",
        full_name="Client Project Management",
        team_type=TeamType.CORE,
        description="Client onboarding, project planning, implementation management, client communication",
        keywords=[
            "cpm", "client project", "project management", "onboarding",
            "implementation", "client communication", "webex", "scheduling",
            "project plan", "milestone", "deliverable",
        ],
        product_scope=["Implementation", "Onboarding", "Project Delivery"],
        document_patterns=[
            "CPM_*", "Project_*", "Implementation*", "Onboarding*",
        ],
        content_signals=[
            "project management", "onboarding", "implementation",
            "client communication", "webex", "scheduling", "milestone",
            "deliverable", "project plan",
        ],
        sub_teams=[
            SubTeam(
                sub_team_id="cpm-onboarding",
                name="Onboarding",
                competencies=["client onboarding", "new property onboarding", "kickoff"],
                keywords=["onboarding", "kickoff", "new client", "new property"],
                agent_focus="Client and property onboarding",
            ),
            SubTeam(
                sub_team_id="cpm-delivery",
                name="Delivery",
                competencies=["project delivery", "milestone tracking", "status reporting"],
                keywords=["delivery", "milestone", "status", "report", "handover"],
                agent_focus="Project delivery and status management",
            ),
        ],
        related_teams=["spm", "ics"],
        shared_documents=["installation", "onboarding", "project planning"],
        agent_capabilities=[
            "Client Onboarding", "Project Planning", "Implementation Management",
            "Client Communication",
        ],
        tools_used=["knowledge", "smartsheet"],
    ),

    # ------------------------------------------------------------------
    # HR — Human Resources
    # ------------------------------------------------------------------
    "hr": TeamDefinition(
        team_id="hr",
        name="HR",
        full_name="Human Resources",
        team_type=TeamType.SUPPORT,
        description="Employee policies, benefits, wellness, compliance, separation",
        keywords=[
            "hr", "human resources", "employee", "policy", "benefit",
            "wellness", "health", "leave", "separation", "appraisal",
            "relocation", "insurance", "superannuation", "referral",
            "handbook", "day care", "meal facility", "night shift",
        ],
        product_scope=["HR Policies", "Employee Benefits"],
        document_patterns=[
            "Employee*", "HR*", "*Policy*", "*Benefit*", "*Handbook*",
            "*Reimbursement*", "*Insurance*",
        ],
        content_signals=[
            "employee", "policy", "benefit", "wellness", "health",
            "leave", "separation", "appraisal", "relocation",
            "handbook", "reimbursement", "insurance", "superannuation",
        ],
        sub_teams=[
            SubTeam(
                sub_team_id="hr-policies",
                name="Policies",
                competencies=["company policies", "compliance", "governance"],
                keywords=["policy", "compliance", "governance", "handbook"],
                agent_focus="HR policy knowledge and compliance",
            ),
            SubTeam(
                sub_team_id="hr-benefits",
                name="Benefits",
                competencies=["employee benefits", "reimbursement", "insurance"],
                keywords=["benefit", "reimbursement", "insurance", "wellness"],
                agent_focus="Employee benefits and wellness programs",
            ),
        ],
        related_teams=[],
        shared_documents=[],
        agent_capabilities=[
            "Policy Knowledge", "Benefits Information", "Compliance",
        ],
        tools_used=["knowledge"],
    ),

    # ------------------------------------------------------------------
    # IT — Information Technology
    # ------------------------------------------------------------------
    "it": TeamDefinition(
        team_id="it",
        name="IT",
        full_name="Information Technology",
        team_type=TeamType.SUPPORT,
        description="Infrastructure, security, databases, servers, networking, system administration",
        keywords=[
            "it", "information technology", "infrastructure", "server",
            "database", "security", "network", "authentication",
            "system administration", "firewall", "vpn", "backup",
        ],
        product_scope=["Infrastructure", "Security", "Databases"],
        document_patterns=[
            "IT_*", "Infrastructure*", "Security*", "Network*",
        ],
        content_signals=[
            "infrastructure", "server", "database", "security",
            "network", "firewall", "vpn", "backup", "system admin",
        ],
        sub_teams=[
            SubTeam(
                sub_team_id="it-infrastructure",
                name="Infrastructure",
                competencies=["servers", "networking", "cloud infrastructure"],
                keywords=["server", "network", "cloud", "infrastructure"],
                agent_focus="Infrastructure management and provisioning",
            ),
            SubTeam(
                sub_team_id="it-security",
                name="Security",
                competencies=["security", "compliance", "access control"],
                keywords=["security", "access", "authentication", "compliance"],
                agent_focus="Security and compliance management",
            ),
        ],
        related_teams=["sdops"],
        shared_documents=["infrastructure", "security", "monitoring"],
        agent_capabilities=[
            "Infrastructure Management", "Security", "Database Administration",
        ],
        tools_used=["knowledge", "sql"],
    ),

    # ------------------------------------------------------------------
    # ROA — Revenue Optimization & Analytics
    # ------------------------------------------------------------------
    "roa": TeamDefinition(
        team_id="roa",
        name="ROA",
        full_name="Revenue Optimization & Analytics",
        team_type=TeamType.CORE,
        description="Revenue management, pricing optimization, analytics, forecasting, demand analysis",
        keywords=[
            "roa", "revenue optimization", "analytics", "pricing",
            "yield management", "demand", "forecasting", "optimization",
            "rate strategy", "competitor analysis", "pace", "revpar",
        ],
        product_scope=["Revenue Management", "Pricing", "Analytics"],
        document_patterns=[
            "ROA_*", "Revenue*", "Pricing*", "Analytics*",
        ],
        content_signals=[
            "revenue", "pricing", "optimization", "forecasting",
            "demand", "yield", "rate strategy", "competitor",
            "pace", "revpar", "analytics",
        ],
        sub_teams=[
            SubTeam(
                sub_team_id="roa-pricing",
                name="Pricing",
                competencies=["rate management", "pricing strategy", "competitive analysis"],
                keywords=["pricing", "rate", "competitor", "bar", "rate shopping"],
                agent_focus="Pricing strategy and competitive rate analysis",
            ),
            SubTeam(
                sub_team_id="roa-analytics",
                name="Analytics",
                competencies=["demand forecasting", "revenue analytics", "performance reporting"],
                keywords=["forecast", "demand", "analytics", "report", "performance"],
                agent_focus="Revenue analytics and demand forecasting",
            ),
        ],
        related_teams=["spm", "cpm"],
        shared_documents=["pricing", "forecasting", "rate management"],
        agent_capabilities=[
            "Revenue Optimization", "Pricing Strategy", "Demand Forecasting",
            "Competitive Analytics",
        ],
        tools_used=["knowledge", "sql"],
    ),
}


# =========================================================================
# OrgMap class
# =========================================================================

class OrgMap:
    """
    Organizational Map — the single source of truth for team structure.

    Provides:
    - Team lookup by ID, name, or keywords
    - Document classification to teams
    - Cross-team relationship queries
    - Sub-team and agent routing
    """

    def __init__(self) -> None:
        self.teams: dict[str, TeamDefinition] = ORG_STRUCTURE.copy()
        self._keyword_index: dict[str, str] = {}  # keyword -> team_id
        self._product_index: dict[str, str] = {}  # product -> team_id
        self._build_indices()

    def _build_indices(self) -> None:
        """Build reverse indices for fast lookup."""
        for team_id, team in self.teams.items():
            for kw in team.keywords:
                self._keyword_index[kw.lower()] = team_id
            for product in team.product_scope:
                self._product_index[product.lower()] = team_id

    def get_team(self, team_id: str) -> Optional[TeamDefinition]:
        """Get a team by ID."""
        return self.teams.get(team_id.lower())

    def get_team_by_name(self, name: str) -> Optional[TeamDefinition]:
        """Get a team by name (fuzzy match)."""
        name_lower = name.lower()
        for team in self.teams.values():
            if (name_lower == team.name.lower() or
                name_lower in team.full_name.lower()):
                return team
        return None

    def get_all_teams(self) -> list[TeamDefinition]:
        """Get all teams."""
        return list(self.teams.values())

    def get_core_teams(self) -> list[TeamDefinition]:
        """Get only core operational teams."""
        return [t for t in self.teams.values() if t.team_type == TeamType.CORE]

    def get_related_teams(self, team_id: str) -> list[TeamDefinition]:
        """Get teams related to the given team."""
        team = self.get_team(team_id)
        if not team:
            return []
        return [self.teams[tid] for tid in team.related_teams if tid in self.teams]

    def get_sub_team(self, team_id: str, sub_team_id: str) -> Optional[SubTeam]:
        """Get a specific sub-team."""
        team = self.get_team(team_id)
        if not team:
            return None
        for st in team.sub_teams:
            if st.sub_team_id == sub_team_id:
                return st
        return None

    def classify_team_by_keywords(self, text: str) -> list[tuple[str, float]]:
        """
        Classify text to teams based on keyword overlap.

        Returns list of (team_id, confidence) sorted by confidence.
        """
        text_lower = text.lower()
        scores: dict[str, float] = {}

        for team_id, team in self.teams.items():
            # Count keyword matches
            keyword_matches = sum(
                1 for kw in team.keywords if kw in text_lower
            )
            # Count content signal matches
            signal_matches = sum(
                1 for sig in team.content_signals if sig in text_lower
            )
            # Count product scope matches
            product_matches = sum(
                1 for prod in team.product_scope if prod.lower() in text_lower
            )

            total = keyword_matches * 1.0 + signal_matches * 0.8 + product_matches * 1.2
            if total > 0:
                # Normalize by number of keywords
                max_possible = len(team.keywords) + len(team.content_signals) + len(team.product_scope)
                scores[team_id] = min(total / max(max_possible * 0.1, 1), 1.0)

        # Sort by score descending
        sorted_teams = sorted(scores.items(), key=lambda x: -x[1])

        # Only return teams with meaningful scores
        return [(tid, round(s, 3)) for tid, s in sorted_teams if s > 0.05]

    def classify_team_by_filename(self, filename: str) -> list[tuple[str, float]]:
        """
        Classify a document to teams based on filename patterns.

        Returns list of (team_id, confidence).
        """
        import re
        filename_lower = filename.lower()
        scores: dict[str, float] = {}

        for team_id, team in self.teams.items():
            for pattern in team.document_patterns:
                # Convert glob pattern to regex
                regex = pattern.lower().replace("*", ".*").replace("?", ".")
                if re.match(regex, filename_lower):
                    scores[team_id] = scores.get(team_id, 0) + 0.3

        # Sort
        sorted_teams = sorted(scores.items(), key=lambda x: -x[1])
        return [(tid, round(min(s, 1.0), 3)) for tid, s in sorted_teams]

    def classify_document(
        self, text: str, filename: str = ""
    ) -> list[dict]:
        """
        Full document classification — combines keyword and filename signals.

        Returns ranked list of team matches with:
        - team_id, team_name, confidence
        - is_primary (top match)
        - is_cross_team (if multiple teams match significantly)
        - matched_sub_teams
        """
        # Keyword-based classification
        keyword_scores = self.classify_team_by_keywords(text)

        # Filename-based classification
        filename_scores = self.classify_team_by_filename(filename) if filename else []

        # Merge scores
        merged: dict[str, dict] = {}

        for team_id, score in keyword_scores:
            merged.setdefault(team_id, {"keyword_score": 0, "filename_score": 0})
            merged[team_id]["keyword_score"] = score

        for team_id, score in filename_scores:
            merged.setdefault(team_id, {"keyword_score": 0, "filename_score": 0})
            merged[team_id]["filename_score"] = score

        # Calculate combined score
        results = []
        for team_id, scores in merged.items():
            combined = scores["keyword_score"] * 0.6 + scores["filename_score"] * 0.4

            # Find matching sub-teams
            team = self.get_team(team_id)
            matched_subs = []
            if team:
                text_lower = text.lower()
                for sub in team.sub_teams:
                    sub_matches = sum(1 for kw in sub.keywords if kw in text_lower)
                    if sub_matches > 0:
                        matched_subs.append(sub.name)

            results.append({
                "team_id": team_id,
                "team_name": team.name if team else team_id,
                "full_name": team.full_name if team else "",
                "confidence": round(combined, 3),
                "keyword_score": round(scores["keyword_score"], 3),
                "filename_score": round(scores["filename_score"], 3),
                "matched_sub_teams": matched_subs,
            })

        # Sort by confidence
        results.sort(key=lambda x: -x["confidence"])

        # Mark primary and cross-team
        if results:
            results[0]["is_primary"] = True
            # Cross-team if second team has >40% of top team's score
            if len(results) > 1 and results[1]["confidence"] > results[0]["confidence"] * 0.4:
                for r in results[1:]:
                    if r["confidence"] > results[0]["confidence"] * 0.4:
                        r["is_cross_team"] = True
                    else:
                        r["is_cross_team"] = False
            else:
                for r in results[1:]:
                    r["is_cross_team"] = False

        return results

    def get_org_summary(self) -> str:
        """Generate a human-readable org summary."""
        lines = [
            "=" * 60,
            "ORGANIZATIONAL MAP",
            "=" * 60,
            "",
        ]

        for team in self.teams.values():
            type_icon = {"core": "🏢", "support": "🛠️", "learning": "📚", "governance": "📋"}
            icon = type_icon.get(team.team_type.value, "📁")

            lines.append(f"{icon} {team.name} — {team.full_name}")
            lines.append(f"   {team.description}")
            lines.append(f"   Products: {', '.join(team.product_scope)}")

            if team.sub_teams:
                lines.append(f"   Sub-teams:")
                for sub in team.sub_teams:
                    lines.append(f"     └─ {sub.name}: {sub.agent_focus}")

            if team.related_teams:
                related_names = [self.teams[tid].name for tid in team.related_teams if tid in self.teams]
                lines.append(f"   Related: {', '.join(related_names)}")

            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
