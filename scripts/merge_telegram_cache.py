#!/usr/bin/env python3
"""
Merge Ratio1 Telegram bot cache pickle files into a stable instance path.

The script is dry-run by default. Pass ``--write`` to create/update files under
the target instance's ``plugin_data`` directory.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


CACHE_FILES = [
  "ratio1_epoch_review_data.pkl",
  "ratio1_watched_wallets_data.pkl",
  "ratio1_offline_node_alerts_data.pkl",
  "ratio1_watched_apis_data.pkl",
]


def load_pickle(path: Path) -> Any:
  with path.open("rb") as stream:
    return pickle.load(stream)


def save_pickle_atomic(path: Path, data: Any) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
  tmp_path = Path(tmp_name)
  try:
    with os.fdopen(fd, "wb") as stream:
      pickle.dump(data, stream)
    os.replace(tmp_path, path)
  finally:
    if tmp_path.exists():
      tmp_path.unlink()


def stable_unique(values: list[Any]) -> list[Any]:
  result = []
  seen = set()
  for value in values:
    marker = repr(value)
    if marker in seen:
      continue
    seen.add(marker)
    result.append(value)
  return result


def source_label(path: Path, cache_root: Path) -> str:
  try:
    return str(path.relative_to(cache_root))
  except ValueError:
    return str(path)


def merge_epochs(items: list[tuple[Path, dict[Any, Any]]]) -> dict[Any, Any]:
  merged: dict[Any, Any] = {}
  for _path, data in items:
    for epoch, value in data.items():
      if bool(value):
        merged[epoch] = value
      elif epoch not in merged:
        merged[epoch] = value
  return merged


def merge_wallets(items: list[tuple[Path, dict[Any, Any]]]) -> dict[str, list[Any]]:
  merged: dict[str, list[Any]] = {}
  for _path, data in items:
    for chat_id, wallets in data.items():
      key = str(chat_id)
      if wallets is None:
        wallets = []
      if not isinstance(wallets, list):
        wallets = list(wallets)
      merged[key] = stable_unique([*merged.get(key, []), *wallets])
  return merged


def merge_newest_by_key(items: list[tuple[Path, dict[Any, Any]]]) -> dict[Any, Any]:
  merged: dict[Any, Any] = {}
  seen_mtime: dict[Any, float] = {}
  for path, data in items:
    mtime = path.stat().st_mtime
    for key, value in data.items():
      if key not in seen_mtime or mtime >= seen_mtime[key]:
        merged[key] = value
        seen_mtime[key] = mtime
  return merged


def merge_apis(items: list[tuple[Path, dict[Any, Any]]]) -> dict[Any, Any]:
  merged: dict[Any, Any] = {}
  source_mtime: dict[Any, float] = {}
  for path, data in items:
    mtime = path.stat().st_mtime
    for health_url, api_watch in data.items():
      if not isinstance(api_watch, dict):
        if health_url not in merged or mtime >= source_mtime.get(health_url, 0):
          merged[health_url] = api_watch
          source_mtime[health_url] = mtime
        continue

      existing = merged.get(health_url)
      if not isinstance(existing, dict):
        existing = {}

      subscribers = stable_unique([
        *existing.get("subscribers", []),
        *api_watch.get("subscribers", []),
      ])

      if mtime >= source_mtime.get(health_url, 0):
        new_value = dict(api_watch)
        new_value["subscribers"] = subscribers
        merged[health_url] = new_value
        source_mtime[health_url] = mtime
      else:
        existing["subscribers"] = subscribers
        merged[health_url] = existing
  return merged


def merge_file(filename: str, items: list[tuple[Path, dict[Any, Any]]]) -> dict[Any, Any]:
  if filename == "ratio1_epoch_review_data.pkl":
    return merge_epochs(items)
  if filename == "ratio1_watched_wallets_data.pkl":
    return merge_wallets(items)
  if filename == "ratio1_watched_apis_data.pkl":
    return merge_apis(items)
  if filename == "ratio1_offline_node_alerts_data.pkl":
    return merge_newest_by_key(items)
  return merge_newest_by_key(items)


def summarize(data: Any) -> dict[str, Any]:
  if not isinstance(data, dict):
    return {"type": type(data).__name__, "repr": repr(data)[:200]}
  return {
    "type": "dict",
    "len": len(data),
    "key_types": sorted({type(key).__name__ for key in data.keys()}),
    "sample_keys": [str(key) for key in list(data.keys())[:5]],
  }


def resolve_source_dir(cache_root: Path, pipeline: str, source: str) -> Path:
  source_path = Path(source)
  if source_path.is_absolute():
    return source_path
  return cache_root / "pipelines_data" / pipeline / source / "plugin_data"


def collect_sources(
  cache_root: Path,
  pipeline: str,
  source_instances: list[str],
  include_flat: bool,
) -> list[Path]:
  source_dirs = []
  if include_flat:
    source_dirs.append(cache_root)
  for source in source_instances:
    source_dirs.append(resolve_source_dir(cache_root, pipeline, source))
  return source_dirs


def backup_target(target_dir: Path, backup_dir: Path | None) -> Path | None:
  existing_files = [target_dir / filename for filename in CACHE_FILES if (target_dir / filename).exists()]
  if not existing_files:
    return None

  if backup_dir is None:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = target_dir.parent / f"{target_dir.name}.backup.{stamp}"
  backup_dir.mkdir(parents=True, exist_ok=False)
  for path in existing_files:
    shutil.copy2(path, backup_dir / path.name)
  return backup_dir


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--cache-root",
    default="/var/cache/edge_node/_local_cache/_data",
    help="Edge node _data cache directory.",
  )
  parser.add_argument("--pipeline", default="ratio1_telegram_bot")
  parser.add_argument("--target-instance", required=True)
  parser.add_argument(
    "--source-instance",
    action="append",
    default=[],
    help="Source instance id or absolute plugin_data path. Can be repeated.",
  )
  parser.add_argument("--include-flat", action="store_true", help="Include legacy flat _data cache files.")
  parser.add_argument("--write", action="store_true", help="Write merged files. Default is dry-run.")
  parser.add_argument("--backup-dir", default=None, help="Optional directory for backing up existing target files.")
  return parser.parse_args()


def main() -> int:
  args = parse_args()
  cache_root = Path(args.cache_root)
  target_dir = cache_root / "pipelines_data" / args.pipeline / args.target_instance / "plugin_data"
  source_dirs = collect_sources(
    cache_root=cache_root,
    pipeline=args.pipeline,
    source_instances=args.source_instance,
    include_flat=args.include_flat,
  )

  report: dict[str, Any] = {
    "mode": "write" if args.write else "dry-run",
    "cache_root": str(cache_root),
    "target_dir": str(target_dir),
    "source_dirs": [str(path) for path in source_dirs],
    "files": {},
  }

  merged_by_file: dict[str, Any] = {}
  for filename in CACHE_FILES:
    loaded: list[tuple[Path, dict[Any, Any]]] = []
    skipped = []
    for source_dir in source_dirs:
      path = source_dir / filename
      if not path.exists():
        skipped.append({"path": source_label(path, cache_root), "reason": "missing"})
        continue
      try:
        data = load_pickle(path)
      except Exception as exc:  # noqa: BLE001 - CLI report should include any load failure.
        skipped.append({"path": source_label(path, cache_root), "reason": repr(exc)})
        continue
      if not isinstance(data, dict):
        skipped.append({"path": source_label(path, cache_root), "reason": f"not dict: {type(data).__name__}"})
        continue
      loaded.append((path, data))

    merged = merge_file(filename, loaded) if loaded else None
    if merged is not None:
      merged_by_file[filename] = merged
    report["files"][filename] = {
      "sources": [
        {
          "path": source_label(path, cache_root),
          "mtime": path.stat().st_mtime,
          "summary": summarize(data),
        }
        for path, data in loaded
      ],
      "skipped": skipped,
      "merged_summary": summarize(merged) if merged is not None else None,
    }

  if args.write:
    backup_dir = Path(args.backup_dir) if args.backup_dir else None
    backup_path = backup_target(target_dir=target_dir, backup_dir=backup_dir)
    report["backup_dir"] = str(backup_path) if backup_path else None
    for filename, merged in merged_by_file.items():
      save_pickle_atomic(target_dir / filename, merged)
    report["written"] = [str(target_dir / filename) for filename in merged_by_file]

  print(json.dumps(report, indent=2, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
