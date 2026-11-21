# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## 本仓库的布局（初始化时与用户确认的结论）

**multi-context** —— 每个子项目各一份 `CONTEXT.md`，仓库根目录一份 `CONTEXT-MAP.md` 指向它们。

- 2026-11-17 已在明确采用运行时架构、统一词典后创建 `CONTEXT-MAP.md` 与 runtime/native/desktop 三个薄上下文入口。规范定义唯一来源为 Wiki1.2；CONTEXT.md 仅说明职责并链接词典，不平行重定义。
- 系统级决定放 `docs/adr/`，与单个上下文有关的决定放 `<子项目>/docs/adr/`。

## Before exploring, read these

- **`CONTEXT-MAP.md`** at the repo root if it exists — it points at one `CONTEXT.md` per context. Read each one relevant to the topic.
- **`CONTEXT.md`** for the context you are about to touch (in a multi-context repo every `CONTEXT.md` lives beside its subproject, not at the repo root).
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. In multi-context repos, also check `<subproject>/docs/adr/` for context-scoped decisions.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Multi-context repo (presence of `CONTEXT-MAP.md` at the root) — 本仓库采用这一种：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

Single-context repo (most repos) — 本仓库不是这一种：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
