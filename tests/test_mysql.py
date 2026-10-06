"""Runs only against an explicitly configured disposable integration database."""
import os
import unittest
from database import connect
from pipeline import ROOT, demo, load, response_curve, responses


@unittest.skipUnless(os.environ.get('MYSQL_INTEGRATION_TEST') == '1', 'MySQL integration database not enabled')
class MySQLTests(unittest.TestCase):
    def test_load_update_analysis_and_invalid_batch(self):
        prices, events = demo()
        load('mysql', prices, events, 'integration')
        load('mysql', prices, events, 'integration')
        with connect('mysql') as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM prices').fetchone()[0], 288)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM events').fetchone()[0], 3)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0], 2)
            rows = connection.execute((ROOT / 'sql/analysis.sql').read_text()).fetchall()
            self.assertEqual(len(rows), 285)
            self.assertTrue(all(abs(r[2]) < .01 for r in rows))
        self.assertTrue(all(r['status'] == 'ok' for r in responses('mysql')))
        self.assertEqual(len(response_curve('mysql')), 216)
        prices[0]['close'] = 123
        load('mysql', prices, events, 'correction')
        with connect('mysql') as connection:
            self.assertEqual(connection.execute('SELECT close FROM prices WHERE instrument=? AND timestamp_utc=?',
                                               (prices[0]['instrument'], prices[0]['timestamp_utc'])).fetchone()[0], 123)
        prices[0]['close'] = -1
        with self.assertRaises(ValueError):
            load('mysql', prices, events, 'invalid')
        with connect('mysql') as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0], 3)
