"""Deterministic compressed source packages; retain raw working files locally."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def pack(folder):
    records = []
    for name in ("snapshot.json", "geometry.json"):
        source = folder / name
        raw = source.read_bytes()
        target = folder / (name + ".gz")
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        if len(packed) >= 95_000_000:
            raise ValueError(f"{target}: compressed source exceeds conservative Git file limit")
        target.write_bytes(packed)
        assert gzip.decompress(target.read_bytes()) == raw
        records.append({"path": target.name, "rawPath": name, "bytes": len(packed), "rawBytes": len(raw),
                        "sha256": hashlib.sha256(packed).hexdigest(), "rawSha256": hashlib.sha256(raw).hexdigest()})
    manifest = {"schema": "atlas-source-package/1", "presetId": folder.name, "files": records}
    (folder / "source-package.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path)
    args = parser.parse_args()
    for folder in args.folders:
        print(json.dumps(pack(folder)), flush=True)


if __name__ == "__main__":
    main()
