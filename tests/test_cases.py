"""SQL classification verifies denominators, co-releases, neutral boundaries and time order."""
import hashlib
import json
import sqlite3
import unittest
from pathlib import Path
from build_case_report import classify


class CaseTests(unittest.TestCase):
    def test_classification_and_co_release_deduplication(self):
        connection=sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        connection.execute('CREATE TABLE session_responses_report ('
                           'event_key TEXT,country TEXT,event_timestamp_utc TEXT,instrument TEXT,'
                           'status TEXT,observation_timestamp_utc TEXT,return_pct REAL)')
        def add(key,release,values,times=('01','02','03'),status=('ok','ok','ok')):
            connection.executemany('INSERT INTO session_responses_report VALUES (?,?,?,?,?,?,?)',
                [(key,'US',release,market,s,t,value) for market,s,t,value in zip(
                    ['STOXX50E','NDX','HSI'],status,times,values)])
        add('a','release1',[.2,.3,.4])
        add('b','release1',[.2,.3,.4])  # Co-release: same price windows, one denominator unit.
        add('c','release2',[.1,.3,.4])  # Boundary is neutral.
        add('d','release3',[.3,-.4,0])  # Mixed takes precedence over neutral.
        add('e','release4',[-.2,-.3,-.4],times=('02','01','03'))  # Time order prevents increase.
        add('f','release5',[.2,.3,None],status=('ok','ok','missing_price'))
        rows=classify(connection)
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0]['indicator_count'],2)
        self.assertEqual([r['direction'] for r in rows],
                         ['all_positive','includes_neutral','mixed_direction','all_negative'])
        self.assertEqual([r['increasing_magnitude'] for r in rows],[1,0,0,0])

    def test_published_case_artifacts(self):
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'results/cases/manifest.json').read_text())
        for relative,record in manifest['artifacts'].items():
            data=(root/relative).read_bytes()
            self.assertEqual(len(data),record['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256'])
        stats=json.loads((root/'results/cases/summary.json').read_text())
        self.assertEqual(sum(stats['categories'].values()),stats['eligible_releases'])
        self.assertEqual(stats['eligible_releases']+stats['excluded_releases'],stats['release_clusters'])
