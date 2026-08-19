from __future__ import annotations

from .intent import IntentClassifier
from .models import Plan


class SANJAYAPlanner:

    def __init__(self):
        self.classifier = IntentClassifier()

    def create_plan(self, query: str) -> Plan:
        return self.classifier.classify(query)