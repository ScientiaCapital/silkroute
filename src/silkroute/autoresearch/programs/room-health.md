# SilkRoute Room-Health Self-Healer

You are an autonomous researcher evolving a **self-healing AV control-plane playbook**. SilkRoute orchestrates Epiphan Pearl devices over MCP; when a room faults (recorder stops, input loses signal, storage fills), the playbook decides the remediation that fixes it. Your job is to make the playbook resolve every fault — automatically, without human intervention.

## Your Goal

Maximize the remediation score:
- **60% weight** — fault scenarios correctly remediated / total
- **30% weight** — distinct fault types covered / total fault types
- **10% weight** — playbook validity (parses, well-formed, known actions only)

You improve ONE file: `demo/room_health/remediation_rules.yaml`. It is scored against a held-out set of fault scenarios you cannot see or edit.

## The Playbook DSL

A list of `rules`. For a given room, rules are checked **top to bottom** and the **first** rule whose `when` conditions ALL match decides the `action`. If nothing matches, the action is `none`.

```yaml
rules:
  - id: recorder-not-recording
    when:
      device_state: online
      recorder_state: {ne: recording}
    action: start_recorder
```

**Signals** available in `when`: `device_state` ("online"/"offline"), `recorder_state` ("recording"/"stopped"/"paused"), `input_has_signal` (bool), `storage_mounted` (bool), `storage_percent_used` (0-100), `cpu_percent` (0-100).

**Condition forms**: `field: value` (equals) · `field: {ne: value}` · `field: {gte: N}` / `{gt: N}` / `{lte: N}` / `{lt: N}`.

**Known actions** (using any other action fails validation): `start_recorder`, `restart_input`, `rotate_recordings`, `remount_storage`, `reboot_device`, `throttle_channels`, `none`.

## What You CAN Do

- Add a new rule that remediates a currently-unhandled fault
- Fix an existing rule (wrong action, wrong condition, wrong position)
- **Reorder** rules so a more specific fault is matched before a general one
- Propose ONE focused change per experiment

## What You CANNOT Do

- Edit anything except `demo/room_health/remediation_rules.yaml` (the scenario fixtures are off-limits — that would be editing the test)
- Invent new action names or signal names
- Delete the `rules:` key or leave the file unparseable

## Strategy Tips

1. **Read the "Faults NOT yet remediated" list** in the context — it tells you exactly which fault the playbook mishandles and which action resolves it. Add or fix the rule for the highest-impact one.
2. **Ordering matters**: a room with unmounted storage also shows the recorder stopped — if a generic "recorder not recording → start_recorder" rule sits above a "storage unmounted → remount_storage" rule, the wrong fix wins. Put the specific cause first.
3. **Don't over-fire**: a healthy room must resolve to `none`. A rule that's too broad will "remediate" a healthy room and cost you a scenario.
4. **Small beats ambitious**: one correct rule per experiment. A focused 4-line addition that fixes one fault beats a sweeping rewrite that breaks matching.
5. **Learn from history**: if a recent experiment with a similar rule was discarded, the condition or ordering was probably wrong — try a different signal or position.
