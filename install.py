"""Copy complete portable Skill bundles; never overwrite an installed Skill."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent


def main():
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skills", nargs="+", choices=sorted(catalog))
    parser.add_argument("--dest", type=Path, default=Path.home() / ".agents" / "skills",
                        help="Skill discovery root (default: ~/.agents/skills)")
    args = parser.parse_args()
    names = list(dict.fromkeys(args.skills))
    destination = args.dest.expanduser().resolve()
    try:
        for name in names:
            if os.path.lexists(destination / name):
                raise ValueError(f"Already installed: {destination / name}; move it outside the Skill discovery root before updating")
            if not (ROOT / catalog[name]["path"] / "SKILL.md").is_file():
                raise ValueError(f"Missing Skill entry: {name}")
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".skills-install-", dir=destination) as staging:
            staging = Path(staging)
            # Stage every bundle before publishing any of them.
            for name in names:
                entry = catalog[name]
                shutil.copytree(ROOT / entry["path"], staging / name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".pytest_cache", ".git"))
                if entry["license_file"]:
                    shutil.copy2(ROOT / entry["license_file"], staging / name / "LICENSE")
            for name in names:
                target = destination / name
                if os.path.lexists(target):
                    raise ValueError(f"Installation target appeared during copying: {target}")
                os.rename(staging / name, target)
                print(target)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Installation failed: {error}\n")


if __name__ == "__main__":
    main()
