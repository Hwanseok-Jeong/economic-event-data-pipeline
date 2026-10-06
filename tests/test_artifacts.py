"""Checked-in demo reports must match the maintained pipeline and file manifest."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline import ROOT, demo, load, response_curve


class ArtifactTests(unittest.TestCase):
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
                self.assertEqual(actual[key], str(value) if value is not None else '', key)
