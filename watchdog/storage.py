"""Resolve storage once inside the caller's Hermes profile scope."""

from .policy import PLUGIN_ID
from .store import Store


def open_store():
    from plugins.plugin_storage import plugin_data_dir, plugin_db

    root = plugin_data_dir(PLUGIN_ID)
    root.chmod(0o700)
    db = plugin_db(PLUGIN_ID)
    (root / "data.db").chmod(0o600)
    return Store(db)
