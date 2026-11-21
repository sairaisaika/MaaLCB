# ADR-0001: One observation–action–transition contract

Status: **Accepted design; implementation migrating**, 2026-11-17. The user explicitly requested adoption into formal Wiki chapters rather than another architecture proposal.

## Context / 背景

Observed failures include foreground/background ownership conflicts, repeated geometry filtering, pending created before dispatch, multiple successor interpretations and evidence exhaustion after an input. Existing domain transactions and actual shop/floor proof work and must be preserved. Historical5c75618/8cfdba5 measurements (runner8749lines, step3081, candidates_of566; map_vision3290lines/97functions) locate coupling; they are not quality or current size claims.

## Decision / 决定

Keep Maa Controller/Resource/Tasker/Pipeline, PI V2, MXU and the Python Agent. Adopt one in-process ownership chain: LaunchSpec → Observation/RunState → domain policy → ActionProposal → ActionExecutor → TransitionJudge → verified business reduction. EvidenceStore and learning records reference the same immutable evidence. Adopt accepted/rejected/unjudged; preserve uncertain dispatch and pending scope. Reserve evidence capacity before physical input under the whole-project2000000000-byte limit. Migrate chain by chain and remove competing legacy owners; do not big-bang rewrite or create distributed services.

The canonical dictionary is [Wiki1.2](../wiki/zh_cn/1-overview.md#glossary). Authoritative architecture/runtime/business/data/deployment/quality contracts now reside in chapters2.6/3.10/4.19/5.6/6.8/7.4. The former2.4 URL is a navigation index, not a second specification. [Wiki9.4.6](../wiki/zh_cn/9-execution-plan.md#runtime-migration) tracks actual deliveries and remaining work.

## Alternatives and consequences / 取舍

Reject continued per-page exception layering and splitting runner files without changing ownership. Reject a big-bang rewrite that loses proven transactions. Reject allowing an unvalidated model to authorize spending or label its own predictions as independent truth. Shared capabilities reduce duplicate recovery, but need explicit legacy adapters, retained-frame negatives and native whole-chain acceptance. No additional locks, approvals or permission gates are introduced by the documentation.

## Evidence boundary / 实施边界

The map page-verdict slice and bounded HUD retention exist in0af685f. Geometry unification, shared data types, general executor, single-copy evidence storage and pre-dispatch capacity reservation remain incomplete. At08:12UTC the actual continuous packaged run ended on evidence capacity in floor2 battle. This decision does not claim full Mirror, GUI Start, cross-task completion or production neural quality.


2026-11-17 offline contract migration: runtime_contracts.TransitionVerdict now owns the three canonical verdict values and validates immutable successor contracts/reasons. MapTransition is a compatibility alias and the production map judge uses this record; no second verdict owner or broader successor table added.50 related tests passed. This source is not installed/live verified. MuMu is reserved by the user for another game: no device connection, controller or native input during migration; retained-frame validation only.


Contract-migration verification:65 Wiki/contract checks passed in37.72s; the broader related map/retention selection passed50 checks in5.61s. Retained native MAP→NODE_PANEL JSON/PNG hashes verified, four synthetic obscuration controls preserved original pending,31actual private configuration files unchanged,zero controller/input.48routes resolve current symbols. These are offline source/document checks, not new live/GUI/full-run acceptance; full-suite failures remain separately recorded.

Capacity migration update: source now implements a physically sized EvidenceCapacity pool, dual fixed-size metadata slots, native Journal byte consumption and terminal release in the Mirror Agent. Main plans admit before domain intent and direct inputs recheck before native dispatch.16tests and isolated retained Journal replay passed; no device input or installation. Composite child-node/other-task/CLI/full-run coverage remains open.
