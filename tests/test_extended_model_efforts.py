"""Catalog and command contracts for agy's extended effort vocabulary."""

import importlib.util
import time
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "extended_effort_models", Path(__file__).resolve().parents[1] / "models.py"
)
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)

CATALOG = """gemini-4-hydrogen-xhigh Gemini 4 Hydrogen (XHigh)
gemini-4-hydrogen-high Gemini 4 Hydrogen (High)
gemini-4-hydrogen-medium Gemini 4 Hydrogen (Medium)
gemini-4-hydrogen-low Gemini 4 Hydrogen (Low)
gemini-3.8-flash-high Gemini 3.8 Flash (High)
gemini-3.8-flash-medium Gemini 3.8 Flash (Medium)
gemini-3.8-flash-low Gemini 3.8 Flash (Low)
gpt-oss-120b-medium GPT-OSS 120B (Medium)
custom-reasoner-max Custom reasoner (Max)
custom-reasoner-high Custom reasoner (High)
gemini-4-carbon Gemini 4 Carbon
claude-opus-5-5 Claude Opus 5.5
"""


class ExtendedModelEffortTests(unittest.TestCase):
    def test_catalog_groups_all_advertised_efforts(self):
        catalog = models.parse_catalog(CATALOG)
        self.assertEqual(catalog, {
            "gemini-4-hydrogen": ("low", "medium", "high", "xhigh"),
            "gemini-3.8-flash": ("low", "medium", "high"),
            "gpt-oss-120b": ("medium",),
            "custom-reasoner": ("high", "max"),
            "gemini-4-carbon": (),
            "claude-opus-5-5": (),
        })

    def test_resolution_preserves_supported_efforts_and_clamps_others(self):
        catalog = models.parse_catalog(CATALOG)
        cases = [
            ("gemini-4-hydrogen", "xhigh", ("gemini-4-hydrogen-xhigh", "xhigh")),
            ("gemini-4-hydrogen-xhigh", None, ("gemini-4-hydrogen-xhigh", "xhigh")),
            ("gemini-4-hydrogen", "max", ("gemini-4-hydrogen-xhigh", "xhigh")),
            ("gemini-3.8-flash", "xhigh", ("gemini-3.8-flash-high", "high")),
            ("gemini-3.8-flash", "max", ("gemini-3.8-flash-high", "high")),
            ("gpt-oss-120b", "max", ("gpt-oss-120b-medium", "medium")),
            ("custom-reasoner", "max", ("custom-reasoner-max", "max")),
            ("gemini-4-carbon", "xhigh", ("gemini-4-carbon", None)),
            ("claude-opus-5-5", "xhigh", ("claude-opus-5-5", None)),
        ]
        with patch.object(models, "_catalog_cache", (time.monotonic() + 60, catalog)):
            for model, effort, expected in cases:
                with self.subTest(model=model, effort=effort):
                    self.assertEqual(models.resolve_model_and_effort(model, effort), expected)
