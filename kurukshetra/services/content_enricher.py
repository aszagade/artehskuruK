"""
Content-Aware Metadata Enrichment
==================================

Classifies documents by:
- Team owner (SDOPS, SPM, Support, etc.)
- Product (G3 RMS, Opera Cloud, NGI, etc.)
- Document type (process guide, troubleshooting, config)
- Domain area (installation, monitoring, migration, etc.)

Uses pattern matching against known IDeaS terminology — no LLM dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TeamOwner(Enum):
    """Allowed team owners per governance rules."""
    SERVICE_DELIVERY = "Service Delivery"
    SDOPS = "SDOPS"
    SUPPORT = "Support"
    OPERATIONS = "Operations"
    REVENUE = "Revenue"
    QA = "QA"
    SHARED_SYSTEMS = "Shared Systems"
    UNKNOWN = "UNKNOWN"


class ProductType(Enum):
    """IDeaS products and systems."""
    G3_RMS = "G3 RMS"
    OPERA_CLOUD = "Opera Cloud"
    NGI = "NGI"
    OXI = "OXI"
    OHIP = "OHIP"
    FOLS = "FOLS"
    CP = "CP"
    RSS = "RSS"
    TARS = "TARS"
    D360 = "D360"
    GENERAL = "General"
    UNKNOWN = "UNKNOWN"


class DocumentClassification(Enum):
    """Document type classification."""
    PROCESS_GUIDE = "Process Guide"
    TROUBLESHOOTING = "Troubleshooting"
    CONFIGURATION = "Configuration"
    API_REFERENCE = "API Reference"
    BEST_PRACTICE = "Best Practice"
    MONITORING = "Monitoring"
    INSTALLATION = "Installation"
    MIGRATION = "Migration"
    ERROR_RESOLUTION = "Error Resolution"
    POLICY = "Policy"
    UNKNOWN = "UNKNOWN"


class Visibility(Enum):
    """Access control level."""
    PUBLIC = "Public"
    INTERNAL = "Internal"
    CONFIDENTIAL = "Confidential"
    RESTRICTED = "Restricted"


@dataclass(slots=True)
class ContentMetadata:
    """Enriched metadata derived from document content analysis."""
    team_owner: TeamOwner
    product: ProductType
    doc_classification: DocumentClassification
    visibility: Visibility
    confidence: float  # 0.0 - 1.0
    detected_terms: list[str] = field(default_factory=list)
    domain_areas: list[str] = field(default_factory=list)
    related_systems: list[str] = field(default_factory=list)


# -----------------------------------------------------------------------
# Keyword dictionaries for classification
# -----------------------------------------------------------------------

TEAM_KEYWORDS: dict[TeamOwner, list[str]] = {
    TeamOwner.SDOPS: [
        "sdops", "service delivery operations", "deployment", "release",
        "production", "monitoring framework", "operational health",
        "escalation", "incident", "on-call", "runbook",
    ],
    TeamOwner.SUPPORT: [
        "support team", "support engineer", "helpdesk", "ticket",
        "case management", "customer support", "first response",
        "knowledge article", "troubleshooting guide",
    ],
    TeamOwner.OPERATIONS: [
        "operations", "ops team", "sre", "site reliability",
        "uptime", "sla", "availability", "disaster recovery",
    ],
    TeamOwner.REVENUE: [
        "revenue management", "pricing", "rate shopping", "bar",
        "yield", "optimization", "forecasting", "demand",
    ],
    TeamOwner.SERVICE_DELIVERY: [
        "service delivery", "client services", "account management",
        "implementation", "onboarding", "handover",
    ],
    TeamOwner.QA: [
        "quality assurance", "testing", "regression", "validation",
        "test case", "test plan", "uat",
    ],
    TeamOwner.SHARED_SYSTEMS: [
        "shared systems", "infrastructure", "database", "server",
        "network", "security", "authentication",
    ],
}

PRODUCT_KEYWORDS: dict[ProductType, list[str]] = {
    ProductType.G3_RMS: [
        "g3 rms", "g3-rms", "g3 rms", "g3", "revenue management system",
        "decision upload", "full upload", "first decision", "catchup",
        "property configuration", "rms monitoring",
    ],
    ProductType.OPERA_CLOUD: [
        "opera cloud", "opera agent", "cloud agent", "ngi agent",
        "opera cloud agent",
    ],
    ProductType.NGI: [
        "ngi", "next generation integration", "ngi hilton",
        "ngi property", "ngi agent",
    ],
    ProductType.OXI: [
        "oxi", "opera xi", "oxi installation", "oxi to agent",
        "oxi migration",
    ],
    ProductType.OHIP: [
        "ohip", "opera hospitality", "ohip emulator", "core ohip",
        "ohip installation",
    ],
    ProductType.FOLS: [
        "fols", "full upload", "fols installation", "fols property",
        "fols rollback",
    ],
    ProductType.CP: [
        "cp", "continuous pricing", "cp configuration", "cp tax",
        "cp optimal", "cpdecision",
    ],
    ProductType.RSS: [
        "rss", "rate shopping", "rate shopping vendor", "rss catchup",
        "rss extract",
    ],
    ProductType.TARS: [
        "tars", "tars error", "tars decision", "tars acknowledgement",
    ],
    ProductType.D360: [
        "demand 360", "d360", "demand360",
    ],
}

CLASSIFICATION_KEYWORDS: dict[DocumentClassification, list[str]] = {
    DocumentClassification.PROCESS_GUIDE: [
        "process", "procedure", "step by step", "how to", "guide",
        "workflow", "steps to follow", "process document",
    ],
    DocumentClassification.TROUBLESHOOTING: [
        "troubleshoot", "troubleshooting", "issue", "problem",
        "resolution", "fix", "debug", "investigate",
    ],
    DocumentClassification.CONFIGURATION: [
        "configuration", "config", "setup", "settings", "parameter",
        "activation", "enable", "disable",
    ],
    DocumentClassification.MONITORING: [
        "monitor", "monitoring", "alert", "notification", "exception",
        "email framework", "watch", "track",
    ],
    DocumentClassification.INSTALLATION: [
        "install", "installation", "reinstall", "add property",
        "new property", "de-install", "setup",
    ],
    DocumentClassification.MIGRATION: [
        "migration", "migrate", "transition", "switch", "move",
        "from one to another",
    ],
    DocumentClassification.ERROR_RESOLUTION: [
        "error", "failure", "fail", "exception", "crash",
        "resolution steps", "resolve", "handling",
    ],
    DocumentClassification.POLICY: [
        "policy", "handbook", "guideline", "regulation",
        "compliance", "code of conduct",
    ],
}

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "installation": ["install", "setup", "add property", "new property"],
    "monitoring": ["monitor", "alert", "notification", "exception", "job"],
    "troubleshooting": ["troubleshoot", "error", "failure", "resolution"],
    "migration": ["migration", "migrate", "transition"],
    "configuration": ["config", "parameter", "setting", "activation"],
    "decision_upload": ["decision upload", "du", "full upload", "first decision"],
    "data_flow": ["data flow", "extract", "data feed", "pull"],
    "reporting": ["report", "scheduled report", "email", "delivery"],
}


class ContentEnricher:
    """
    Analyzes document content to extract organizational metadata.

    No LLM dependency — uses keyword/pattern matching against known
    IDeaS terminology for fast, deterministic classification.
    """

    def __init__(self) -> None:
        self._compiled_team = self._compile_keywords(TEAM_KEYWORDS)
        self._compiled_product = self._compile_keywords(PRODUCT_KEYWORDS)
        self._compiled_class = self._compile_keywords(CLASSIFICATION_KEYWORDS)

    @staticmethod
    def _compile_keywords(
        keyword_map: dict[Enum, list[str]],
    ) -> dict[Enum, re.Pattern]:
        """Pre-compile keyword patterns for efficient matching."""
        compiled = {}
        for enum_val, keywords in keyword_map.items():
            pattern = re.compile(
                r"\b(?:" + "|".join(re.escape(kw) for kw in keywords) + r")\b",
                re.IGNORECASE,
            )
            compiled[enum_val] = pattern
        return compiled

    def enrich(
        self,
        text: str,
        filename: str = "",
    ) -> ContentMetadata:
        """
        Analyze document text and extract organizational metadata.

        Args:
            text: Full document text content
            filename: Original filename for additional signals

        Returns:
            ContentMetadata with classified fields and confidence
        """
        combined_text = f"{filename} {text}"
        combined_lower = combined_text.lower()

        # Classify team owner
        team, team_conf = self._classify_enum(
            combined_lower, self._compiled_team
        )

        # Classify product
        product, prod_conf = self._classify_enum(
            combined_lower, self._compiled_product
        )

        # Classify document type
        doc_class, class_conf = self._classify_enum(
            combined_lower, self._compiled_class
        )

        # Detect domain areas
        domain_areas = self._detect_domains(combined_lower)

        # Detect related systems
        related = self._detect_related_systems(combined_lower)

        # Visibility inference
        visibility = self._infer_visibility(combined_lower)

        # Detected terms (acronyms, product names)
        detected_terms = self._extract_terms(combined_text)

        # Overall confidence
        confidence = (team_conf + prod_conf + class_conf) / 3.0

        return ContentMetadata(
            team_owner=team,
            product=product,
            doc_classification=doc_class,
            visibility=visibility,
            confidence=round(confidence, 3),
            detected_terms=detected_terms,
            domain_areas=domain_areas,
            related_systems=related,
        )

    def _classify_enum(
        self,
        text: str,
        compiled_map: dict[Enum, re.Pattern],
    ) -> tuple[Enum, float]:
        """Classify text against pre-compiled keyword patterns."""
        scores: dict[Enum, int] = {}
        for enum_val, pattern in compiled_map.items():
            matches = pattern.findall(text)
            if matches:
                scores[enum_val] = len(matches)

        if not scores:
            return list(compiled_map.keys())[-1], 0.0  # UNKNOWN / last enum

        best = max(scores, key=scores.get)
        total_matches = sum(scores.values())
        confidence = scores[best] / max(total_matches, 1)

        return best, min(confidence, 1.0)

    def _detect_domains(self, text: str) -> list[str]:
        """Detect domain areas mentioned in the document."""
        found = []
        for domain, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    found.append(domain)
                    break
        return found

    def _detect_related_systems(self, text: str) -> list[str]:
        """Detect related technical systems mentioned."""
        systems = [
            "Datadog", "Smartsheet", "SFDC", "Salesforce", "JIRA",
            "Jenkins", "Docker", "Kubernetes", "RabbitMQ", "Kafka",
            "SQL Server", "SAS", "Opera", "SynXis", "Curtis",
            "Amadeus", "Sabre", "Mews",
        ]
        found = []
        text_lower = text.lower()
        for system in systems:
            if system.lower() in text_lower:
                found.append(system)
        return found

    def _infer_visibility(self, text: str) -> Visibility:
        """Infer document visibility from content signals."""
        restricted_signals = [
            "confidential", "restricted", "internal only",
            "do not share", "sensitive", "password",
        ]
        public_signals = [
            "public", "customer facing", "client",
            "public documentation",
        ]

        for signal in restricted_signals:
            if signal in text:
                return Visibility.CONFIDENTIAL

        for signal in public_signals:
            if signal in text:
                return Visibility.PUBLIC

        return Visibility.INTERNAL  # Default for operational docs

    def _extract_terms(self, text: str) -> list[str]:
        """Extract notable terms, acronyms, and product names."""
        terms = set()

        # Acronyms (2-6 uppercase letters)
        for match in re.finditer(r"\b([A-Z]{2,6})\b", text):
            term = match.group(1)
            # Filter common English words
            if term not in {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
                           "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "HAS", "HIS",
                           "HOW", "ITS", "MAY", "NEW", "NOW", "OLD", "SEE", "WAY",
                           "WHO", "DID", "GET", "LET", "SAY", "SHE", "TOO", "USE",
                           "CTX", "PDF", "URL", "API", "SQL", "IMG", "END", "MID"}:
                terms.add(term)

        return sorted(terms)[:20]  # Cap at 20 terms
