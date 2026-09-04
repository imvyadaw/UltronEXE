# ULTRON Advanced Autonomy Fabric

## Purpose

This layer makes ULTRON's existing subsystems behave like one bounded
autonomous lifecycle instead of isolated features.

`OBSERVE -> MODEL -> MISSION -> RESEARCH -> ACT -> VERIFY -> LEARN`

## Integrated capabilities

- World-state snapshots
- Persistent missions and checkpoints
- Multi-source web research
- Source-tagged Knowledge OS storage
- Experience/outcome learning
- Learned strategy confidence
- Sandbox-first self-evolution evaluation
- Explicit non-deployment boundary for code evolution

## Safety boundaries

The fabric does not create a new OS/network execution bypass. Actions must
continue through ULTRON's existing capability registry and permission/action
pipeline. Evolution is evaluated in a temporary sandbox and is never
automatically deployed to production.

## Configuration

`ULTRON_ADVANCED_AUTONOMY_ENABLED=true` is the default. Set it to `false` to
disable the composition layer without removing the underlying subsystems.

The persistent event/strategy store is `database/advanced_autonomy.db`.
