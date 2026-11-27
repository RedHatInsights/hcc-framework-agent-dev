"""Compare release behavior for one component/repository pair across two RPAs."""

import argparse
import sys
from pathlib import Path

import yaml


def select(entries, field, value):
    matches = [entry for entry in entries if entry[field] == value]
    if len(matches) != 1:
        raise ValueError(f"expected one {field}={value!r}, found {len(matches)}")
    return matches[0]


def settings(path, component, url):
    doc = yaml.safe_load(path.read_text())
    if doc["kind"] != "ReleasePlanAdmission":
        raise ValueError(f"{path}: not a ReleasePlanAdmission")
    spec = doc["spec"]
    entry = select(spec["data"]["mapping"]["components"], "name", component)
    repo = select(entry["repositories"], "url", url)
    # Keep omission distinct from explicit false: never infer release defaults.
    result = {
        key: entry[key] for key in ("public", "pushSourceContainer") if key in entry
    }
    result["policy"] = spec["policy"]
    if "tags" in repo:
        result["tags"] = sorted(repo["tags"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("component")
    parser.add_argument("old_repo")
    parser.add_argument("approved_repo")
    args = parser.parse_args()
    try:
        old = settings(args.source, args.component, args.old_repo)
        new = settings(args.destination, args.component, args.approved_repo)
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"Cannot compare RPA mappings: {exc}\n")

    differences = [
        key for key in sorted(old.keys() | new.keys()) if old.get(key) != new.get(key)
    ]
    for key in differences:
        print(f"{key}: {old.get(key, '<absent>')!r} -> {new.get(key, '<absent>')!r}")
    return int(bool(differences))


if __name__ == "__main__":
    sys.exit(main())
