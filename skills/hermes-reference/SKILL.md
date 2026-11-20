---
name: hermes-reference
description: "Use when designing, connecting, checking or fixing a Hermes agent. Quick reference from the official Hermes docs, checked on this Mac: where things live, limits, tools, connections, security, messaging, verify commands, and fixes."
version: 1.0.0
---

# Hermes reference (for building and checking agents)

Official docs: https://hermes-agent.nousresearch.com/docs (Skills, Tools & Toolsets, Memory, Personality & SOUL.md, Context Files, MCP, Security, Configuration, Messaging, Tips, CLI Commands). Commands below were checked on this Mac's install. If something here disagrees with the live docs or with `hermes <command> --help`, trust those and tell Robi.

## 1. An agent is a profile

A "Bot" in the Hermes app is a profile: `~/.hermes/profiles/<name>/` with its own `SOUL.md`, `config.yaml`, `.env`, `skills/`, `memories/`, sessions and logs. `hermes -p <name> <command>` runs anything as that agent. One gateway serves all profiles (`hermes gateway list`).

## 2. How instructions load

| File | Holds | Loaded from |
|---|---|---|
| `SOUL.md` | who it is: voice, tone, how it handles doubt | the profile home, always |
| `AGENTS.md` | rules for the work in one folder | the **working folder** (outside a git repo, only that folder) |
| `.hermes.md` | same, highest priority | working folder |

- Only one project file type loads (`.hermes.md`, then `AGENTS.override.md`, then `AGENTS.md`, then `CLAUDE.md`).
- One-shot runs (`hermes -p x -z`) use the folder you pass with `--in`. Always pass it.
- Context files are scanned for prompt injection and blocked if flagged. They count against the budget on **every message**, so keep them short.
- Rule of thumb: if it should follow the agent everywhere, `SOUL.md`. If it belongs to one folder or project, `AGENTS.md`.

## 3. Memory (limits matter)

- `MEMORY.md` (agent notes) 2,200 characters. `USER.md` (about the person) 1,375 characters. Both load at session start as a snapshot; changes show next session.
- Memory is per profile. Do not point two agents at one profile.
- Past chats are searchable (`session_search`, `hermes sessions list`). External memory providers are optional (`hermes memory setup`). Check with `hermes -p <name> memory status`.
- Save durable facts (preferences, locations, conventions), not trivia or temporary context. `memory.write_approval: true` makes it ask first.

## 4. Skills

- A skill is `skills/<category>/<name>/SKILL.md` with frontmatter `name`, `description`, `version`, optional `references/`, `templates/`, `scripts/`.
- Loaded on demand: the list of names and descriptions is always visible, the body loads only when needed. Write the **description** so it says *when to use it*. Keep the body under about 24,000 characters.
- Check: `hermes -p <name> skills list`. Audit hub skills: `hermes skills audit`. Invoke by name with `/skill-name`.
- Lean agent: create the profile with `--no-skills` so it carries only the skills it needs.
- `skills.write_approval: true` makes agent-written skills wait for review.

## 5. Tools and toolsets

- Toolsets on this install (`hermes -p <name> tools list` shows each as enabled or disabled): `web`, `browser`, `terminal`, `file`, `code_execution`, `vision`, `video`, `image_gen`, `video_gen`, `x_search`, `tts`, `stt`, `skills`, `todo`, `kanban`, `memory`, `context_engine`, `session_search`, `connections`, `clarify`, `delegation`, `cronjob`, `computer_use`, and plugin toolsets such as `a2a`. MCP servers add `mcp-<server>`.
- Turn a toolset off for one agent with `agent.disabled_toolsets` in its `config.yaml` (`create_agent.py` does this from `toolsets_off`). `hermes tools` with no subcommand is interactive and cannot run from a script; use `hermes -p <name> tools list`.
- Least privilege: give an agent only the toolsets its job needs. Plain questions: browse the web? read and write files? run commands on the computer? create images? speak aloud? run on a timer? call other helpers?
- Some tools need keys (for example web search). A missing key means the tool is not really connected.

## 6. Connecting outside tools (MCP)

- Servers live under `mcp_servers:` in the **agent's** `config.yaml`. Stdio: `command`, `args`, `env`. HTTP: `url`, `headers`. OAuth servers: `auth: oauth`, then `hermes -p <name> mcp login <server>`.
- Tools appear as `mcp_<server>_<tool>`. Limit them with `tools.include` or `tools.exclude` (include wins). Prefer an include list of only what the job needs, and read-only tools first.
- Secrets: write `${VAR}` in config and keep the value in the agent's `.env` (permissions 600). Never put a key in chat, `SOUL.md`, `AGENTS.md` or config.
- Verify: `hermes -p <name> mcp list`, then `hermes -p <name> mcp test <server>`, then ask the agent for one harmless read. After config changes run `/reload-mcp`. Startup problems show in `hermes logs`.
- Typical failures: 401/403 wrong token or login; 400/405 the endpoint is SSE-only (`transport: sse`); HTML back means the URL is a web page; tools missing means a filter, `enabled: false` or a failed connection; `npx` missing means Node is not found.

## 7. Safety model

- Approvals (`approvals.mode`): `smart` (default), `manual`, `off`. Keep `smart` or `manual`. Never `off`, and avoid `--yolo`.
- One-shot runs, cron jobs and API sessions cannot ask anyone, so risky commands are **denied** there by default. That is correct; do not loosen it without a reason.
- `approvals.deny` takes patterns that are always blocked. Use it for "never" rules that map to commands.
- File tools refuse protected paths (SSH keys, `.env`, OAuth files). But the terminal runs as the same Mac user, so on this Mac a folder rule is a **rule the agent follows, not a wall**. Say that plainly. A real wall needs a sandbox (Docker or similar), which is not installed here.
- Secrets live in `.env` or the Keychain, never copied between agents.

## 8. Reaching the agent

- **Hermes app:** it appears under Bots. **Terminal:** `hermes -p <name>`. **Another agent:** `hermes -p <name> --in <folder> -z "<task>"`.
- **Telegram (one bot per agent).** A token can only be used by one agent, so every agent that should be on Telegram gets its **own** bot. Easiest: Hermes app, Messaging, Telegram, pick the agent, "Create with QR". It creates the bot, finds the numeric user ID, writes `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS` into that agent's `.env` and restarts the gateway. Manual: create the bot with @BotFather (`/newbot`), find the numeric ID with @userinfobot, then run `hermes -p <name> gateway setup` or put the two lines in that agent's `.env`. **Robi handles the token. You never see, type or store it.**
- **Access is locked by default.** Only numeric IDs in `TELEGRAM_ALLOWED_USERS` may talk to it (not usernames). Never allow everyone on an agent that has terminal access. `hermes pairing list|approve|revoke` also exists.
- After any config change run `hermes gateway restart`, but first make sure nobody's task is running (`active_agents` is 0 in `~/.hermes/gateway_state.json`). `/sethome` in a chat sets where timer results go. In groups: turn off Group Privacy in BotFather and re-add the bot, or make it admin; `telegram.require_mention: true` limits replies.
- **Check:** `hermes gateway status`, `~/.hermes/logs/gateway.log`, `/whoami` and `/platform list` inside the chat, and `~/.hermes/gateway_state.json` showing `<name>:telegram` as `connected`. Then send it a hello from the allowed account and see it answer.
- **Failures:** no reply means a wrong token or a stopped gateway; "Unauthorized" means your ID is not on the allowlist; "concurrent polling" means two gateways use one token; adapter paused means `/platform resume telegram`; silent despite a token means `platforms.telegram.enabled: false`.
- Chat is short by nature: an agent reached by Telegram should keep answers brief and avoid long tables.

### Voice notes (speech to text)

- Hermes transcribes incoming voice notes automatically (`stt.enabled: true`). With no engine available the agent only gets an audio file; its own log (`~/.hermes/profiles/<name>/logs/gateway.log`) says "Voice transcription failed" and the agent should say so and ask for typing, never guess.
- Engines (`stt.provider`): `local` (faster-whisper, no key, voice stays on the Mac), `groq` (`GROQ_API_KEY`), `openai` (`VOICE_TOOLS_OPENAI_KEY`). Auto order: local, groq, openai.
- **Local setup on this Mac (done 2026-11-10):** install into the *active* Hermes runtime with Hermes's own uv: `~/.hermes/tools/uv-*/uv pip install --python <runtime venv>/bin/python faster-whisper "av==16.1.0"`. The runtime venv is the one `hermes doctor` calls "Runtime venv staged". **Pin `av`:** the newest `av` (19) breaks faster-whisper 1.2.1 with "open() got an unexpected keyword argument 'metadata_errors'"; 16.1.0 and 15.1.0 work. The runtime has no pip. The model downloads from Hugging Face on first use (`small` is about 460 MB in `~/.cache/huggingface`).
- Settings per agent: `hermes -p <name> config set stt.provider local`, `stt.local.model small`, `stt.language ""` (auto-detect; the default `en` forces English and ruins Tagalog or Taglish). Then restart the gateway with `hermes -p default gateway restart` when no task is running.
- The docs do not say whether the install survives `hermes update`; after an update, re-check with a spoken test and reinstall if needed.
- Test without a person: `say -o sample.aiff "..."`, then transcribe it with the runtime's Python and `faster_whisper.WhisperModel('small', device='cpu', compute_type='int8')`. Then ask Robi to send a real voice note and check the agent's log.

## 9. Verify toolbox

| Question | Command |
|---|---|
| Is Hermes healthy? | `hermes doctor` |
| Is the agent configured? | `hermes -p <n> config check`, `hermes -p <n> config get <key>` |
| Is it served? | `hermes gateway list` |
| What does every message cost? | `hermes -p <n> prompt-size --json` |
| Which tools and skills? | `hermes -p <n> tools list`, `hermes -p <n> skills list` |
| Are connections alive? | `hermes -p <n> mcp list`, `hermes -p <n> mcp test <server>` |
| What happened? | `hermes logs errors -n 50 --since 1h`, `hermes sessions list` |
| What is it remembering? | `hermes -p <n> memory status`, read `memories/MEMORY.md` |
| Does it answer? | `hermes -p <n> --in <folder> -z "<prompt>"` (exit 0 ok, 2 failed or partial, 130 interrupted, 1 no text) |

## 10. Cost and quality

- Routine work: a fast model. Judgment and careful writing: a stronger one. Avoid switching models mid-conversation.
- Keep the instructions stable and short so caching works; check with `prompt-size`.
- Be specific in requests. Put recurring rules in `AGENTS.md`, recurring procedures in a skill.

## 11. Symptom to fix

| Symptom | Likely cause and fix |
|---|---|
| Ignores messages on Telegram | not on the allowlist or not paired; adapter paused (`/platform resume`) |
| Works in the app, not in a one-shot | forgot `--in`, or the action needs approval (denied in headless runs) |
| "I can't do that" for a tool it should have | toolset disabled, MCP filter, failed MCP connection, or missing key |
| Never uses its skill | skill description does not say when to use it; skill not in its profile |
| Forgets things | memory is full (2,200 characters); consolidate, or use session search |
| Works in the wrong folder | working folder not set, or `AGENTS.md` missing there |
| Slow and expensive | system prompt or skill list too large; use `prompt-size`; lean skills; a faster model |
| Asks approval all the time | approvals mode `manual`; consider `smart`, or allow a specific safe pattern |
