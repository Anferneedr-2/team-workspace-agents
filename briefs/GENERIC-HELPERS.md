# Generic helpers index (the repository list)

Status: DRAFT

## What this list is
The repository is the set of helpers with a job and a method and no client data. A project gets a COPY (new brief, built with create_agent.py), and the copy learns that project's data in its own memory. Generic helpers change only when the employee approves. Client data never moves between teams.

This file is only an index. Nothing is marked "generic" in the registry yet, and no script copies a helper into a project. Every helper and folder stays where it is.

## Generic roles (copy these into a project when needed)
Brief file = the source to copy from (in this folder). "Lives in" = where the live helper works today.

| Helper | One-line job | Brief | Lives in | Note |
|---|---|---|---|---|
| team-lead | Splits a request into task files, one owner each, keeps the handover log, reports to the employee | team-lead.md | team-work | Built as a practice member (placement team:team-work). Copy keeps the job, changes the placement |
| short-text-writer | Writes short drafts from a written task; asks when something is missing | short-text-writer.md | team-work | Same note as team-lead |
| reviewer | Checks a draft against its task and definition of done; PASS or RETURNED; never rewrites | reviewer.md | team-work | Same note as team-lead |
| memory-manager | Keeps the project notes (context, decisions, glossary) with source and date; answers only from them | memory-manager.md | Generic-Helpers | Recommended default for company projects |
| document-engineer | Keeps README, CHANGELOG and a Deliverables index with approval status; never edits AGENTS.md | document-engineer.md | Generic-Helpers | Recommended default for company projects |
| project-manager | Sets up and tracks projects, writes status and management reports | project-manager.md | Project-Management | Brief mentions the agency; check for client data before copying |
| hr-assistant | HR support: screening, interviews, onboarding, policy answers | hr-assistant.md | HR | Brief says not tied to any client |
| accounting-assistant | Reviews expenses and invoices, summaries, reconciliation support, from supplied documents | accounting-assistant.md | Accounting | Prepares and flags only |
| account-manager | Tracks what each client bought, promised, is open, renewals; meeting and renewal briefs | account-manager.md | Account-Management | Holds per-client records: check before any copy |
| sales-agent | Lead qualification, call prep, follow-ups, pipeline review drafts | sales-agent.md | Sales | Brief says not tied to any client |
| chief-marketing-officer | Writes marketing documents after a short question round, scores its own work | chief-marketing-officer.md | CMO | Not tied to any client |
| client-onboarding | Collects what each client already has into a per-client folder others can trust | client-onboarding.md | Client-Onboarding | Per-client records stay in its own folder, never copied |

## Default set for every new client
team-lead (also the orchestrator: one helper, not two), memory-manager and document-engineer. The multi-agent-engineer copies them into each client when that client is set up, each after a plan and your yes. Existing clients (example-client, example-client, example-client, example-client) have none yet; adding them is paused.

## Builders (not copied into projects)
- agent-creator (Agents): builds single helpers and owns the repository.
- multi-agent-engineer (Multi-Agent-Engineer): builds and sets up a team from the repository.

## Project-specific (stay in their project, not in the repository)
- example-client-invoice-maker (example-client): example-client-only job; the employee decided there is no generic invoice maker.
- example-client-deck-builder (example-client).
- Project-specific helper entries must include no client names and remain in their own project folder.

## Retired
- cmo (replaced by chief-marketing-officer).

## Not yet following the requirements (left alone)
clone-remix-orchestrator, clone-site-bot, remix-site-bot, wedworks-chat.

## Open points
- No registry field or script marks a helper as generic. Request for the employee to arrange.
- No approved script adds a new project (client) to the registry, or copies a generic helper into a project.
- Moving clickup-manager to the example-client folder would need a new brief, a build and a retire, each with the employee's yes.
- Before any helper here is copied, the engineer checks its brief for client data and asks the employee.
