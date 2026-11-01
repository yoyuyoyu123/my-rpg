"""Allowlisted staging only: never package .env, saves, virtualenvs or tests."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ["research_db", "tag_ontology", "china_works_2010_2015", "china_works_2016_2020",
            "china_works_2021_2024", "china_works_2025_2026", "japan_works_2010_2015",
            "japan_works_2016_2020", "japan_works_2021_2026", "manga_works_2010_2015",
            "manga_works_2016_2020", "manga_works_2021_2026"]


def prepare(dest: Path):
    dest = dest.resolve()
    # Only remove the staging directory allocated inside this project's build directory.
    expected = (ROOT / "android/app/build/generated/game").resolve()
    if dest != expected:
        raise ValueError("Android staging destination must be android/app/build/generated/game")
    if dest.exists():
        shutil.rmtree(dest)
    python_dir, assets = dest / "python", dest / "assets"
    assets.mkdir(parents=True)
    for source in (ROOT / "backend/app").rglob("*.py"):
        if "__pycache__" in source.parts or source.is_symlink():
            continue
        target = python_dir / source.relative_to(ROOT / "backend")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    paths = [Path("index.html"), Path("data/worlds/catalog.json")]
    paths += [Path("research") / (name + ".json") for name in RESEARCH]
    manifest = {}
    with zipfile.ZipFile(assets / "game-web.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in paths:
            source = ROOT / relative
            if source.is_symlink():
                raise ValueError("Bundled game resources may not be symlinks")
            data = source.read_bytes()
            archive.writestr(relative.as_posix(), data)
            manifest[relative.as_posix()] = hashlib.sha256(data).hexdigest()
        shell = (ROOT / "android/app/src/main/assets/mobile-shell.js").read_bytes()
        archive.writestr("mobile-shell.js", shell)
        manifest["mobile-shell.js"] = hashlib.sha256(shell).hexdigest()
    (assets / "game-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Android: staged Python backend and {len(paths)} public game resources")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=ROOT / "android/app/build/generated/game")
    prepare(parser.parse_args().dest)
