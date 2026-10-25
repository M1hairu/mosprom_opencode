#!/usr/bin/env python3
"""3D models of exhibits from GitHub releases (#354): `make models`.

Takes every *.glb asset of the repository releases (gh CLI, newest release wins for one
name) into web/public/models/ and adds it to web/src/planner/models.json.
Asset name = plan key: an object id (`ex_gaas.glb`) or an object type id
(`ot_smart_base.glb`) from content/plan-219-zoned.json; the object id wins in the 3D plan.
The repository is private: the site and the VPS cannot fetch release assets, so the
files go to main through a PR like any other file. Stdlib only.
"""
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "web/public/models"
INDEX = ROOT / "web/src/planner/models.json"
PLAN = ROOT / "content/plan-219-zoned.json"
# A phone on mobile data opens the 3D plan: one model above this is a slow page.
WARN_BYTES = 5 * 1024 * 1024
# The 3D plan has no decoder for these: such a file stays a box.
UNSUPPORTED = {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu"}


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def glb_extensions(path: Path) -> set[str]:
    data = path.read_bytes()
    magic, _, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("not a binary glTF (.glb)")
    length, kind = struct.unpack_from("<I4s", data, 12)
    if kind != b"JSON":
        raise ValueError("first glb chunk is not JSON")
    head = json.loads(data[20 : 20 + length])
    return set(head.get("extensionsRequired", []))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    keys = {o["id"] for o in plan["objects"]} | {t["id"] for t in plan["catalog"]["objectTypes"]}
    index: dict[str, str] = json.loads(INDEX.read_text(encoding="utf-8"))

    releases = json.loads(gh("release", "list", "--limit", "100", "--json", "tagName,createdAt"))
    releases.sort(key=lambda r: r["createdAt"], reverse=True)
    taken: set[str] = set()
    problems = 0
    loaded = 0
    with tempfile.TemporaryDirectory() as tmp:
        for release in releases:
            tag = release["tagName"]
            assets = json.loads(gh("release", "view", tag, "--json", "assets"))["assets"]
            for name in sorted(a["name"] for a in assets if a["name"].lower().endswith(".glb")):
                if name in taken:
                    continue
                taken.add(name)
                key = name[: -len(".glb")]
                if key not in keys:
                    print(f"ПРОПУСК {tag}/{name}: нет объекта или типа «{key}» в {PLAN.name}")
                    problems += 1
                    continue
                gh("release", "download", tag, "--pattern", name, "--dir", tmp, "--clobber")
                path = Path(tmp) / name
                try:
                    bad = glb_extensions(path) & UNSUPPORTED
                except ValueError as e:
                    print(f"ПРОПУСК {tag}/{name}: {e}")
                    problems += 1
                    continue
                if bad:
                    print(f"ПРОПУСК {tag}/{name}: сжатие {', '.join(sorted(bad))}; экспорт из Blender без сжатия")
                    problems += 1
                    continue
                size = path.stat().st_size
                if size > WARN_BYTES:
                    print(f"ВНИМАНИЕ {name}: {size / 1e6:.1f} МБ, на телефоне загрузка будет долгой")
                path.replace(MODELS_DIR / name)
                index[key] = name
                loaded += 1
                print(f"{tag}/{name} → web/public/models/{name} ({size / 1e6:.2f} МБ)")

    INDEX.write_text(json.dumps(dict(sorted(index.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"взято из релизов: {loaded}, пропущено: {problems}; таблица — {INDEX.relative_to(ROOT)}")
    if not taken:
        print("в релизах нет файлов .glb: план в 3D берёт модели из web/public/models")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
