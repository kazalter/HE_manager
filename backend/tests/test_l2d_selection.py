import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('l2d_selection', Path(__file__).resolve().parents[2] / 'desktop' / 'src' / 'l2d_selection.py')
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)


def test_prefer_uncensored_and_skip_existing():
    assert selection.select_targets(
        ['both_2', 'both_2_hx', 'server_2_hx', 'only_2_hx', 'old_2', '../unsafe'],
        ['server_2', 'old_2'],
    ) == ['both_2', 'only_2_hx']


def test_uncensored_is_still_added_if_only_censored_is_installed():
    assert selection.select_targets(['skin_2', 'skin_2_hx'], ['skin_2_hx']) == ['skin_2']
