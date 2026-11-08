# profiles/ - thin global Hermes souls (installed BY HAND, not into projects)
The full souls are owned by the prompts specialist; this kit ships them for reference only.
- `hermes-architect.SOUL.md` / `hermes-worker.SOUL.md`: <= 3800 chars each, no per-turn variable header (prompt cache).
- A project installs them into the Hermes profile the model runs under, never into the project tree.
- A global profile runs the FULL soul, not the thin one: `.hermes/prompts/ARCHITECT.md` (fill `{{PROJECT_NAME}}`, `{{OWNER}}`, `{{REPLY_LANG}}`) or `.hermes/prompts/WORKER.md` (fill `{{PROJECT_NAME}}`, `{{REPLY_LANG}}`); no project: the kit name. Copy it again after every change to that file; nothing in the kit tree can see the profile copy.
