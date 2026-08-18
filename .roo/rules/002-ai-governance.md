# AI Governance Framework

## Principle

Every knowledge asset belongs to an owner and has a defined visibility level.

## Ownership

Possible owners include:

* Service Delivery
* Support
* Operations
* Revenue
* QA
* Shared Systems

Never assume ownership. Mark UNKNOWN if not evident.

## Visibility

Allowed values:

* Public
* Internal
* Confidential
* Restricted

Do not expose Restricted content in generated examples.

## Trust

Every generated answer should internally evaluate:

* source reliability
* document freshness
* confidence score
* evidence availability

If evidence is weak, explicitly state uncertainty instead of fabricating an answer.

## Audit Philosophy

Knowledge must be traceable.

Architecture decisions, glossary additions, and process definitions should be explainable and attributable to repository evidence.
