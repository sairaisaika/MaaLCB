# 8 Agent Rules Layer

[中文](../zh_cn/8-agent-rules.md) · [← Index](index.md)

This chapter is about **what you must follow while working in this repository**, not about product behaviour. Its source files are `AGENTS.md` and the four rule documents under `docs/agents/`; this chapter reads them as one continuous line, but it does **not** replace them — `AGENTS.md` remains the entry point and those four files remain the operational source (`AGENTS.md:4`: `This file is the entry point for agents working in this repo.`).

## 8.1 Where the rules layer sits among the documents

This repository carries four kinds of prose, each with its own job and none replacing another: the **sources of truth** (`PROJECT.md` for progress and the development contract, `docs/design.md` for design constraints, `docs/acceptance.md` for the acceptance standard; `AGENTS.md:8-10` lists all three as required reading before touching code), the **narrative layer** (this wiki; `AGENTS.md:11` says outright that it does not replace those three), the **collaboration rules layer** (`AGENTS.md` plus the four files under `docs/agents/`, covering how to file tickets, how to label them, how to choose words, how to sediment conclusions), and the **out-of-repo conclusion store** (agentmemory, retrievable across sessions, see 8.5).

```mermaid
flowchart TD
  A["AGENTS.md (the index file, 29 lines)"] --> B["Read first: PROJECT.md / docs/design.md / docs/acceptance.md"]
  A --> C["docs/agents/issue-tracker.md (77 lines) tickets and specs"]
  A --> D["docs/agents/triage-labels.md (32 lines) five roles and five wayfinder labels"]
  A --> E["docs/agents/domain.md (59 lines) multi-context vocabulary and ADRs"]
  A --> F["docs/agents/memory.md (94 lines) writing conclusions back to agentmemory"]
  F --> G["agentmemory (outside the repository, project = MaaLimbus)"]
```

`AGENTS.md` is 29 lines long and every section under `## Agent skills` is a one-line pointer; the actual rule text lives entirely in those four files. That is deliberate: the entry file carries **dispatch**, not content.

## 8.2 Tickets and specs: GitHub Issues plus the deck tools

This repository's issues and specs are GitHub issues, on the remote `sairaisaika/MaaLCB` (`origin`, main branch `main`) (`docs/agents/issue-tracker.md:71-75`). Reading and writing **go through the plugin's own deck tools; you do not hand-type tracker commands** — the tools do the work against whatever the current backend is and read it back to check, so the same instructions hold when the backend is not GitHub (`docs/agents/issue-tracker.md:7-13`).

| What you want to do | Tool |
| --- | --- |
| Create a ticket | `deck_issue_create` |
| Read a ticket, with its comments and labels | `deck_issue_get` |
| See which maps and open tickets exist | `deck_context` |
| See one map's child tickets and progress | `deck_map_snapshot` |
| Create a whole map at once (map + children + edges) | `deck_map_plan_create` |
| Add one edge, parent or blocking | `deck_map_link` |
| Change a ticket (comment / labels / claim / close / body) | `deck_issue_patch` |

Only two things fall outside the tools, and both happen outside the tracker: **logging in** (`gh auth login`, then confirm with `gh auth status`) and **creating a repository** (`gh repo create`; the panel's create-and-publish wizard normally does it for you) (`docs/agents/issue-tracker.md:17-22`).

One general rule for writing a body: **write the body to a file first** (real newlines, each `## section` on its own line, one blank line between paragraphs), then hand the file to the tool; do not paste the body into a command line, do not write newlines as the two literal characters `\n`, and do not let the body start with a BOM — then read it back to check (`docs/agents/issue-tracker.md:26-30`).

Blocking relations are preferably laid down as the backend's own **native dependency edges**; only when that is genuinely unavailable do you fall back to a `Blocked by: #n` line at the top of the child ticket's body, with several numbers separated by commas — that line is the **fallback** shared by all three backends and must not become the default (`docs/agents/issue-tracker.md:34-36`).

## 8.3 Triage labels

The skills speak in terms of five **canonical roles**; on the tracker those become five label strings, and in this repository the right column matches the left (`docs/agents/triage-labels.md:5-11`):

| Role | Meaning |
| --- | --- |
| `needs-triage` | A maintainer needs to evaluate this issue |
| `needs-info` | Waiting on the reporter for more information |
| `ready-for-agent` | Fully specified, ready for an AFK agent |
| `ready-for-human` | Requires human implementation |
| `wontfix` | Will not be actioned |

`/wayfinder` uses one further label family with **no role mapping** — the label string is the type (`docs/agents/triage-labels.md:17-23`):

| Label | Meaning |
| --- | --- |
| `wayfinder:map` | The map issue; owns Notes / Decisions so far / Fog |
| `wayfinder:research` | Research ticket |
| `wayfinder:prototype` | Prototype ticket |
| `wayfinder:grilling` | Open decision or discussion ticket |
| `wayfinder:task` | Task ticket |

All ten (five roles plus five wayfinder labels) were created on the remote during initialisation; `bug` uses GitHub's own. **No label is otherwise mandatory unless a skill explicitly asks for it** (`docs/agents/triage-labels.md:29-31`).

## 8.4 Domain vocabulary: multi-context

This repository's domain-document layout is **multi-context**: one `CONTEXT.md` per subproject, with a `CONTEXT-MAP.md` at the repository root pointing at them; system-wide decisions go to `docs/adr/` and decisions belonging to a single context to `<subproject>/docs/adr/` (`docs/agents/domain.md:5-11`). This layout is the conclusion confirmed with the user during initialisation.

Before exploring, read: `CONTEXT-MAP.md` at the root if it exists, then the `CONTEXT.md` of the context you are about to touch, then the ADRs under `docs/adr/` that cover that area. **If these files do not exist, proceed silently** — do not flag the absence and do not propose creating them upfront; `/domain-modeling` creates them lazily when a term or decision is actually written down (`docs/agents/domain.md:19-25`).

Vocabulary has discipline: when your output names a domain concept (a ticket title, a refactor proposal, a hypothesis, a test name), use the definition in `CONTEXT.md` and do not drift to synonyms the glossary explicitly avoids. A concept you need but the glossary lacks is itself a signal — either you are inventing language the project does not use, or there is a real gap (`docs/agents/domain.md:51-55`). **Surface a conflict with an existing ADR explicitly** instead of silently overriding it (`docs/agents/domain.md:57-59`).

## 8.5 Sedimenting conclusions: writing back to agentmemory

This discipline governs exactly one thing: **once a session reaches a conclusion, write it into agentmemory outside the repository** (`docs/agents/memory.md:3`). It exists because of an observable gap: agentmemory is not short of raw session records, it is short of **conclusions** — searching `MaaLimbus` usually turns up tool_use shells (which file was read, which command was run) rather than how something was finally decided or which approach proved unworkable, so the next session steps into the same pit again (`docs/agents/memory.md:7-11`).

```mermaid
flowchart TD
  S["A session reaches a conclusion"] --> T{"Does it hit one of the three triggers?"}
  T -- "Feature landed and verified / an investigation concluded / a pit was fixed" --> W["Write once, at session wrap-up"]
  T -- "It is only intermediate process" --> N["Do not write: that is a session log"]
  W --> Q{"Kind of conclusion"}
  Q -- "Decision / insight / reusable pattern" --> M1["memory_save"]
  Q -- "Lesson learned" --> M2["memory_lesson_save"]
  Q -- "One-off raw observation" --> M3["memory_observe"]
  M1 --> R["Always set project to MaaLimbus"]
  M2 --> R
  M3 --> R
  R --> V["Read it back: memory_lesson_recall / memory_smart_search"]
```

Write **conclusions and criteria**, not a running log, and do not copy diffs: what was done (one sentence), why that way (including the rejected option and the reason), which approach proved unworkable (with the most characteristic error text or symptom), and the criteria / values / paths (acceptance standard, thresholds, version numbers, key file paths). A counter-example is read A, changed B, ran the tests; a good example is X does not work because Y (error text `...`), so switch to Z, and the criterion is command W printing P (`docs/agents/memory.md:33-50`).

`project` is always `MaaLimbus` — retrieval splits on this field, and leaving it blank or filling in the default workspace or an absolute repository path scatters this repository's conclusions into other projects, which is the same as not writing them. `concepts` / `files` / `tags` are comma-separated strings, not arrays. After writing, read back with `memory_lesson_recall` or `memory_smart_search` to confirm it is retrievable and `project` is right (`docs/agents/memory.md:62-69`).

It divides labour with `PROJECT.md` sharply: **`PROJECT.md` is the in-repo chronological ledger** (how far this round got, what comes next, which holes are still open) and **agentmemory is the out-of-repo conclusion store across sessions** (how this was decided last time, which approach does not work). **Do not copy one passage into both** — progress already written in PROJECT.md is not copied into agentmemory as body text, and a conclusion already in agentmemory is referenced from PROJECT.md by a one-line pointer only when a continuation needs it; when the conclusion already belongs to `docs/design.md`, `docs/acceptance.md` or `docs/agents/*.md`, one pointer line is enough (`docs/agents/memory.md:84-91`).

The non-applicable cases are stated too: a session that produced no conclusion (browsing, pure question and answer), and a conclusion that merely repeats what someone already wrote — in the latter case reinforce the existing memory instead, or simply do not write (`docs/agents/memory.md:92-94`).

## 8.6 How the rules layer is enforced

Separate responsibilities from execution evidence: **`AGENTS.md` provides the entry**, project rule files hold their conventions, and **the Wiki supplies verifiable locations, contracts and plans**. File existence does not prove tool invocation. Section8.7 records actual hook wiring and open acceptance. External issue/memory tool availability and execution need separate observations; pointers cannot establish that all three mechanisms are running.

This layering also explains why `.gitignore:28-29` lets only two files through: the rules layer is by default **local configuration**, and only the part that must travel across sessions and between people ships with the repository — `!docs/agents/memory.md` and `!AGENTS.md` are exactly those two exceptions.

## Not verified / open questions

This section states honestly how far this chapter was verified and what was **not**.

1. **This chapter performed no ticket operation.** The tool list and the fallback in 8.2 are taken from the text of `docs/agents/issue-tracker.md`; this chapter neither created a ticket nor verified what the `deck_*` tools report on the current backend. The authority on the tool contract is the plugin, not this chapter.

2. **The label list is a snapshot.** The ten labels in 8.3 come from the current-state paragraph at `docs/agents/triage-labels.md:29-31`; this chapter did not query the remote repository to re-check that they still exist today.

3. **multi-context is the agreed layout, not a measured state.** 8.4 states the conclusion confirmed with the user during initialisation: these files were absent at initialisation. The current root `CONTEXT-MAP.md`, domain `CONTEXT.md` files and `docs/adr/0001-runtime-convergence.md` exist. That old absence is not current evidence; read the relevant domain context for the task.

4. **The line counts are measurements from the time of writing.** The figures 29 / 77 / 32 / 59 / 94 in the 8.1 diagram (`AGENTS.md` and the four rule files) and `docs/wiki/README.md:72` were measured on 2026-10-12 (America/Indianapolis); re-measure before quoting.

5. **The `.gitignore` exceptions state an intent, not an index.** Those two lines at `.gitignore:28-29` decide which files of the rules layer travel with the repository; this chapter only explains that design and does not claim what the git index currently holds — whether `AGENTS.md` has been `git add`ed is unrelated to this chapter's account.

6. **The two languages were not compared sentence by sentence.** Only headings, numbering, tables and paragraph order are guaranteed to correspond; `../zh_cn/8-agent-rules.md` is the source and this page is its mirror rather than an independent write, so a factual error in the Chinese page is inherited here.


Added session rule: AGENTS.md Memory points to `docs/agents/memory.md`. Save only evidence-backed conclusions under agentmemory project MaaLimbus at session close and read them back. Check memory_save / memory_lesson_save availability before calling. When unavailable, preserve conclusions in PROJECT.md and state that external writeback remains incomplete; repository documents and local logs are not external-memory writes.


<a id="project-wiki-hooks"></a>
## 8.7 project-wiki hook integration

Use the host-exposed **project-wiki** as the sole generic guide. The retired `multi-agent-wiki` guide is a redirect; its old script forwards to the project-owned `tools/wiki_router.py`. `tools/wiki_route.py` no longer depends on a skill directory. Bilingual mirrors and schema-1 routes remain MaaLimbus responsibilities. The actual installed version is0.2.17, distinct from upstream0.2.39; this change neither overwrites plugin caches nor migrates schemas.

The plugin already supplied a SessionStart hook, but this host process has no `PROJECT_WIKI_PACKET`, so its documented behavior was a quiet opt-out. An optional local `.codex/hooks.json` uses a thin adapter to select a current task explicitly, then delegate saved-index reading to the installed `lifecycle.deliver`. It does not implement a second Wiki reader or run games, tests, maintenance or commands quoted in task data.

| Boundary | Producer → consumer | Fields and failure semantics |
| --- | --- | --- |
| Task routing | `wiki_context.native_context` → upstream `workflow.capture/start` | query, cards, all planned-file owners, unregistered, omitted; top-two query hits are not a complete impact inventory |
| Explicit selection | `wiki_session.prepare` → `wiki_hook.selection` | root, packet, packet SHA, provider version, lifecycle/workflow SHA; verify actual index delivery before atomic publication, not just a nonempty warning |
| Saved delivery | Normally trusted SessionStart → `wiki_hook.deliver` → upstream reader | startup/resume/clear/compact/fork; saved-only reading, no Git refresh, live source check or packet-command execution |
| Semantic use | Agent receiving context → current source and relevant Wiki sections | Open the contract and verify symbols; injection alone proves neither reading nor correct use |
| Delivery reconciliation | Actual diff → original routes and semantic/evidence review | Record structure, source, packaged and whole-run verification separately |

```mermaid
sequenceDiagram
  participant C as Coordinator
  participant N as Project router
  participant W as Installed project-wiki workflow
  participant S as Private selected packet
  participant H as Trusted host SessionStart
  C->>W: Explicit capture and start
  W->>N: Reviewed argv and planned files
  N-->>W: All declared owners and unknowns
  W->>S: Saved task and hashes
  C->>S: Select after real index delivery replay
  H->>W: Bridge invokes saved-only deliver
  W-->>H: Task context or delivery warning
  Note over W,H: Context delivery is not source or game acceptance
```

Actual entrypoints:

```powershell
python tools/wiki_session.py prepare --provider-version 0.2.17 --query wiki-hook-integration --files tools/wiki_hook.py tools/wiki_session.py --task-id wiki-hooks --outcome "Wire Wiki task delivery" --acceptance "Declared owners and no device input" --capability "saved-only delivery"
python tools/wiki_session.py status
python tools/wiki_session.py replay --source resume
```

Task contents and hashes stay in ignored `build/wiki` and `.codex/wiki-selection.json`. Absent selection is a quiet opt-out; missing, changed, escaping, nested-checkout or version-mismatched data produces a delivery warning. Failed preparation preserves the previous selection. Keep the provider's size limit: use a short current-phase task rather than truncate owners and pretend delivery succeeded. Screenshots, account details and full transcripts do not enter the public Wiki. An identical ambient `PROJECT_WIKI_PACKET` uses the original plugin without duplicate project injection; conflicting selections need explicit reconciliation.

On2026-11-18 the project's host trust record was observed after the user's normal Hooks review. Direct replay through the actual installed saved reader also passed. Actual host SessionStart execution and context delivery remain unobserved; replay is not a host event. Verify a normal later startup/resume/compact through the existing definition. Never manufacture trusted hashes or substitute an existing plugin's trust for review of a new definition.

### Unverified / open items

SessionStart delivers context only. The current plugin's Codex profile does not contain its Claude-only pre-edit gate; without local evidence, PreToolUse/Stop execution is unverified. Same-event handlers may run concurrently, so hook ordering cannot serialize maintenance and tests. Host invocation, actual agent use and whole-Mirror acceptance remain separate open items.

<a id="wiki-work-protocol"></a>
## 8.8 Wiki-driven convergence work

Use the [dictionary](1-overview.md#glossary), [unique responsibilities](2-architecture.md#feature-2-6), [formal runtime](3-runtime.md#feature-3-10) and [delivery table](9-execution-plan.md#runtime-migration), rather than another parallel architecture proposal. Verify the actual producers, consumers, units, pending state and counterexamples before selecting a slice; proposed types stay explicitly unimplemented. Preserve historical source, self-test, replay and live results as feasibility evidence. This effort needs fresh official-install acceptance from login through completion of the current Mirror run.

One coordinator schedules **maintenance/editing → tests → build/install → live** serially in a shared workspace. Stop editing source during tests. Live operation uses the frozen installation; continue read-only analysis without replacing dist. Device exclusivity does not serialize engineering operations; a test parent must not hold a controller lock that makes its own child probes fail. This defines scheduling responsibility, not a claim that SessionStart implements an interprocess scheduler. See [7.4](7-quality.md#feature-7-4) for evidence requirements.

Refresh task selection for the current phase. Upstream `workflow.py show --snapshot-only` displays saved data only. The coordinator checks current inputs at execution and actual-diff return boundaries, using the installed version's `capture-return`/`review-template`/`finish` interfaces. Do not document commands from another version as locally available. Include unplanned files in actual-diff review rather than intersecting changes with the original plan.

Classify upstream findings as project integration, installed-version/host differences, or a genuinely missing generic capability. Absent selection, stale project entry, schema adaptation and the project's overflow interpretation belong to this integration. Upstream already covers snapshot-only reading, complete impacts, six views, producers/consumers, design review and actual-diff return; duplicating those is not an improvement. Open a projectWikiSkill PR only for a reproducible unaddressed generic gap, and leave it unmerged for the user's audit.

## 8.9 Selecting game-automation development tools

This pass reviewed sources only; it installed nothing and started no second controller. The [MaaFramework ecosystem list](https://github.com/MaaXYZ/MaaFramework/blob/main/README_en.md#ai-assisted-development) links these community projects. Listing is not official distribution or MaaLimbus acceptance.

| Candidate | Project use | Adoption boundary |
| --- | --- | --- |
| [maaframework-skills](https://github.com/Kutius/maaframework-skills) | Lightweight Pipeline, recognition, PI V2 and Agent callback reference | Self-described v5.x snapshot generated2026-04-16; verify implementation against this project's pinned5.12.2 protocol |
| [Everything-Maa](https://github.com/KhazixW2/Everything-Maa) | Evaluate workflow-build, pipeline-option and pipeline-testing for option-to-production-entry and end-to-end review | README provides Codex and skills-only targets; default core also configures MCP. Do not substitute a default full install for the existing entry. No project execution or acceptance yet |
| [MaaEvidenceKit](https://github.com/Windsland52/MaaEvidenceKit) | Read-only native node/task/log locations for diagnosis | It does not own root-cause conclusions, automatic repair or business completion. Validate compressed-report/privacy/capacity behavior and5.12.2 log compatibility before integration |

project-wiki owns project responsibility, planning and evidence navigation; Maa-specific skills supply protocol/tool details, not another competing project fact store. Preserve the existing Maa Controller/Context input path, frozen versions, one controller and the whole-project2GB limit. A tool's testing or AI name does not establish knowledge of Limbus pages, model quality or current pending transactions.
