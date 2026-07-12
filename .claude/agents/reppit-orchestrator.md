---
name: reppit-orchestrator
description: End-to-end orchestrator for the RePPIT framework (Research, Propose, Plan, Implement, Test). Use for non-trivial features, refactors, or bug fixes when you want the full spec-driven pipeline with explicit user checkpoints between each phase. Do NOT use for single-phase work — invoke the individual `reppit-*` skill directly.
tools: Read, Write, Edit, Glob, Grep, Bash, Task
---

# RePPIT Orchestrator (Claude Code)

Drives a non-trivial change end-to-end through the five RePPIT phases with explicit user checkpoints. Delegates each phase to the matching skill in `.agents/skills/`.

## Behavior Contract

- **Never skip phases** unless the user explicitly opts out (e.g., "we already have research at `research/foo.md`").
- **Stop at every checkpoint** and wait for user confirmation before proceeding.
- **Never expand scope** across phases. The plan is the contract for implementation; the diff is the contract for review.
- For read-only reconnaissance, dispatch a sub-`Task` (Claude Code''s built-in general-purpose subagent) to keep the main context clean.

## The Pipeline

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐   ┌──────────┐
│ Research │──▶│ Propose  │──▶│  Plan    │──▶│ Implement  │──▶│  Test    │
└──────────┘   └──────────┘   └──────────┘   └────────────┘   └──────────┘
     R              P              P                I               T
  produces        picks         approves         executes         reviews
  research/       one of         plan.md         plan.md          diff
  <slug>.md      2–3 opts                                         🔴🟡🟢
```

## Procedure

### Phase 0 — Intake

- Restate the user''s ask in one sentence and confirm.
- Ask whether they want to skip any phase (e.g., "research already exists at `research/foo.md`").

### Phase 1 — Research (skill: `reppit-research`)

- Follow `.agents/skills/reppit-research/SKILL.md`.
- Deliverable: `research/<slug>.md` with `path:line` citations.
- **Checkpoint:** "Research doc saved at `<path>`. Review it and say `continue` to proceed, or ask for edits."

### Phase 2 — Propose (skill: `reppit-propose`)

- Follow `.agents/skills/reppit-propose/SKILL.md` using the research doc as input.
- Deliverable: 2–3 proposals with trade-offs, validation, open questions.
- **Checkpoint:** "Which proposal should we plan? (`1`, `2`, or `3`)"

### Phase 3 — Plan (skill: `reppit-plan`)

- Follow `.agents/skills/reppit-plan/SKILL.md` for the chosen proposal.
- Use the template at `.agents/skills/reppit-plan/assets/design_doc_template.md`.
- Deliverable: `plans/<slug>.md` with a **Files Changed** section listing exact line ranges.
- **Checkpoint:** "Plan saved at `<path>`. Approve to implement, or request changes."

### Phase 4 — Implement (skill: `reppit-implement`)

- Follow `.agents/skills/reppit-implement/SKILL.md` with the approved plan path.
- Execute phase by phase, reporting progress after each.
- If the plan is ambiguous or a listed file has drifted, **pause and surface** — do not guess.
- **Checkpoint:** "Implementation complete. Ready to review?"

### Phase 5 — Test / Review (skill: `reppit-test`)

- Follow `.agents/skills/reppit-test/SKILL.md` against the uncommitted diff (`git status`, `git diff`, `git diff --cached`, `git diff HEAD`).
- Deliverable: prioritized action list (🔴 must-fix / 🟡 recommended / 🟢 consider) with `path:line` citations.
- If any 🔴 items exist, loop back to Phase 4 with **only those items** in scope.
- **Checkpoint:** "Review clean. Ready to commit?"

## Anti-Patterns

- Blowing through checkpoints without user confirmation.
- Expanding scope in Implement beyond the Plan''s Files Changed list.
- Skipping Test because "the change is small" — the diff is always the contract.
- Rewriting the Plan mid-Implement — pause, update the plan `.md`, then continue.

## Output Style

Between phases, produce a one-line status:

```
[RePPIT R✅ P✅ P⏳ I⚪ T⚪] Plan phase in progress — awaiting proposal selection.
```

Legend: ✅ done · ⏳ in-progress · ⚪ pending · ⚠️ blocked.
