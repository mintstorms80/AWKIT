# NOTICE - where the kit's ideas came from

The kit's text is its own wording. Where a rule was adapted from a public repository, the file says so in a line
`(Adapted from <source>, <licence>)`. This table is the audit trail; `selftest.py` fails when a source named in the payload is missing here.

| Source | Licence seen | Taken (kit version) | Not taken |
|---|---|---|---|
| DannyMac180/skills | MIT | work packet, deeper-not-bigger (2.2.0) | explain-this, modsmith, codex-relay |
| DannyMac180/fable-advisor | MIT | Reviewer role and verdicts, failure and refusal rules (2.2.1) | Codex/Luna/Sol lanes, lanes.json, racing two diffs |
| DannyMac180/meta-agent | none stated ("License TBD") | nothing copied | everything |
| vercel-labs/agent-desktop | Apache-2.0 | blind-check, deferral rule, optional pre-commit guard, version consistency (2.2.2) | the CLI and its platform skills |
| mattpocock/skills | MIT | bug cards, vertical slices, two-axis review, steering signals (2.3.0) | glossary/ADR flow, wayfinder, parallel implementers |
| obra/superpowers | MIT | review pack, third-fail, rulings list, regression revert-proof (2.4.0) | per-task fresh implementers, worktrees, plugin installs |
| anthropics/skills | Apache-2.0 (document skills docx/pdf/pptx/xlsx: proprietary, nothing taken) | cold read of a card (2.4.1) | skill-creator eval harness, doc skills, mcp-builder, webapp-testing |
| multica-ai/andrej-karpathy-skills | none found (no LICENSE file in the repository) | one rule in own wording, no text copied: SPEC cards are surgical (2.4.2) | the four-principle CLAUDE.md as such, EXAMPLES.md |
| cloudflare/security-audit-skill | MIT | three-verdict findings (CONFIRMED / NEEDS-VALIDATION without severity / REJECTED), a verifier briefed to refute, machine-checked finding lines (2.5.0) | coverage ledger, sandboxed validation, the attack-class libraries |
| ckelsoe/prompt-architect | MIT | pre-mortem before BLOCK Q (2.6.0); prompt-quality scoring dimensions read, not taken | the 31 frameworks (CO-STAR, RISEN...), installer, scoring UI: prompt-engineering product, the kit writes cards |
| skillsdirectory.com (listing of the final-release-review skill by JoshuaShepherd, a copy of an openai-agents-js repo skill; licence not shown on the page) | unknown | idea only, own wording: deterministic gate rule, cite a trigger or say ship (2.6.0); `review_pack.py` defaults to the newest tag | the directory itself (100k+ skills, most repo-specific; a security grade A is not a quality grade), implementation-strategy (semver boundary), code-change-verification (pnpm stack) |
| dev.to/devprompts (4 articles: code review, debugging, architecture, documentation prompts) | no licence stated | ideas only: 'nothing found' is a valid answer (2.6.0) | the prompt listicles: the kit's SWARM/CARD rules are already stricter (negative constraints, enumerated checklists, context+constraint+format) |
| archgee.com/blog/chatgpt-prompts-architects | n/a | nothing: prompts for building architects, not software | everything |
| agent-souls.com/personas (wklken/souls) | none stated | nothing: persona prompts, AI-generated; risk-tiered gates noted as an unbuilt idea (2.6.0) | everything |
| clawhub.ai/skills (Skill Vetter by spclaudehome; also self-improving-agent, Self-Improving + Proactive, Proactive Agent MIT) | Skill Vetter: not stated on the page | idea only, own regex: payload red-flag check (2.6.0) | the self-improvement and proactive skills (runtime memory for a chat agent), every integration skill |
| mergisi/awesome-openclaw-agents | MIT | nothing: persona templates and 5 Claude Code skills; one unbuilt idea (cache-busting hook signal) noted in CHANGELOG 2.6.0 | everything |
| github/spec-kit | MIT | nothing: processes already covered by AGENTS.md, card-lint, re_audit, Bug cards, questionnaire; 3 candidate checks measured at 0 hits (CHANGELOG 2.6.1) | everything |
| llm-as-a-verifier/llm-as-a-verifier | MIT | nothing: LLM-graded verification, API cost (CHANGELOG 2.6.1) | everything |
| rajatslakhina/reward-hacking-gate-article-demo | MIT | nothing: diff-audit idea measured on 4 repos, would fire on legitimate edits (CHANGELOG 2.6.1) | everything |
| jackiectl/research-agent-pitfalls | MIT | nothing: per-rule firing ledger noted as unbuilt idea (CHANGELOG 2.6.1) | everything |
| agent-done-or-not (mohamedzhioua), verification-before-completion (obra/superpowers), Prufgate (Apache-2.0), Test Ratchet (MIT), review-pro (MIT), codeprobe (MIT), agent-deck, Arai (Apache-2.0), Urd (MIT), IIKit, retro-harness (MIT) | mixed, as stated on each page | idea only, own code: `learn.py` stale-gate (2.6.1) | their engines, hooks, CLIs and installers; everything else in them is covered by an existing kit rule (CHANGELOG 2.6.1) |
