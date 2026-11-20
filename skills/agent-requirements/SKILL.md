---
name: agent-requirements
description: "Use when deciding whether and what helper (agent) to build, checking it meets every requirement, writing the Agent Brief with tests, and building it only after approval."
version: 2.0.0
---

# Agent requirements, readiness gate, brief and build

Companions: `agent-lifecycle` (the 10 stages), `hermes-reference` (Hermes facts), `~/Team-Workspace/Agents/CONVENTIONS.md` (how agents are organized), `~/Team-Workspace/Agents/AGENT-REQUIREMENTS.md` (the full checklist). Talk about all of it in plain words (see `socratic-discovery`); never paste it at the person.

## 1. Is a new helper the right answer?

1. **No helper needed?** Would a checklist, a template or a better habit solve it?
2. **An existing helper?** Run `hermes profile list` and `python3 ~/Team-Workspace/Agents/bin/registry.py status`. Could a live helper take this on?
3. **One job?** If the need has two jobs, plan two helpers, or build the first job now.

Say the result plainly ("I think this is a new helper / an existing helper / not a helper job, because ..."). Let Robi disagree.

## 2. Readiness gate (do not write the brief until every line is true and confirmed)

- [ ] **The problem** and who has it
- [ ] **The workflow today**, step by step, and **where the helper enters** it
- [ ] **Who talks to the helper** and how it reaches them (user journey)
- [ ] **Who its work reaches** (customer journey) and which moments it must **not** touch
- [ ] **The tools and systems** the work uses, and whether the helper must read or change them
- [ ] **Where it lives**: a client's folder or its own team folder
- [ ] **What "done well" looks like** and how we will know it worked
- [ ] **What it must never do** and **what needs Robi's OK first**
- [ ] **A first test task** and at least one task it must refuse or ask about

If a line is not true, name the gap and ask the next question. Never fill a gap yourself.

## 3. Requirements to settle (plain question, a recommendation, Robi decides)

| # | Settle | Plain question | Default if unsure |
|---|---|---|---|
| 1 | **Job** | "In one sentence, what is its one job?" | must be answered |
| 2 | **Where it lives** | "Is this for one client, or a helper for the whole team?" | client folder if one client |
| 3 | **Name** | "What should we call it?" (the role only; the client name is added) | job-based, short |
| 4 | **How you reach it** | "Hermes app, Telegram, or another helper calling it?" | Hermes app |
| 5 | **AI brain** | "Routine work, or judgment and careful writing?" | routine: `claude-haiku-5-5`; judgment: `claude-sonnet-5-5` |
| 6 | **Built-in tools** | "Does it need to browse the web? Read and write files? Run commands? Create images? Speak?" | only what the job needs; the rest go in `toolsets_off` |
| 7 | **Outside tools** | "Does it need to use Jira, Notion, Drive or similar? Only read, or also change things?" | none; read-only first |
| 8 | **Skills** | "Does it need a special method, or just its instructions?" | none, lean |
| 9 | **Memory** | "Remember lots of facts over time, or only the chat?" | built-in notes |
| 10 | **Timer** | "Should it run on its own at set times?" | no (needs a separate OK) |
| 11 | **Passwords** | "Does it log in to anything?" | no (Robi stores any key himself, never in chat) |
| 12 | **Hand-offs** | "Does it answer only to you, or hand work to another helper?" | Robi |
| 13 | **Rules** | "What must it never do? What must it ask first? Any command that must always be blocked?" | ask first before sending, publishing, spending, deleting |
| 14 | **Tests** | "What is a first real task? What should it refuse?" | intro + normal + boundary |
| 15 | **Review** | "When should we look at how it is doing?" | after 3 tasks or 7 days |

Fixed by the house rules (do not ask): every agent is registered, starts as `testing`, gets a home folder with README, AGENTS.md and CHANGELOG, and is only promoted to `production` after Robi approves a correct real result.

## 4. The Agent Brief

Save to `~/Team-Workspace/Agents/briefs/<name>.md`. The top is plain words for Robi. The build spec at the bottom is for the scripts.

````markdown
# Agent brief: <plain name>

Status: DRAFT   (change to: APPROVED by Robi on YYYY-MM-DD, only after he says yes)
Date: YYYY-MM-DD

## In plain words
<5-8 short lines: the problem, who has it, what the helper will do, what it will not do, how we'll know it works>

## The problem
## The workflow today
<numbered steps, who does each, and where the helper enters>
## Who talks to it (user journey)
## Who its work reaches (customer journey)
## Tools and systems it touches
## What it does and what it must never do
- Does:
- Never:
- Asks Robi first before:
## How we will know it works
## Tests
<the intro, normal, edge, boundary, scope and tool tests, in words>
## Not known yet
## Why a helper (and not something simpler)

## Requirements check
| Requirement | Answer |
|---|---|
<the 15 rows above, answered>

## Build spec
(Simple format: `key: text` lines, and `- item` lines under list keys. No quoting rules.)
```build-spec
# client:<ClientFolder> works in that client's folder; team:<TeamFolder> gets its own team folder
placement: team:Example-Team
# the role only; for a client agent the client prefix is added automatically
name: example-helper
description: One paragraph saying what it does and for whom.
# claude-haiku-5-5 for routine work, claude-sonnet-5-5 for judgment and careful writing
model: claude-haiku-5-5
# lean = only the skills it needs (recommended); standard = all built-in skills
skills_mode: lean
# names from ~/Team-Workspace/Agents/skills, comma separated, or leave empty
skills:
# builtin or holographic
memory: builtin
# built-in toolsets it must NOT have: web, browser, image_gen, tts, code_execution, terminal, cronjob, delegation ...
toolsets_off:
  - image_gen
  - tts
# command patterns that are always blocked
block_commands:
intent: The goal in one or two sentences.
role: Who it is and what it is responsible for.
instructions:
  - one plain, direct rule per line
never:
  - ...
ask_first:
  - ...
context:
  - ...
examples:
  - Robi: '...' -> It replies: '...'
# outside tools: name | method (mcp, builtin or skill) | what it is for | read-only or can change | secret name only
connections:
# tests: kind | prompt | expect: words the answer should contain
tests:
  - normal | the first real task, in words | expect: key words
  - boundary | a request that must make it ask first | expect: ask, approval
```
````

## 5. Approval, build, verify

1. Show Robi the **"In plain words"** part, the limits and the readiness result. Ask: "Shall I build it as written?" Do not build on silence or a maybe.
2. After a clear yes set `Status: APPROVED by Robi on <date>` and run (from `~/Team-Workspace/Agents/bin/`):
   - `python3 create_agent.py ../briefs/<name>.md --dry-run`
   - `python3 create_agent.py ../briefs/<name>.md --approved --smoke`
   - `python3 check_agent.py <slug> --scenarios`
3. Change an existing helper: update the brief, get a new approval, `create_agent.py ... --update --approved` (backs up first). Retire: `create_agent.py --retire <slug> --approved`.
4. Report in plain words after each command. Follow `agent-lifecycle` for connecting tools, hand-over, first real use and review.
5. Never create timers, store passwords, connect outside tools, or message anyone without a separate, explicit OK.
