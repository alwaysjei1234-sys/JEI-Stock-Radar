"""HTTP 200 alone cannot certify a successful MIS application response."""
import json
import unittest
from unittest.mock import MagicMock, patch
from scripts import update_system as u


class MisResponseStatusTests(unittest.TestCase):
    def fetch(self, payload):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with patch.object(u.urllib.request, 'urlopen', return_value=response):
            return u.fetch_mis_channels(['tse_2330.tw'])

    def test_error_status_cannot_supply_even_well_formed_quotes(self):
        quote = dict(c='2330', ex='tse', ch='2330.tw', d='20261105',
                     t='10:00:00', z='100', y='99', v='10')
        with self.assertRaises(ValueError):
            self.fetch({'rtcode': '5000', 'msgArray': [quote]})

    def test_missing_or_wrong_type_status_is_not_success(self):
        for status in (None, 0, True, '', '0'):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.fetch({'rtcode': status, 'msgArray': []})

    def test_invalid_envelopes_are_rejected(self):
        for payload in ([], None, {'rtcode': '0000'},
                        {'rtcode': '0000', 'msgArray': {}},
                        {'rtcode': '0000', 'msgArray': None}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.fetch(payload)

    def test_successful_array_is_passed_to_existing_quote_gates(self):
        quotes = [{'c': '2330'}, None]
        self.assertEqual(self.fetch({'rtcode': '0000', 'msgArray': quotes}), quotes)

    def test_successful_empty_array_keeps_existing_retry_path(self):
        self.assertEqual(self.fetch({'rtcode': '0000', 'msgArray': []}), [])

    def test_empty_request_does_not_access_network(self):
        with patch.object(u.urllib.request, 'urlopen') as request:
            self.assertEqual(u.fetch_mis_channels([]), [])
            request.assert_not_called()
