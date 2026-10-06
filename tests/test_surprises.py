"""Numeric contracts and SQL grouping/median/coverage over known inputs."""
import hashlib
import json
import sqlite3
import unittest
from pathlib import Path
from surprise_analysis import create_tables, normalize_pair, query


def sql_fixture(connection):
    create_tables(connection)
    events=[]
    responses=[]
    # Four repeated above-forecast releases: even-sized median differs from mean.
    for i,value in enumerate([-2,-1,3,10]):
        key=f'a{i}'
        events.append((key,'US: CPI (MoM)',f'2024-01-{i+1:02}T00:00:00+00:00','0.3%','0.2%',
                       *normalize_pair('0.3%','0.2%')))
        responses.append((key,'HSI','closed_at_release','ok',value,'baseline','observed',15,1))
    # Unknown surprise retained, a missing price excluded from the return denominator.
    for i in range(2):
        key=f'u{i}'
        events.append((key,'US: Statement',f'2024-02-{i+1:02}T00:00:00+00:00','','',
                       *normalize_pair('','')))
        responses.append((key,'HSI','closed_at_release','ok' if i==0 else 'missing_price',
                          .1 if i==0 else None,'baseline','observed',15,1))
    events.append(('single','US: One-off','2024-03-01T00:00:00+00:00','2','1',*normalize_pair('2','1')))
    responses.append(('single','HSI','closed_at_release','ok',9,'baseline','observed',15,1))
    # A separate market state must not be pooled with the four closed observations.
    responses.append(('a0','NDX','open_at_release','ok',.2,'baseline','observed',1,1))
    connection.executemany('INSERT INTO event_surprises VALUES (?,?,?,?,?,?,?,?,?,?)',events)
    connection.executemany('INSERT INTO surprise_responses VALUES (?,?,?,?,?,?,?,?,?)',responses)
    return query(connection,'surprise_summary.sql',(.1,)*6)


class SurpriseTests(unittest.TestCase):
    def test_numeric_contract(self):
        self.assertAlmostEqual(normalize_pair('0.30%','0.2%')[3],.1)
        self.assertEqual(normalize_pair('1.2M','1,200K')[3],0)
        self.assertEqual(normalize_pair('-0.515M','1.500M')[3],-2015000)
        self.assertEqual(normalize_pair('2%','2')[4],'unit_mismatch')
        self.assertEqual(normalize_pair('','2')[4],'missing_value')
        self.assertEqual(normalize_pair('1,23','2')[4],'unsupported_format')
        self.assertEqual(normalize_pair('NaN','2')[4],'missing_value')
        self.assertEqual(normalize_pair('2–3%','2%')[4],'unsupported_format')

    def test_sql_summary(self):
        connection=sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        rows=sql_fixture(connection)
        self.assertEqual(len(rows),3)
        cpi=next(r for r in rows if r['family']=='US: CPI (MoM)' and r['instrument']=='HSI')
        self.assertEqual(cpi['n'],4)
        self.assertEqual(cpi['median_return_pct'],1)
        self.assertEqual(cpi['mean_return_pct'],2.5)
        self.assertEqual(cpi['positive_share_pct'],50)
        self.assertEqual(cpi['negative_share_pct'],50)
        unknown=next(r for r in rows if r['surprise_category']=='unknown')
        self.assertEqual(unknown['n'],1)
        self.assertEqual(unknown['neutral_n'],1)
        self.assertEqual(unknown['neutral_share_pct'],100)
        self.assertEqual(unknown['family_release_count'],2)
        observations=query(connection,'surprise_observations.sql')
        self.assertEqual(len(observations),7)
        self.assertEqual(sum(r['status']!='ok' for r in observations),1)

    def test_artifact_integrity(self):
        out=Path(__file__).resolve().parents[1]/'results/surprises'
        manifest=json.loads((out/'manifest.json').read_text())
        for filename,record in manifest['artifacts'].items():
            data=(out/filename).read_bytes()
            self.assertEqual(len(data),record['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256'])
