import os

import pytest

from autoharness import config


@pytest.fixture
def dir_link():
    """Link a directory: a symlink, or an NTFS junction where Windows withholds the symlink
    privilege (no Developer Mode / not elevated). Both are followed by Path.resolve()."""
    def link(alias, target):
        try:
            alias.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            import _winapi
            _winapi.CreateJunction(str(target), str(alias))
    return link


@pytest.fixture(autouse=True)
def _no_real_notifier(monkeypatch):
    # config reads AUTOHARNESS_NOTIFY* at import: without this, a contributor's own notifier (a team
    # Slack hook, desktop popups) would fire for every drain the suite runs
    monkeypatch.setattr(config, "NOTIFY", "")
    monkeypatch.setattr(config, "NOTIFY_CMD", "")
