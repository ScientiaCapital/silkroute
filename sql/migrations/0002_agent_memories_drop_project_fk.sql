-- Migration 0002: drop the FK on agent_memories.project_id
--
-- Bug found while wiring AutoResearch into agent_memories: the FK to
-- projects(id) meant any ad-hoc project label (AutoResearch's --project,
-- or `silkroute run --project foo` for an unregistered foo) silently
-- failed to save memories. project_id is meant to be a free-form scope
-- label (NULL already means "global") — it never needed to reference a
-- real, budget-governed project row.

ALTER TABLE agent_memories DROP CONSTRAINT IF EXISTS agent_memories_project_id_fkey;
