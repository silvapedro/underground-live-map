---
name: reppit-plan
description: 'Plan phase of the RePPIT framework (Research, Propose, Plan, Implement, Test). Draft a design-doc-shaped implementation plan as a .md file — no code changes. Uses the bundled design doc template covering context, requirements, decisions, files to change (with line numbers), phases, testing, observability, and rollout. USE FOR: create implementation plan, write design doc, RePPIT plan, spec before coding, plan a feature, plan a refactor, produce plan.md, design doc for change. DO NOT USE FOR: gathering facts (use reppit-research), comparing approaches (use reppit-propose), writing the code itself (use reppit-implement).'
argument-hint: 'Scope of the change and desired location for the plan .md'
---

# RePPIT — Plan

Draft a concrete implementation plan as a Markdown file. This is the second **P** (Plan) in RePPIT. **No code is written in this phase.**

## When to Use

- The user has picked a proposal (typically from `reppit-propose`) and wants a written spec before coding.
- The user asks to "plan", "write a design doc", "spec out", or "draft a plan for" a change.

## Behavior

- **Do not implement any change.** Output is a `.md` plan only.
- Only include sections that influence *this* change. Leave testing / observability / rollout / security blank when they do not apply.
- Only plan changes that are directly requested. Keep solutions simple and focused.
- Cite files to change with **explicit line numbers** (e.g., `file_to_change_1.py (relevant snippet line 23-49)`).

## Procedure

1. **Clarify scope, constraints, and timeline.** Ask questions before writing anything down.
2. **Open the template** at [design_doc_template.md](./assets/design_doc_template.md) and mirror its structure.
3. **Draft the plan** as a `.md` file at the user's `desired_location` (ask if not given).
4. **Populate** current context, requirements, design decisions, and implementation plan with concise, actionable bullets.
5. **Files Changed section is required** and must list every impacted file with line ranges — no exceptions.
6. **Testing / Observability / Rollout / Security** — fill in only if they influence this change; otherwise omit.
7. **Stop.** Do not begin implementation. Confirm the plan with the user first.

## Template

The design doc template lives at [assets/design_doc_template.md](./assets/design_doc_template.md). It covers:

- Current Context
- Functional & Non-Functional Requirements
- Design Decisions with rationale and trade-offs
- Technical Design (core components, data models, integration points)
- **Files Changed** (with mandatory line numbers)
- Implementation Plan (phased)
- Testing Strategy
- Observability (logging, metrics)
- Future Considerations
- Dependencies
- Security Considerations
- Rollout Strategy
- References

## Anti-Patterns

- Starting to implement code during the plan phase.
- Omitting line numbers in the Files Changed section.
- Padding the plan with sections that do not apply to this change.
- Expanding scope beyond what the user requested.

## Next Step

Hand the plan `.md` path to `reppit-implement` to execute it.
