"""Offline connector regressions with the actual shared base and HTTP dependency."""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

import aiohttp


class CalendarTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        packages = {}
        for name in ('core', 'core.data_sources', 'core.data_sources.market_feeds'):
            package = types.ModuleType(name)
            package.__path__ = [str(root / name.replace('.', '/'))]
            packages[name] = package
        with patch.dict(sys.modules, packages):
            name = 'core.data_sources.fxmacrodata_calendar'
            spec = importlib.util.spec_from_file_location(name, root / 'core/data_sources/fxmacrodata_calendar.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.connector_type = module.FXMacroDataCalendarConnector
        self.connector = self.connector_type(
            api_key='fixture-key', session=AsyncMock(spec=aiohttp.ClientSession)
        )
        self.connector._make_request = AsyncMock()

    async def test_upstream_details_are_not_written_to_logs(self):
        self.connector._make_request.return_value = {'detail': 'fixture-private-value'}
        with self.assertLogs(self.connector.logger, level='ERROR') as logs:
            self.assertEqual([], await self.connector.get_calendar())
        self.assertNotIn('fixture-private-value', '\n'.join(logs.output))

    async def test_malformed_response_has_generic_diagnostic(self):
        self.connector._make_request.return_value = {'data': {}}
        with self.assertLogs(self.connector.logger, level='ERROR'):
            self.assertEqual([], await self.connector.get_calendar())

    async def test_valid_rows_and_tier_filter_are_preserved(self):
        rows = [{'name': 'first', 'market_tier': 1}, {'name': 'second', 'market_tier': 2},
                {'name': 'third', 'top_tier_for_currency': True}]
        self.connector._make_request.return_value = {'data': rows + [None]}
        self.assertEqual(rows, await self.connector.get_calendar())
        self.assertEqual([rows[0], rows[2]], await self.connector.get_calendar(top_tier_only=True))

    async def test_header_parameters_and_redirect_protection_are_preserved(self):
        self.connector._make_request.return_value = {'data': []}
        await self.connector.get_calendar('USD', '2026-01-01', '2026-01-31')
        args = self.connector._make_request.call_args
        self.assertEqual('GET', args.args[0])
        self.assertTrue(args.args[1].endswith('/calendar/usd'))
        self.assertEqual({'start_date': '2026-01-01', 'end_date': '2026-01-31'}, args.kwargs['params'])
        self.assertEqual('fixture-key', args.kwargs['headers']['X-API-Key'])
        self.assertFalse(args.kwargs['allow_redirects'])

    async def test_surrounding_key_whitespace_is_removed(self):
        connector = self.connector_type(api_key='  fixture-key\n')
        connector._make_request = AsyncMock(return_value={'data': []})
        await connector.get_calendar()
        self.assertEqual('fixture-key', connector._make_request.call_args.kwargs['headers']['X-API-Key'])

    async def test_embedded_key_whitespace_is_rejected_without_echo(self):
        with self.assertRaises(ValueError) as raised:
            self.connector_type(api_key='fixture-key\r\nX-Other: value')
        self.assertNotIn('fixture-key', str(raised.exception))

    async def test_missing_key_is_supported(self):
        with patch.dict(os.environ, {'FXMD_API_KEY': ''}):
            connector = self.connector_type()
        connector._make_request = AsyncMock(return_value={'data': []})
        await connector.get_calendar()
        self.assertNotIn('X-API-Key', connector._make_request.call_args.kwargs['headers'])

    async def test_no_response_keeps_existing_empty_result(self):
        self.connector._make_request.return_value = None
        self.assertEqual([], await self.connector.get_calendar())


if __name__ == '__main__':
    unittest.main()
