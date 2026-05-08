# Execution Prompts

Copy/paste prompts for long-horizon StormLead build sessions live here. Keep research notes in `docs/research/`; keep executable milestone prompts in this folder.

## Prompts

- **`master-agent-execution-prompt.md`** - reusable base prompt and template for future StormLead execution prompts.
- **`2026-05-04-build-execution-prompt.md`** - task-by-task build sequence with implementation checklists.
- **`2026-05-04-tooling-and-agent-safety-review-prompt.md`** - milestone prompt for tightening agent/tooling docs, MCP safety, and execution-prompt consistency.
- **`2026-05-04-visual-agentic-workflow-execution-prompt.md`** - visual agentic workflow visibility milestone prompt.
- **`2026-05-04-v1-execution-prompt.md`** - local V1 technical-readiness milestone prompt.
- **`2026-05-05-first-launch-gate-gap-closure.md`** - milestone prompt for auditing and closing the first launch-gate gaps from buyer CRM through local capture, reporting, and prod/config safety.
- **`2026-05-06-finish-lead-gen-self-learning.md`** - end-to-end finish prompt for local lead-gen completion with MCP, Playwright, Puppeteer/Lighthouse, self-learning loops, and bounded runner dispatch.

## Usage Rules

- Read `AGENTS.md` before using any prompt from this folder.
- Preserve StormLead's synthetic local-simulation safety constraints unless the user explicitly approves real-world activation.
- Keep generated evidence under ignored `testing/` paths.
- Make future milestone prompts inherit `master-agent-execution-prompt.md` instead of repeating base safety/tooling rules.
- Update this index whenever a new execution prompt is added.
