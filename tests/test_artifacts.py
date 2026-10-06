"""Checked-in demo reports must match the maintained pipeline and file manifest."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline import ROOT, demo, load, response_curve


class ArtifactTests(unittest.TestCase):
    def test_real_report_artifact_integrity_and_cash_scope(self):
        manifest = json.loads((ROOT/'results/real/manifest.json').read_text())
        self.assertEqual(manifest['dataset'],'real')
        self.assertEqual({s['ticker'] for s in manifest['price_sources']},{'^HSI','^STOXX50E','^NDX'})
        self.assertEqual(len(manifest['timezone_checkpoints']),3)
        for relative, record in manifest['artifacts'].items():
            data=(ROOT/relative).read_bytes()
            self.assertEqual(len(data),record['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256'])
        with (ROOT/'results/real/focus_1h_summary.csv').open(newline='',encoding='utf-8') as handle:
            rows=list(csv.DictReader(handle))
        self.assertEqual(len(rows),9)
        self.assertTrue(all(int(row['n'])>=2 for row in rows))

    def test_manifest_and_responses_match_pipeline(self):
        manifest = json.loads((ROOT / 'results/manifest.json').read_text())
        self.assertEqual(manifest['dataset'], 'synthetic')
        for relative, metadata in manifest['artifacts'].items():
            data = (ROOT / relative).read_bytes()
            self.assertEqual(len(data), metadata['bytes'], relative)
            self.assertEqual(hashlib.sha256(data).hexdigest(), metadata['sha256'], relative)
        with (ROOT / 'results/response_curve.csv').open(newline='', encoding='utf-8') as handle:
            saved = list(csv.DictReader(handle))
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'demo.db'
            load(db, *demo(), 'artifact_check')
            expected = response_curve(db)
        self.assertEqual(len(saved), manifest['response_rows'])
        self.assertEqual(len(saved), len(expected))
        for actual, row in zip(saved, expected):
            for key, value in row.items():
                if isinstance(value, float):
                    # math.log can differ in its final bit across Windows/Linux.
                    self.assertAlmostEqual(float(actual[key]), value, delta=1e-14, msg=key)
                else:
                    self.assertEqual(actual[key], str(value) if value is not None else '', key)
