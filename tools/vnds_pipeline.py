#!/usr/bin/env python3
"""Scan, structure-check, and track CLANNAD VNDS RU translation files."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIG = ROOT / "script"
RU_DIR = ROOT / "translated-ru" / "script"
LISTING = ROOT / "translated-ru" / "listing.json"
SPEAKERS_PATH = ROOT / "translated-ru" / "speakers.json"

CYR = re.compile(r"[А-Яа-яЁё]")
LAT_WORD = re.compile(r"[A-Za-z]{3,}")
SPEAKER_LINE = re.compile(r"^(\s*)text\s+@\[(.*)\]\s*$")
TEXT_LINE = re.compile(r"^(\s*)text(?:\s+(.*))?$")
CHOICE_LINE = re.compile(r"^(\s*)choice(?:\s+(.*))?$")
VAR_TOKEN = re.compile(r"\{\$[^}]*\}")

STATUSES = (
    "missing",
    "empty",
    "untranslated",
    "partial",
    "needs_qa",
    "qa_failed",
    "approved",
)

PRIORITY = [
    "qa_failed",
    "needs_qa",
    "partial",
    "untranslated",
    "empty",
    "missing",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_speakers() -> dict:
    data = load_json(SPEAKERS_PATH, {"speakers": {}})
    return data.get("speakers", {})


def orig_files() -> list[str]:
    return sorted(p.name for p in ORIG.glob("*.scr"))


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def is_speaker(line: str) -> bool:
    return SPEAKER_LINE.match(line) is not None


def is_dialogue_cmd(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("text ") or s.startswith("text\t") or s == "text" or s.startswith("choice")


def body_of_text(line: str) -> str:
    m = TEXT_LINE.match(line)
    if not m:
        return ""
    return (m.group(2) or "").strip()


def dialogue_bodies(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if is_speaker(line):
            continue
        s = line.lstrip()
        if s.startswith("text"):
            b = body_of_text(line)
            if b:
                out.append(b)
        elif s.startswith("choice"):
            m = CHOICE_LINE.match(line)
            out.append((m.group(2) or "") if m else "")
    return out


def looks_english(text: str) -> bool:
    if CYR.search(text):
        return False
    return bool(LAT_WORD.search(text))


def classify_file(name: str, speakers: dict) -> dict:
    op = ORIG / name
    rp = RU_DIR / name
    rec = {
        "name": name,
        "status": "missing",
        "structure_ok": False,
        "orig_lines": 0,
        "ru_lines": 0,
        "ru_bytes": 0,
        "cyrillic_ratio": 0.0,
        "english_left": 0,
        "speakers_untranslated": [],
        "structure_errors": [],
        "notes": "",
    }
    if not op.exists():
        rec["status"] = "missing"
        rec["notes"] = "нет оригинала"
        return rec
    olines = read_lines(op)
    rec["orig_lines"] = len(olines)
    if not rp.exists():
        rec["status"] = "missing"
        return rec
    rec["ru_bytes"] = rp.stat().st_size
    if rec["ru_bytes"] < 8:
        rec["status"] = "empty"
        rec["notes"] = "пустой или битый файл"
        return rec
    rlines = read_lines(rp)
    rec["ru_lines"] = len(rlines)
    struct = structure_check(olines, rlines, speakers)
    rec["structure_ok"] = struct["ok"]
    rec["structure_errors"] = struct["errors"][:20]
    rec["speakers_untranslated"] = struct["speakers_untranslated"][:30]

    bodies = dialogue_bodies(rlines)
    orig_bodies = dialogue_bodies(olines)
    if not orig_bodies:
        rec["cyrillic_ratio"] = 1.0
        rec["status"] = "needs_qa" if rec["structure_ok"] else "partial"
        rec["notes"] = "нет реплик — только код"
        return rec

    translatable = [b for b in orig_bodies if looks_english(b)]
    ru_cyr = sum(1 for b in bodies if CYR.search(b) or not looks_english(b))
    rec["cyrillic_ratio"] = round(ru_cyr / max(len(bodies), 1), 3)
    rec["english_left"] = sum(1 for b in bodies if looks_english(b))

    same = 0
    n = min(len(orig_bodies), len(bodies))
    if n:
        same = sum(1 for a, b in zip(orig_bodies[:n], bodies[:n]) if a == b)

    if rec["english_left"] == 0 and rec["cyrillic_ratio"] >= 0.95:
        rec["status"] = "needs_qa"
    elif not translatable:
        rec["status"] = "needs_qa"
        rec["notes"] = "реплики без английского текста"
    elif rec["english_left"] >= max(3, int(0.7 * len(translatable))) and same > 0.6 * n:
        rec["status"] = "untranslated"
    elif rec["cyrillic_ratio"] < 0.85 or rec["english_left"] > 0:
        rec["status"] = "partial"
    else:
        rec["status"] = "needs_qa"

    if not rec["structure_ok"] and rec["status"] in ("needs_qa",):
        rec["status"] = "partial"
        rec["notes"] = (rec["notes"] + " ").strip() + "нарушена структура"
    return rec


def structure_check(olines: list[str], rlines: list[str], speakers: dict) -> dict:
    errors = []
    untranslated = []
    if len(olines) != len(rlines):
        errors.append(f"число строк: orig {len(olines)} != ru {len(rlines)}")
    n = min(len(olines), len(rlines))
    for i in range(n):
        o, r = olines[i], rlines[i]
        os_ = SPEAKER_LINE.match(o)
        rs_ = SPEAKER_LINE.match(r)
        if os_ or rs_:
            if not (os_ and rs_):
                errors.append(f"L{i+1}: тег говорящего не совпадает")
                continue
            if os_.group(1) != rs_.group(1):
                errors.append(f"L{i+1}: отступ говорящего")
            en = os_.group(2)
            ru = rs_.group(2)
            if en.startswith("{$"):
                if ru != en:
                    errors.append(f"L{i+1}: переменная говорящего изменена {en!r} -> {ru!r}")
            elif ru == en and LAT_WORD.search(en):
                untranslated.append(en)
            elif en in speakers and ru not in (speakers[en]["ru"], en):
                # допускаем en только как «ещё не переведён»; иное имя — ошибка
                if ru != speakers[en]["ru"]:
                    errors.append(
                        f"L{i+1}: говорящий {en!r} ожидается {speakers[en]['ru']!r}, сейчас {ru!r}"
                    )
            continue
        oc = CHOICE_LINE.match(o)
        rc = CHOICE_LINE.match(r)
        if oc or rc:
            if not (oc and rc):
                errors.append(f"L{i+1}: choice/не-choice")
                continue
            if oc.group(1) != rc.group(1):
                errors.append(f"L{i+1}: отступ choice")
            oopts = (oc.group(2) or "").split("|")
            ropts = (rc.group(2) or "").split("|")
            if len(oopts) != len(ropts):
                errors.append(f"L{i+1}: число вариантов choice {len(oopts)} != {len(ropts)}")
            ov = VAR_TOKEN.findall(oc.group(2) or "")
            rv = VAR_TOKEN.findall(rc.group(2) or "")
            if ov != rv:
                errors.append(f"L{i+1}: переменные в choice изменены")
            continue
        ot = TEXT_LINE.match(o)
        rt = TEXT_LINE.match(r)
        if ot and (o.lstrip().startswith("text")):
            if not (rt and r.lstrip().startswith("text")):
                errors.append(f"L{i+1}: text стал не-text")
                continue
            if ot.group(1) != rt.group(1):
                errors.append(f"L{i+1}: отступ text")
            ov = VAR_TOKEN.findall(ot.group(2) or "")
            rv = VAR_TOKEN.findall(rt.group(2) or "")
            if ov != rv:
                errors.append(f"L{i+1}: переменные в text изменены")
            continue
        if o != r:
            errors.append(f"L{i+1}: кодовая строка изменена")
            if len(errors) >= 40:
                break
    return {
        "ok": not errors and len(olines) == len(rlines),
        "errors": errors,
        "speakers_untranslated": sorted(set(untranslated)),
    }


def merge_listing(scan_rows: list[dict]) -> dict:
    old = load_json(LISTING, {"files": []})
    old_map = {f["name"]: f for f in old.get("files", [])}
    files = []
    for row in scan_rows:
        prev = old_map.get(row["name"], {})
        status = row["status"]
        prev_status = prev.get("status")
        # ручные статусы QA не затираем машинным сканом
        if prev_status == "approved" and status == "needs_qa" and row.get("structure_ok"):
            status = "approved"
        elif prev_status == "qa_failed" and status in ("needs_qa", "partial"):
            status = "qa_failed"
        files.append(
            {
                "name": row["name"],
                "status": status,
                "structure_ok": row["structure_ok"],
                "orig_lines": row["orig_lines"],
                "ru_lines": row["ru_lines"],
                "cyrillic_ratio": row["cyrillic_ratio"],
                "english_left": row["english_left"],
                "speakers_untranslated": row.get("speakers_untranslated") or [],
                "structure_errors": row.get("structure_errors") or [],
                "notes": prev.get("notes") or row.get("notes") or "",
                "qa_checked_at": prev.get("qa_checked_at"),
            }
        )
    return {
        "updated": now_iso(),
        "summary": dict(Counter(f["status"] for f in files)),
        "files": files,
    }


def cmd_scan(_args) -> None:
    speakers = load_speakers()
    rows = [classify_file(name, speakers) for name in orig_files()]
    listing = merge_listing(rows)
    save_json(LISTING, listing)
    print(json.dumps({"updated": listing["updated"], "summary": listing["summary"]}, ensure_ascii=False, indent=2))


def listing_map() -> dict:
    data = load_json(LISTING, {"files": []})
    return data, {f["name"]: f for f in data.get("files", [])}


def cmd_next(args) -> None:
    data, _ = listing_map()
    files = data.get("files") or []
    if not files:
        print("listing пуст — сначала: python tools/vnds_pipeline.py scan")
        return
    want = args.status
    picked = []
    for st in PRIORITY:
        if want and st != want:
            continue
        for f in files:
            if f["status"] == st:
                picked.append(f)
                if len(picked) >= args.limit:
                    break
        if len(picked) >= args.limit:
            break
    print(json.dumps({"next": picked, "summary": data.get("summary")}, ensure_ascii=False, indent=2))


def cmd_check(args) -> None:
    speakers = load_speakers()
    rec = classify_file(args.file, speakers)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    if rec["structure_errors"]:
        print("\nSTRUCTURE:")
        for e in rec["structure_errors"]:
            print(" -", e)


def cmd_set_status(args) -> None:
    if args.status not in STATUSES:
        raise SystemExit(f"неизвестный статус {args.status}; допустимы: {', '.join(STATUSES)}")
    data, fmap = listing_map()
    rec = fmap.get(args.file)
    if rec is None:
        speakers = load_speakers()
        rec = classify_file(args.file, speakers)
        data.setdefault("files", []).append(rec)
        fmap[args.file] = rec
    rec["status"] = args.status
    if args.notes is not None:
        rec["notes"] = args.notes
    if args.status in ("approved", "qa_failed"):
        rec["qa_checked_at"] = now_iso()
    data["updated"] = now_iso()
    data["summary"] = dict(Counter(f["status"] for f in data["files"]))
    save_json(LISTING, data)
    print(json.dumps({"name": args.file, "status": rec["status"], "notes": rec.get("notes", "")}, ensure_ascii=False, indent=2))


def cmd_init_file(args) -> None:
    name = args.file
    src = ORIG / name
    dst = RU_DIR / name
    if not src.exists():
        raise SystemExit(f"нет оригинала {src}")
    if dst.exists() and dst.stat().st_size >= 8 and not args.force:
        raise SystemExit(f"{dst} уже есть; --force чтобы перезаписать")
    dst.write_bytes(src.read_bytes())
    print(f"скопирован {name} -> translated-ru/script/")


def cmd_translate_speakers(args) -> None:
    speakers = load_speakers()
    path = RU_DIR / args.file
    if not path.exists():
        raise SystemExit(f"нет файла {path}")
    out = []
    n = 0
    for line in read_lines(path):
        m = SPEAKER_LINE.match(line)
        if m:
            en = m.group(2)
            if en in speakers and not en.startswith("{$"):
                ru = speakers[en]["ru"]
                if ru != en:
                    line = f"{m.group(1)}text @[{ru}]"
                    n += 1
        out.append(line)
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    print(f"заменено тегов говорящих: {n}")


def main() -> None:
    p = argparse.ArgumentParser(description="VNDS RU translation pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="пересканировать все .scr и обновить listing.json")

    n = sub.add_parser("next", help="следующий файл в очереди")
    n.add_argument("--limit", type=int, default=1)
    n.add_argument("--status", default="", help="фильтр статуса")
    n.set_defaults(func=cmd_next)

    c = sub.add_parser("check", help="проверить один файл")
    c.add_argument("file")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("set-status", help="записать статус QA в listing.json")
    s.add_argument("file")
    s.add_argument("status")
    s.add_argument("--notes", default=None)
    s.set_defaults(func=cmd_set_status)

    i = sub.add_parser("init-file", help="скопировать оригинал в translated-ru/script")
    i.add_argument("file")
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_init_file)

    t = sub.add_parser("translate-speakers", help="проставить русские @[имена] по глоссарию")
    t.add_argument("file")
    t.set_defaults(func=cmd_translate_speakers)

    args = p.parse_args()
    if args.cmd == "scan":
        cmd_scan(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
