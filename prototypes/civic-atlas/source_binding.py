"""Bind saved worlds to the full authoritative source, including business data."""
import gzip
import hashlib
import json

_hashes = {}


def read_snapshot(folder):
    path = folder / "snapshot.json"
    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    with gzip.open(folder / "snapshot.json.gz", "rt", encoding="utf-8") as handle:
        return json.load(handle)


def fingerprint(snapshot):
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    for part in encoder.iterencode(snapshot):
        digest.update(part.encode("utf-8"))
    return digest.hexdigest()


def source_fingerprint(folder, snapshot=None):
    path = folder / "snapshot.json"
    if not path.is_file():
        path = folder / "snapshot.json.gz"
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if key not in _hashes:
        _hashes[key] = fingerprint(snapshot if snapshot is not None else read_snapshot(folder))
    return _hashes[key]


def require_binding(world, expected):
    """Add an identity-only migration after comparing an older saved snapshot."""
    with world.read_db() as db:
        row = db.execute("SELECT value FROM meta WHERE key='atlasSourceSha256'").fetchone()
        if row:
            actual = json.loads(row[0])
        else:
            source = db.execute("SELECT value FROM meta WHERE key='snapshot'").fetchone()
            if not source:
                raise ValueError("Initialize the world before binding its source.")
            # World.initialize stores precisely this canonical JSON encoding.
            digest = hashlib.sha256()
            for offset in range(0, len(source[0]), 1024 * 1024):
                digest.update(source[0][offset:offset + 1024 * 1024].encode("utf-8"))
            actual = digest.hexdigest()
    if actual != expected:
        raise ValueError("The authoritative town source changed, including geometry, accounts, tariffs or feature data. "
                         "Use an explicit migration or a new store; saved history was preserved.")
    if not row:
        with world.db() as db:
            world.put(db, "atlasSourceSha256", expected)
