"""Exercise the local read-only tools through the actual MCP stdio protocol."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from brochure.tracing import TraceStore, research_trace

ROOT = Path(__file__).resolve().parents[1]


class TraceToolTests(unittest.TestCase):
    def test_stdio_lists_reads_compares_without_mutating_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store = TraceStore(directory / 'traces.sqlite3')
            identifier = 'a' * 32
            with research_trace(store, identifier, 'operator-test', 'research'):
                pass
            before = (directory / 'traces.sqlite3').read_bytes()

            async def exercise():
                params = StdioServerParameters(command=sys.executable,
                    args=[str(ROOT / 'scripts/trace_mcp.py'), '--data-dir', str(directory)],
                    env={'LANGSMITH_TRACING': 'false'})
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = (await session.list_tools()).tools
                        names = {tool.name for tool in tools}
                        self.assertEqual(names, {'list_research_runs', 'get_research_run',
                                                 'get_research_call', 'compare_research_runs'})
                        self.assertTrue(all(tool.annotations.readOnlyHint for tool in tools))
                        result = await session.call_tool('list_research_runs', {'limit': 5})
                        self.assertFalse(result.isError)
                        self.assertEqual(json.loads(result.content[0].text)['runs'][0]['id'], identifier)
                        result = await session.call_tool('get_research_run', {'run_id': identifier})
                        self.assertFalse(result.isError)
                        self.assertEqual(json.loads(result.content[0].text)['status'], 'completed')
                        result = await session.call_tool('compare_research_runs', {
                            'first_run_id': identifier, 'second_run_id': identifier})
                        self.assertFalse(result.isError)
                        self.assertEqual(json.loads(result.content[0].text)['stages'], [])
                        result = await session.call_tool('get_research_run', {'run_id': '../auth.sqlite3'})
                        self.assertTrue(result.isError)

            asyncio.run(exercise())
            self.assertEqual((directory / 'traces.sqlite3').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
