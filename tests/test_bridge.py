import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('bridge_baseline',Path(__file__).parents[1]/'tools/bridge-baseline.py')
bridge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class LegacyBridgeTests(unittest.TestCase):
    def test_current_release_source_stays_baseline_until_signed_install(self):
        source=(Path(__file__).parents[1]/'harbor/server.py').read_text(encoding='utf-8')
        result=bridge.baseline_source(source)
        self.assertIn("VERSION = '0.3.1'",result)
        self.assertEqual(result.replace("VERSION = '0.3.1'","VERSION = '0.9.0'"),source)

    def test_missing_duplicate_or_dynamic_version_cannot_be_bootstrapped(self):
        for source in ('print("no version")',"VERSION = '0.9.0'\nVERSION = '0.4.1'\n",'VERSION = read_version()'):
            with self.subTest(source=source),self.assertRaises(ValueError):bridge.baseline_source(source)
