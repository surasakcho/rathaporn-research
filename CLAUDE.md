## Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### 5. Commit After Verifying Major Changes

**Don't let verified work sit uncommitted.**

After completing and verifying a significant change:
- Suggest a commit before moving on to the next task.
- Don't batch unrelated changes into one commit.
- A committed checkpoint is cheap; losing verified work is not.

### 6. Suggest /compact Periodically

**Long contexts degrade quality and waste tokens.**

After approximately 20–50 prompts in a session:
- Suggest the user run `/compact` to compress context.
- Do this proactively — don't wait for slowdowns or errors.

### 7. Python Environment Hygiene

**Always use a virtual environment. Never pollute global Python.**

At the start of any Python work:
- Check for a `.venv` directory in the project root.
- If missing, create one: `python -m venv .venv`
- Always use `.venv` as the default interpreter for the session.

### 8. Output Format Convention

**Every processed output must be saved in both CSV and GeoPackage.**

- CSV: for the analysis pipeline (Stata, R, pandas)
- GeoPackage: for visual validation in QGIS

Apply this to all data preparation scripts that produce tambon-level or spatial outputs.
