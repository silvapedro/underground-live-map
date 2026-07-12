---
name: reppit-research
description: 'Research phase of the RePPIT framework (Research, Propose, Plan, Implement, Test). Document an existing codebase exactly as it is today — no suggestions, no evaluations, no future work. Produces a structured research doc with concrete file:line references. USE FOR: research codebase, investigate feature, map existing implementation, understand how X works, RePPIT research, spec-driven research, gather context before proposing changes, produce research doc, document current behavior. DO NOT USE FOR: proposing solutions (use reppit-propose), planning a change (use reppit-plan), general codebase Q&A (use the Explore subagent).'
argument-hint: 'The research question or area to investigate'
---

# RePPIT — Research

Document the existing codebase exactly as it is today. This is the **R** in RePPIT: gather truth before proposing, planning, or implementing anything.

## When to Use

- The user asks to "research", "investigate", "map", or "document" a part of the codebase before making changes.
- A downstream RePPIT step (`reppit-propose`, `reppit-plan`) needs a canonical reference doc.
- You need a shared artifact that later prompts/agents can cite.

## Behavior Contract

- **Only document what exists today.** No suggestions, no RCA, no future work, no evaluations.
- Provide concrete file paths and line references (`path/to/file.py:123-145`) in every finding.
- Read any user-mentioned files **fully** before decomposing the work.
- Prefer live code findings over historical docs when they conflict.

## Procedure

1. **Intake.** Read directly mentioned files in full. Capture the research query verbatim.
2. **Decompose.** Break the query into focused research areas and create an internal checklist.
3. **Explore in parallel.** Investigate independent areas concurrently. When helpful:
   - Inspect `git` history for context on why something exists.
   - Use `context7` for up-to-date 3rd-party API documentation.
4. **Synthesize.** After all exploration completes, combine findings. Live code wins over stale docs.
5. **Write the research doc.** Save under a top-level `research/` directory (create it if missing). File name: `research/<short-slug>.md`.

## Output Format

The research doc must contain:

- **Summary** — 3–6 sentences answering the research question.
- **Detailed findings** — grouped by component/area, each with code references in the form `path/to/file.py:123-145`.
- **Cross-component connections** — data flows, call graphs, integration points.

## Anti-Patterns

- Suggesting fixes or improvements — that belongs in `reppit-propose`.
- Findings without file:line citations.
- Skipping user-mentioned files or reading them only partially.
- Producing prose without a clear component/area structure.

## Next Step

Hand the research doc to `reppit-propose` to generate solution options.
