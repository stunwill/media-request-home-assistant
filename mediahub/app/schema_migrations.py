"""Serialize complete schema checks/DDL across ingress and external workers."""
from __future__ import annotations

import fcntl
import functools
import os
import threading

_local = threading.local()


def serialised(function):
    @functools.wraps(function)
    def migrate(*args, **kwargs):
        from . import main
        if getattr(_local, 'depth', 0):
            return function(*args, **kwargs)
        path = main.DATABASE_FILE.with_suffix('.migration.lock')
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            _local.depth = 1
            result = function(*args, **kwargs)
            with main.connect_db() as db:
                db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, completed_at TEXT NOT NULL)')
                db.execute('INSERT OR REPLACE INTO schema_migrations VALUES(?,?)', (function.__module__+'.'+function.__name__, main.utc_now()))
            return result
        finally:
            _local.depth = 0
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    return migrate
