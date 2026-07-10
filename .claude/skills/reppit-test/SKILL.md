---
name: reppit-test
description: 'Test/Review phase of the RePPIT framework (Research, Propose, Plan, Implement, Test). Perform a comprehensive review of all uncommitted changes (staged and unstaged) and produce a prioritized action list with file:line references and severity indicators. USE FOR: review uncommitted changes, code review before commit, RePPIT test, verify implementation, review diff, prioritized action items, git diff review, pre-commit review. DO NOT USE FOR: reviewing an existing PR on GitHub (use address-pr-comments), running the test suite (use terminal), implementing fixes (use reppit-implement).'
argument-hint: 'Optionally scope the review (e.g., a subdirectory or file glob)'
---

# RePPIT — Test / Review

Review all uncommitted changes in the current branch and produce a prioritized action list. This is the **T** in RePPIT — the verification step that gates a commit.

## When to Use

- Implementation (via `reppit-implement` or otherwise) is complete and the user wants a review before committing.
- The user asks to "review my changes", "check the diff", "review before commit", or "RePPIT test".

## What This Does

- Gathers all uncommitted changes (staged + unstaged) in the current branch.
- Analyzes them across multiple dimensions.
- Produces a single prioritized action list with severity indicators and file:line references.

## Procedure

1. **Collect change context** by running:
   - `git status --porcelain`
   - `git diff`
   - `git diff --cached`
   - `git diff HEAD`
   - `git log --oneline -n 5`
2. **Analyze** the changes across:
   - Security (input validation, secrets, injection, OWASP concerns)
   - Performance (N+1, unnecessary allocations, hot-path costs)
   - Style and consistency with the surrounding code
   - Missing edge cases and error handling at boundaries
   - Dependency impact (new deps, version bumps, transitive risk)
   - Integration risk (contract changes, breaking callers)
3. **Prioritize** every finding with a severity indicator:
   - 🔴 must-fix — blocks the commit
   - 🟡 recommended — should fix before merging
   - 🟢 consider — nice-to-have
4. **Deliver** using the template below.

## Output Template

```
## Code Review

Summary: <1-2 sentences>

Action Items:
1. <indicator> <action> in `path:line`
2. <indicator> <action> in `path:start-end`
```

## Notes

- Every action item must reference `path:line` or `path:start-end`.
- Keep the summary to 1–2 sentences; the value is in the prioritized list.
- If there are zero findings, say so explicitly rather than padding the list.

## Next Step

Hand 🔴 must-fix items back to `reppit-implement` (or fix directly), then re-run this skill until the list is clean.
