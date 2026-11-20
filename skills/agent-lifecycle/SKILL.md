---
name: agent-lifecycle
description: "Use for the whole journey of a new helper, from first question to a tested, connected, documented helper that Robi is using correctly: 10 stages with exit criteria, plain-language scripts, test plan, hand-over card and review loop."
version: 1.0.0
---

# Agent lifecycle (end to end)

The ideal outcome: Robi says "I need a helper for X" and ends with a helper that is **understood, built correctly, connected to the tools it needs, tested, documented, used correctly, and reviewed**. You own that whole outcome. A helper that was only "created" is not finished.

Always tell Robi where you are in one short line: **"Step 3 of 10: writing the plan."** Never skip a stage. Never say "done" for a stage until its exit check is true.

Rules for how things are organized are in `~/Team-Workspace/Agents/CONVENTIONS.md`. Hermes facts are in the `hermes-reference` skill.

## The 10 stages

| # | Stage | You do | Exit check (all true) |
|---|---|---|---|
| 1 | **Discover** | Interview (socratic-discovery), map workflow, user journey and customer journey | Readiness gate in `agent-requirements` is true and Robi said "yes, that's right" to the teach-back |
| 2 | **Shape** | Decide fit (no helper / existing / new), one job, placement, name, tools, memory, model, limits, how it is reached | every row of the requirements table has an answer or a named Unknown |
| 3 | **Brief and approval** | Write the Agent Brief with tests; show the plain-words part | Robi said a clear yes to "Shall I build it as written?" and Status is APPROVED |
| 4 | **Pre-build check** | `hermes status`; gateway running; model works; name free; placement valid; secrets plan; dry run | dry run prints the plan with no STOP |
| 5 | **Build** | `create_agent.py --approved --smoke` | script says BUILT; smoke answer is sensible and exit 0 |
| 6 | **Connect tools and reach** | Only what the brief lists: outside tools, and a Telegram bot if it will be reached there (below) | each connection passes `mcp test` and one harmless read; Telegram shows connected and has answered a hello |
| 7 | **Verify** | `check_agent.py <slug> --scenarios`; explain results plainly; fix and re-run | no FAIL; every REVIEW read with Robi |
| 8 | **Hand over** | Give the "How to use your helper" card | Robi can say how to ask it, what it asks first, where its work lands |
| 9 | **First real use** | Sit through one real task with Robi | Robi says the result was right (then `registry.py set-status <slug> production --approved`) |
| 10 | **Review** | After three real tasks or seven days, then monthly | review recorded; decision: keep, change or retire |

## Stage notes

**2 Shape.** Ask about: *where it lives* (a client's folder, or its own team folder), *what tools it needs* (plain questions: browse the web? read and write files? run commands on the computer? create images? work on a timer? talk to other helpers? use an outside tool such as Jira, Notion, Drive?), *how Robi will reach it* (Hermes app, terminal, Telegram, another helper), *how strict the fence must be* (on this Mac a folder limit is a rule it follows, not a wall; say so plainly). Choose the lean setup: only the toolsets and skills the job needs (`toolsets_off`, `skills_mode: lean`).

**3 Brief.** Put real tests in the build spec `tests:` (see below). Show only "In plain words" and the limits to Robi, not the technical block.

**4 Pre-build.** Run `hermes -p agent-creator status`, `python3 ~/Team-Workspace/Agents/bin/registry.py status`, then the dry run. If the gateway is not running or the name is taken, stop and say so.

**5 Build.** Run the dry run, then the real build. Report in plain words: where it lives, what it is called, what it can and cannot do, and that it starts as **testing**.

**6 Connect tools and reach.** If the brief's `reach` includes Telegram (needs Robi's OK): this agent needs its own bot. Tell Robi, in plain words: (1) easiest, open the Hermes app, Messaging, Telegram, choose this helper and use "Create with QR", which does everything and restarts the gateway; or (2) make a bot with @BotFather and run `hermes -p <slug> gateway setup`. He, not you, handles the token and gives the numeric user ID to the setup. Before any gateway restart check that no task is running. Then run `check_agent.py <slug>`: it must show Telegram connected; then Robi confirms with `/whoami` in the chat that only his own account has access. If Robi sends voice notes (ask in the interview), make sure speech to text works first (`hermes-reference`, Voice notes). Finally ask Robi to send the bot "hello" and a short voice note from his phone and confirm it answers in short, plain messages. Use the `hermes-reference` failure list if not.

**Outside tools** (needs Robi's separate OK for each connection):
1. Choose the method: a built-in toolset, an MCP server, or a skill with its own key.
2. Secrets: Robi stores the key himself in that helper's `.env` (permissions 600) or the Mac Keychain. You never see it, never type it, never put it in a file. Tell him the exact place, in plain words.
3. Add the connection to that helper's `config.yaml` (`mcp_servers`, include only the tools the job needs, read-only first, secrets as `${VAR}`), or let Robi run `hermes -p <slug> mcp add`.
4. Verify: `hermes -p <slug> mcp list`, `hermes -p <slug> mcp test <server>`, then ask the helper for one harmless read and check it. If it fails, use the failure table in `hermes-reference`.
5. Record the connection in the brief and write a CHANGELOG line.

**7 Verify.** Run `check_agent.py <slug> --scenarios`. Explain the result without jargon: what passed, what needs fixing, what Robi must read. Fixes to instructions go through an updated, re-approved brief and `create_agent.py --update` (it backs up first). Re-run until there is no FAIL. The report is saved as `briefs/<slug>-test-report.md`.

Write tests in the brief like this (kind | prompt | expect: words it should use):
- `intro` — it states its job and its folder.
- `normal` — the first test task from the user journey, in test mode.
- `edge` — an unusual but realistic request from the workflow's exceptions.
- `boundary` — a request that must make it ask first or refuse (sending to a client, deleting, spending).
- `scope` — a request to look at another client's files (client agents).
- `tool` — one harmless read through each connected tool.
Test runs are always "test mode": nothing is sent, published, deleted, spent or changed outside its Work folder.

**8 Hand-over card** (plain words, give it to Robi and save it in the helper's folder as `Work/how-to-use.md`):
- **What it is for** (one sentence) and **what it will never do**.
- **Where to find it**: the Hermes app under Bots, or `hermes -p <slug> --in <folder> -z "<request>"`.
- **How to ask**: three example requests taken from the user journey.
- **What it will ask you first** before acting.
- **Where its work lands**: drafts in `Work/`, approved files in `Deliverables/`.
- **How to correct it**: say what was wrong; it saves lasting lessons to its memory. Bigger changes go through `agent-creator`.
- **How to check on it**: the test report, and `hermes sessions list` for what it has done.
- **When we review it**: the date.

**9 First real use.** Ask Robi for one real task. Stay with it. Afterwards ask: "Was that the result you wanted? What surprised you?" Only a clear yes allows promotion. A "mostly" means go back to stage 7 or 5 with a change.

**10 Review.** Ask: What worked? What annoyed you? What did it get wrong? What should it never do that it did? What is it missing? With Robi's permission look at `hermes sessions list` and `hermes logs errors --since 7d` for this helper. Change what is needed through an updated brief. Record it with `registry.py review <slug>`. Decide: keep as is, change, or retire (`create_agent.py --retire <slug> --approved`, which keeps the brief and registry row).

## When something fails

Say plainly what failed and what it means for Robi, name the likely cause (use the failure table in `hermes-reference`), propose one fix, and ask before applying anything that changes a helper. Never hide a failure, never mark a stage done because it "mostly works", never claim a helper works without a `check_agent.py` run that has no FAIL.

## Never

- Skip the interview or the approval, or build because Robi is in a hurry.
- See, type, store or log a password or key.
- Create timers, connect outside tools, or message anyone without a separate, explicit OK.
- Edit another helper's instructions, delete a helper, or promote one to `production` without Robi's clear yes.
