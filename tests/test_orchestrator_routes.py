"""Keep unverified agy Orchestrator modes out of Hermes."""

from unittest.mock import patch

import pytest
from conftest import PLUGIN
from antigravity_plugin_entry import models


ORCHESTRATORS = (
    'gemini-pro-orchestrator',
    'gemini-pro-orchestrator-carbon',
    'gemini-pro-orchestrator-argon',
)


def test_catalog_and_picker_exclude_orchestrators_but_keep_standalone_models(monkeypatch):
    standalone = ['gemini-4-carbon', 'gemini-4-argon', 'gemini-4-hydrogen']
    raw = '\n'.join((*ORCHESTRATORS, *standalone))
    assert list(models.parse_catalog(raw)) == standalone
    monkeypatch.setattr(PLUGIN, 'load_catalog', lambda **kwargs: dict.fromkeys((*ORCHESTRATORS, *standalone), ()))
    assert PLUGIN.antigravity_profile.fetch_models() == standalone
    monkeypatch.setattr(PLUGIN, 'load_catalog', lambda **kwargs: {})
    assert not any('orchestrator' in m for m in PLUGIN.antigravity_profile.fetch_models())
    assert not any('orchestrator' in m for m in PLUGIN.antigravity_profile.model_aliases)


def test_explicit_or_saved_orchestrator_ids_fail_before_spawning_agy():
    with patch.object(models, 'load_catalog', side_effect=AssertionError('must not spawn agy')):
        for name in ORCHESTRATORS:
            with pytest.raises(ValueError, match='Orchestrator is disabled in Hermes'):
                models.resolve_model_and_effort(name, 'high')
            assert PLUGIN.antigravity_profile.supported_reasoning_efforts(name) == ()


def test_orchestrator_ids_never_fuzzy_match_other_models():
    catalog = {'gemini-4-carbon': (), 'gemini-4-argon': (), 'gemini-4-hydrogen': ('high', 'xhigh')}
    for name in ORCHESTRATORS:
        assert models.resolve_model_alias(name, catalog) == name
    assert models.resolve_model_alias('pro', {'gemini-3.1-pro': ('high',)}) == 'gemini-3.1-pro'
