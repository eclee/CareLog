"""Back up the stopped CareLog service without importing the application.

Usage: python scripts/backup_data.py --data ./data --output ./backups/before-1.4
The output directory must not already exist. Stop all writers first.
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.data.resolve()
    target = args.output.resolve()
    if not (source / "carelog.db").is_file():
        parser.error(f"database not found: {source / 'carelog.db'}")
    if target.exists():
        parser.error(f"backup already exists: {target}")
    target.mkdir(parents=True)
    try:
        with sqlite3.connect(source / "carelog.db") as old, sqlite3.connect(target / "carelog.db") as new:
            old.backup(new)
            integrity = new.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"backup integrity check failed: {integrity}")
        if (source / "uploads").is_dir():
            shutil.copytree(source / "uploads", target / "uploads")
        digest = hashlib.sha256((target / "carelog.db").read_bytes()).hexdigest()
        manifest = {"database_sha256": digest, "database_integrity": integrity,
                    "source": str(source), "photo_files": sum(1 for p in (target / "uploads").rglob("*") if p.is_file())}
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        shutil.rmtree(target)
        raise
    print(f"Backup verified: {target}")


if __name__ == "__main__":
    main()
