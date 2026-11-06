import unittest
from unittest.mock import AsyncMock, patch

from agent.approval_store import DbApprovalGate
from agent.coding_agent import CodingAgent
from agent.run_store import RunStore
from agent.runtime import build_coding_agent, build_coding_agent_from_engine
from agent.sqlalchemy_meta import SqlAlchemyMetaStore


class RuntimeCompositionTests(unittest.TestCase):
    def test_persistent_gate_and_run_store_share_the_same_meta_store(self):
        meta = object()
        agent = build_coding_agent(AsyncMock(), {}, meta)

        self.assertIsInstance(agent, CodingAgent)
        self.assertIsInstance(agent.gate, DbApprovalGate)
        self.assertIsInstance(agent.run_store, RunStore)
        self.assertIs(agent.gate.meta, meta)
        self.assertIs(agent.run_store.meta, meta)

    def test_engine_factory_uses_sqlalchemy_meta_adapter(self):
        engine = object()
        expected_meta = SqlAlchemyMetaStore(engine)
        with patch("agent.runtime.SqlAlchemyMetaStore", return_value=expected_meta), \
             patch("agent.runtime.build_coding_agent") as build:
            build_coding_agent_from_engine(AsyncMock(), {}, engine, max_steps=7)

        build.assert_called_once()
        args, kwargs = build.call_args
        self.assertIs(args[2], expected_meta)
        self.assertEqual(kwargs["max_steps"], 7)

    def test_persistent_agent_requires_project_id_before_model_call(self):
        from agent.coding_agent import CodingAgent
        from agent.run_store import RunStore

        chat = AsyncMock()
        meta = object()
        agent = CodingAgent(
            chat=chat,
            tools={},
            gate=DbApprovalGate(meta),
            run_store=RunStore(meta),
        )

        async def invoke_without_project():
            return await agent.run("Inspeccionar")

        with self.assertRaisesRegex(ValueError, "project_id es obligatorio"):
            import asyncio
            asyncio.run(invoke_without_project())
        chat.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
