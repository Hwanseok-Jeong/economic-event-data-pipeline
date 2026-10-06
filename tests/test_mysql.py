"""Runs only against an explicitly configured disposable integration database."""
import os
import unittest
from datetime import datetime, timedelta
from database import connect
from pipeline import ROOT, demo, load, response_curve, responses
from study import session_responses


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
            key, stamp = connection.execute('SELECT event_key,timestamp_utc FROM events ORDER BY timestamp_utc LIMIT 1').fetchone()
            connection.execute('INSERT INTO event_details VALUES (?,?,?,?,?,?)', (key,'Fixture release','','','','fixture'))
            connection.execute('INSERT INTO market_sessions VALUES (?,?,?,?)',
                               ('DEMO_US','2024-01-02T00:00:00+00:00','2024-01-02T23:00:00+00:00','2024-01-02'))
            bars = [('DEMO_US', p['timestamp_utc'],
                     (datetime.fromisoformat(p['timestamp_utc'])+timedelta(hours=1)).isoformat(),
                     p['close'], p['close'], '2024-01-02') for p in demo()[0]
                    if p['instrument']=='DEMO_US' and p['timestamp_utc'].startswith('2024-01-02')]
            connection.executemany('INSERT INTO market_bars VALUES (?,?,?,?,?,?)',bars)
        session_rows = session_responses('mysql',[1])
        self.assertEqual(len(session_rows),1)
        self.assertEqual(session_rows[0]['mode'],'open_at_release')
        self.assertEqual(session_rows[0]['status'],'ok')
