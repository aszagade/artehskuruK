# Knowledge & Learning Framework

## Philosophy

The LLM is a reasoning engine, not the source of truth.

Repository knowledge is the primary authority.

## SEAL Learning Model

SEAL continuously improves organizational knowledge without modifying original documents.

It maintains four logical registries:

* Glossary
* Unknown Terms
* Decisions
* Patterns

These are conceptual registries and should not be created automatically unless instructed.

## Unknown Handling

If an acronym, process, or business term is not supported by repository evidence:

1. Mark it as UNKNOWN.
2. Explain what information is missing.
3. Never fabricate a definition.

## Knowledge Priority

Use evidence in this order:

1. Repository documents
2. Source code
3. SQL and configuration
4. User clarification
5. General reasoning

General model knowledge should never override repository evidence.

## Continuous Improvement

When newer documents contradict older ones, identify the conflict and present both versions instead of silently replacing historical knowledge.
