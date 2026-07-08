---
name: reppit-propose
description: 'Propose phase of the RePPIT framework (Research, Propose, Plan, Implement, Test). Generate up to two or three distinct solution proposals grounded in a research doc plus a new feature/change request. Each proposal includes trade-offs, impacted systems, validation strategy, and open questions. USE FOR: propose solutions, generate solution options, evaluate approaches, RePPIT propose, solution design alternatives, compare approaches before planning, produce proposal doc. DO NOT USE FOR: gathering codebase facts (use reppit-research first), writing a chosen implementation plan (use reppit-plan), implementing code (use reppit-implement).'
argument-hint: 'The feature/change request and path to the research doc'
---

# RePPIT — Propose

Generate distinct solution proposals grounded in a prior research document. This is the **P** (Propose) in RePPIT.

## When to Use

- A `research/*.md` doc exists (produced by `reppit-research`) and the user wants options before committing to a plan.
- The user asks to "propose", "compare approaches", "suggest solutions", or "explore options".

## Prerequisite

**Requires a research document** produced by `reppit-research`. If none exists, stop and instruct the user to run `reppit-research` first (or ask for the doc path).

## Behavior

- Treat the research doc as the canonical reference — do not re-derive facts.
- Produce **2–3 distinct approaches**, ordered from most to least aligned with the research constraints.
- Every proposal highlights trade-offs, impacted systems, validation steps, and open questions.
- Cite specifics with `` `path/to/file.py:lines` ``.

## Procedure

1. **Intake.** Capture the user's request and the path to the research doc.
2. **Parse research.** Read the research doc fully. Extract:
   - Constraints
   - Relevant modules
   - Dependencies and data flows
   - Prior decisions
3. **Synthesize solution space.** Derive candidate approaches. For each: primary changes, affected code paths, required migrations/config updates, rollout considerations.
4. **Validation planning.** For each approach, identify tests, experiments, or observability needed to prove it works. Surface critical unknowns.
5. **Deliver** using the template below.

## Output Template

```
## Solution Proposals

Context:
- Request: <short restatement of the ask>
- Research Source: <filename and key sections used>

Proposal 1 — <title>
- Overview: <2-3 sentences>
- Key Changes: <components/modules>
- Trade-offs: <risks vs benefits>
- Validation: <tests/experiments/metrics>
- Open Questions: <gaps or follow-ups>

Proposal 2 — <title>
- ...
```

## Notes

- If the research doc does not directly address the request, **call out the gaps** and recommend more research before proposing.
- Stay concise; favor clarity over exhaustive detail while remaining actionable.
- Do not silently pick a winner — present the trade-offs and let the user choose.

## Next Step

Once the user picks a proposal, hand it to `reppit-plan` to draft the design doc.
