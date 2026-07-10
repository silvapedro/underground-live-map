---
name: reppit-explore
description: 'Companion to the RePPIT framework (Research, Propose, Plan, Implement, Test). Quickly brief the user on an unfamiliar area of the codebase — overview, entry points, call graph, structure, data flow. Lighter-weight than reppit-research (no persisted doc). USE FOR: explore unfamiliar codebase, brief me on this feature, what does this module do, map dependencies, understand this area, quick codebase orientation, RePPIT explore, pre-research reconnaissance. DO NOT USE FOR: producing a persisted research doc with file:line citations (use reppit-research), proposing changes (use reppit-propose). PREFER the built-in `Explore` subagent when you just need a Q&A answer — this skill is the structured briefing template.'
argument-hint: 'The unfamiliar area, feature, or module to brief on'
---

# RePPIT — Explore (companion)

A lightweight orientation skill that sits *before* `reppit-research`. Use it when the user needs a quick briefing on an unfamiliar area, not a persisted research artifact.

## When to Use

- The user asks to "brief me on", "explore", "orient me to", or "explain how X works".
- You need a mental map before deciding whether to run full `reppit-research`.
- Onboarding to a new module, feature, or subsystem.

## When NOT to Use

- The user needs a persisted `research/*.md` doc with citations → use `reppit-research`.
- The user only needs one specific answer — invoke the built-in **`Explore`** subagent directly (fast, read-only, single output).

## What to Produce

Focus on **clarity and concision**. Deliver:

- **Overview** — the feature/area and its purpose (2–4 sentences).
- **Key entry points** — functions or files with paths and what each does.
- **Call graph / dependencies** — how major functions/modules interact; external libs/services used.
- **File and directory structure** — where related code lives and how it is organized.
- **Data flow and state** — important models, inputs/outputs, side effects.

## How to Explore

1. Start by reading the primary entry file, then follow imports to map dependencies.
2. Skim tests, fixtures, or example scripts to see intended behavior.
3. Note any setup steps required to run or reproduce behavior — **do not execute** unless the user asks.
4. When multiple areas are independent, dispatch parallel read-only sub-explorations (or the `Explore` subagent).

## Anti-Patterns

- Producing a long research report — that is `reppit-research`'s job.
- Suggesting changes or refactors — this is exploration, not proposal.
- Executing setup scripts or mutating state during exploration.

## Next Step

If the user wants to make changes to what you explored, hand off to `reppit-research` (for a persisted doc) or straight to `reppit-propose` if the area is already well-known.
