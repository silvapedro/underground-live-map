---
name: reppit-implement
description: 'Implement phase of the RePPIT framework (Research, Propose, Plan, Implement, Test). Execute a pre-approved plan .md exactly as written — no scope expansion, no re-design. USE FOR: implement plan, execute design doc, RePPIT implement, code the plan, ship the plan, apply the design doc, build what the plan says. DO NOT USE FOR: writing the plan (use reppit-plan), proposing alternatives (use reppit-propose), reviewing/testing after (use reppit-test).'
argument-hint: 'Path to the plan .md to implement'
---

# RePPIT — Implement

Execute the plan described in the provided `.md` file. This is the **I** in RePPIT.

## When to Use

- The user provides a path to a plan/design doc and asks to implement it.
- The user says "implement the plan", "execute /path/to/plan.md", or "build what the plan says".

## Behavior Contract

- **Follow the plan exactly.** Do not expand scope, redesign, or add features the plan does not describe.
- If the plan is ambiguous or missing a critical detail, **stop and ask** rather than guessing.
- Only touch files listed in the plan's **Files Changed** section. If a new file must be added, confirm with the user first.
- Keep changes minimal and focused; no drive-by refactors.

## Procedure

1. **Read the plan `.md` in full** before touching any code.
2. **Confirm the file list.** Cross-check the plan's Files Changed section against reality (do the files/line ranges still exist?). If drift is detected, surface it and pause.
3. **Execute phase by phase** in the order the plan specifies.
4. **After each phase**, briefly report progress (files changed, tests added).
5. **Do not run `reppit-test`** — hand off to it when implementation is complete.

## Anti-Patterns

- Adding features, error handling, docstrings, or refactors the plan did not request.
- Modifying files outside the plan's Files Changed list.
- Silently resolving ambiguity by guessing.
- Rewriting the plan mid-implementation instead of pausing to update it.

## Next Step

Hand off to `reppit-test` for review and verification.
