import math
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from pipeline import ROOT, demo, load, response_curve, responses, utc, validate


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / 'test.db'

    def test_repeat_load_is_idempotent_and_audited(self):
        prices, events = demo()
        load(self.db, prices, events, 'test')
        load(self.db, prices, events, 'test')
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM prices').fetchone()[0], 288)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM events').fetchone()[0], 3)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0], 2)

    def test_invalid_batch_does_not_change_database(self):
        prices, events = demo()
        load(self.db, prices, events, 'test')
        prices[0]['close'] = float('nan')
        with self.assertRaises(ValueError):
            load(self.db, prices, events, 'bad')
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0], 1)

    def test_timezone_normalization_and_naive_rejection(self):
        self.assertEqual(utc('2024-03-31T03:00:00+02:00'), '2024-03-31T01:00:00+00:00')
        self.assertEqual(utc('2024-10-27T02:00:00+01:00'), '2024-10-27T01:00:00+00:00')
        with self.assertRaises(ValueError):
            utc('2024-01-01T12:00:00')

    def test_conflicting_duplicates_rejected(self):
        prices, events = demo()
        prices.append(dict(prices[0], close=999))
        with self.assertRaises(ValueError):
            validate(prices, events)

    def test_full_curve_preserves_single_horizon_results(self):
        prices, events = demo()
        load(self.db, prices, events, 'test')
        curve = response_curve(self.db)
        self.assertEqual(len(curve), 216)
        self.assertEqual([r for r in curve if r['horizon_hours'] == 24], responses(self.db, 24))
        self.assertEqual({r['horizon_hours'] for r in curve}, set(range(1, 25)))

    def test_returns_are_partitioned_by_instrument(self):
        prices, events = demo()
        load(self.db, prices, events, 'test')
        with closing(sqlite3.connect(self.db)) as connection, connection:
            rows = connection.execute((ROOT / 'sql/analysis.sql').read_text()).fetchall()
        self.assertEqual(len(rows), 285)
        self.assertTrue(all(abs(row[2]) < .01 for row in rows))

    def test_response_and_distant_bar_exclusion(self):
        prices, events = demo()
        load(self.db, prices, events, 'test')
        rows = responses(self.db)
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(row['status'] == 'ok' for row in rows))
        first = rows[0]
        lookup = {(p['instrument'], p['timestamp_utc']): p['close'] for p in prices}
        expected = math.log(lookup[first['instrument'], first['target_timestamp_utc']] /
                            lookup[first['instrument'], first['base_timestamp_utc']])
        self.assertAlmostEqual(first['log_return'], expected)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("DELETE FROM prices WHERE timestamp_utc BETWEEN '2024-01-03T11:00:00+00:00' AND '2024-01-03T15:00:00+00:00'")
        self.assertTrue(any(row['status'] == 'outside_tolerance' and row['log_return'] is None for row in responses(self.db)))


if __name__ == '__main__':
    unittest.main()
