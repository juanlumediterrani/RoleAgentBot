#!/usr/bin/env python3
"""Compara secciones de personalidades para detectar campos faltantes.

Dos modos de uso pensados para ayudar a Cascade:

1) translate: traducir una personalidad a otro idioma.
   Compara <personality>/<lang> contra <personality>/es-ES.
   Ej.: python tools/compare_personality.py translate yuki en-US

2) extend: completar los campos de una personalidad tomando RAB como modelo.
   Compara <personality>/es-ES contra rab/es-ES.
   Ej.: python tools/compare_personality.py extend yuki

Recorre todos los .json de la carpeta del idioma (incluyendo subcarpetas como
descriptions/) y reporta, por archivo:
  - claves faltantes (presentes en referencia, ausentes en objetivo)
  - claves vacías en objetivo (string/lista/dict vacío)
  - claves extra (presentes sólo en objetivo)
  - diferencias de longitud en listas de strings

Imprime además un recuento final de secciones pendientes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PERSONALITIES_DIR = ROOT / "personalities"
REFERENCE_PERSONALITY = "rab"
REFERENCE_LANG = "es-ES"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def walk_keys(
    ref: Any,
    tgt: Any,
    prefix: str,
    missing: list[str],
    empty: list[str],
    extra: list[str],
    list_mismatch: list[tuple[str, int, int]],
) -> None:
    """Recorre recursivamente ref/tgt y anota diferencias estructurales."""
    if isinstance(ref, dict):
        if not isinstance(tgt, dict):
            missing.append(prefix or "<root>")
            return
        for key, ref_val in ref.items():
            path = f"{prefix}.{key}" if prefix else key
            if key not in tgt:
                missing.append(path)
                continue
            tgt_val = tgt[key]
            if is_empty(tgt_val) and not is_empty(ref_val):
                empty.append(path)
                continue
            walk_keys(ref_val, tgt_val, path, missing, empty, extra, list_mismatch)
        for key in tgt.keys():
            if key not in ref:
                path = f"{prefix}.{key}" if prefix else key
                extra.append(path)
    elif isinstance(ref, list):
        if not isinstance(tgt, list):
            missing.append(prefix or "<root>")
            return
        if len(tgt) < len(ref):
            list_mismatch.append((prefix, len(ref), len(tgt)))


def discover_json_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def compare_dirs(ref_dir: Path, tgt_dir: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"files": {}, "totals": {
        "missing_files": 0, "missing_keys": 0, "empty_keys": 0,
        "extra_keys": 0, "list_mismatch": 0,
    }}

    ref_files = discover_json_files(ref_dir)
    for ref_path in ref_files:
        rel = ref_path.relative_to(ref_dir)
        tgt_path = tgt_dir / rel
        entry: dict[str, Any] = {
            "missing_file": False,
            "missing_keys": [],
            "empty_keys": [],
            "extra_keys": [],
            "list_mismatch": [],
        }

        if not tgt_path.exists():
            entry["missing_file"] = True
            report["totals"]["missing_files"] += 1
            report["files"][str(rel)] = entry
            continue

        try:
            ref_data = load_json(ref_path)
            tgt_data = load_json(tgt_path)
        except json.JSONDecodeError as exc:
            entry["error"] = f"JSON inválido: {exc}"
            report["files"][str(rel)] = entry
            continue

        walk_keys(
            ref_data, tgt_data, "",
            entry["missing_keys"], entry["empty_keys"],
            entry["extra_keys"], entry["list_mismatch"],
        )

        report["totals"]["missing_keys"] += len(entry["missing_keys"])
        report["totals"]["empty_keys"] += len(entry["empty_keys"])
        report["totals"]["extra_keys"] += len(entry["extra_keys"])
        report["totals"]["list_mismatch"] += len(entry["list_mismatch"])
        report["files"][str(rel)] = entry

    # Archivos presentes sólo en destino (extra).
    ref_rel = {p.relative_to(ref_dir) for p in ref_files}
    for tgt_path in discover_json_files(tgt_dir):
        rel = tgt_path.relative_to(tgt_dir)
        if rel not in ref_rel:
            report["files"].setdefault(str(rel), {
                "missing_file": False,
                "missing_keys": [],
                "empty_keys": [],
                "extra_keys": [],
                "list_mismatch": [],
                "only_in_target": True,
            })

    return report


def print_report(report: dict[str, Any], ref_label: str, tgt_label: str) -> None:
    print(f"Referencia: {ref_label}")
    print(f"Objetivo:   {tgt_label}")
    print("-" * 72)

    pending_files = 0
    for rel, entry in report["files"].items():
        if entry.get("only_in_target"):
            print(f"[extra]    {rel}  (sólo en objetivo)")
            continue
        if entry.get("missing_file"):
            print(f"[FALTA]    {rel}  (archivo inexistente en objetivo)")
            pending_files += 1
            continue
        if "error" in entry:
            print(f"[error]    {rel}: {entry['error']}")
            pending_files += 1
            continue

        has_issues = any((
            entry["missing_keys"], entry["empty_keys"],
            entry["list_mismatch"],
        ))
        if not has_issues and not entry["extra_keys"]:
            print(f"[ok]       {rel}")
            continue

        if has_issues:
            pending_files += 1
        print(f"[revisar]  {rel}")
        for k in entry["missing_keys"]:
            print(f"    - faltante: {k}")
        for k in entry["empty_keys"]:
            print(f"    - vacío:    {k}")
        for path, ref_len, tgt_len in entry["list_mismatch"]:
            print(f"    - lista corta: {path}  ({tgt_len}/{ref_len})")
        for k in entry["extra_keys"]:
            print(f"    - extra:    {k}")

    totals = report["totals"]
    print("-" * 72)
    print(
        "Totales: "
        f"archivos_faltantes={totals['missing_files']}, "
        f"claves_faltantes={totals['missing_keys']}, "
        f"claves_vacias={totals['empty_keys']}, "
        f"listas_cortas={totals['list_mismatch']}, "
        f"claves_extra={totals['extra_keys']}"
    )
    print(f"Archivos con trabajo pendiente: {pending_files}")


def resolve_lang_dir(personality: str, lang: str) -> Path:
    path = PERSONALITIES_DIR / personality / lang
    if not path.is_dir():
        sys.exit(f"No existe: {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_tr = sub.add_parser("translate", help="Comparar <personality>/<lang> contra <personality>/es-ES")
    p_tr.add_argument("personality")
    p_tr.add_argument("lang", help="Idioma objetivo, p.ej. en-US")

    p_ex = sub.add_parser("extend", help="Comparar <personality>/es-ES contra rab/es-ES")
    p_ex.add_argument("personality")

    args = parser.parse_args()

    if args.mode == "translate":
        ref = resolve_lang_dir(args.personality, REFERENCE_LANG)
        tgt = resolve_lang_dir(args.personality, args.lang)
        ref_label = f"{args.personality}/{REFERENCE_LANG}"
        tgt_label = f"{args.personality}/{args.lang}"
    else:
        ref = resolve_lang_dir(REFERENCE_PERSONALITY, REFERENCE_LANG)
        tgt = resolve_lang_dir(args.personality, REFERENCE_LANG)
        ref_label = f"{REFERENCE_PERSONALITY}/{REFERENCE_LANG}"
        tgt_label = f"{args.personality}/{REFERENCE_LANG}"

    report = compare_dirs(ref, tgt)
    print_report(report, ref_label, tgt_label)


if __name__ == "__main__":
    main()
