#!/usr/bin/env python3
"""Validate a result JSON against schemas/result.schema.json plus the semantic rules of
docs/result-schema.md section 9 (plus rule 7: structure covers 0..duration_sec contiguously). Usage: uv run --with jsonschema validate_result.py FILE"""

import json
import re
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover
    sys.exit("jsonschema missing: run with `uv run --with jsonschema n8n/scripts/validate_result.py FILE`")

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "result.schema.json"


def iter_starts(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("start", "end") and isinstance(v, (int, float)):
                yield f"{path}.{k}", v
            else:
                yield from iter_starts(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_starts(v, f"{path}[{i}]")


def _normalize(text: str) -> str:
    return re.sub(r"[^\w]+", " ", str(text).lower(), flags=re.UNICODE).strip()


def _dice(a: str, b: str) -> float:
    ba = {a[i : i + 2] for i in range(len(a) - 1)}
    bb = {b[i : i + 2] for i in range(len(b) - 1)}
    if not ba or not bb:
        return 0.0
    return 2 * len(ba & bb) / (len(ba) + len(bb))


def quote_found(quote: str, clean_text: str, threshold: float = 0.9) -> bool:
    """Same rule as the digest check in n8n (llm-call): a normalized verbatim fragment of the
    transcript (case and punctuation ignored), otherwise a sentence with bigram similarity >= 0.9."""
    nq = _normalize(quote)
    if not nq:
        return False
    if nq in _normalize(clean_text):
        return True
    sentences = [_normalize(s) for s in re.split(r"(?<=[.!?…])\s+", clean_text)]
    return any(_dice(nq, s) >= threshold for s in sentences if s)


def semantic_errors(result: dict) -> list[str]:
    errors = []
    duration = result["source"]["duration_sec"]
    for path, value in iter_starts(result):
        if path.startswith("$.transcript.segments") or path.startswith("$.transcript.clean"):
            continue
        if value > duration:
            errors.append(f"rule 2: {path}={value} exceeds duration_sec={duration}")
    for seg in result["transcript"]["segments"]:
        if seg["end"] > duration + 1 or seg["start"] > seg["end"]:
            errors.append(f"rule 2: bad segment {seg['start']}-{seg['end']}")
    clean_text = " ".join(p["text"] for p in result["transcript"]["clean"])
    for i, q in enumerate(result["digest"]["quotes"]):
        if not quote_found(q["text"], clean_text):
            errors.append(f"rule 3: quote[{i}] not found in transcript.clean: {q['text'][:60]!r}")
    meta_summary = re.compile(r"^(обсужда|рассматрива|объясня|разбира|описыва|представля|подводится|подведение|обзор|discuss|overview|explain|describ|present|summing up|summar|cover)", re.I)
    list_or_popular = re.compile(r"(включа(ет|ют)|includ(e|es)|такие как|such as|являются? (популярн|известн|распространённ)|(is|are) (a )?(popular|well-known|widely used))", re.I)
    generic_title = re.compile(r"^(введение|заключение|вступление|основная часть|итоги|выводы|introduction|conclusion|main part|summary|overview|intro|outro)\.?$", re.I)
    allowed_title = re.compile(r"^(реклама|вступление канала|advertisement|channel intro)$", re.I)
    for i, part in enumerate(result["digest"]["structure"]):
        if meta_summary.match(part["summary"].strip()):
            errors.append(f"rule 9: structure[{i}].summary starts with a meta verb: {part['summary'][:50]!r}")
        if generic_title.match(part["title"].strip()) and not allowed_title.match(part["title"].strip()):
            errors.append(f"rule 9: structure[{i}].title is a generic label: {part['title']!r}")
    retell = re.compile(r"^\s*(спикер|автор|лектор|докладчик|ведущий|он|она|[А-ЯЁ][а-яё]+(\s[А-ЯЁ][а-яё]+)?)\s+(отмечает|подч[её]ркивает|призывает|говорит|рассказывает|объясняет|утверждает|считает|заявляет|делится|описывает|советует|напоминает)\b|^\s*(the\s+)?(speaker|author|lecturer|presenter|he|she|[A-Z][a-z]+(\s[A-Z][a-z]+)?)\s+(notes|emphasi[sz]es|urges|says|explains|argues|states|claims|shares|describes|advises|reminds|points out|stresses)\b")
    not_a_claim = re.compile(r"(являются?|служат?|стали?|стал[аи]?)\s+(напутствием|призывом|советом|наставлением|лозунгом|девизом)|\b(serves?|served|is|are|became|remains?)\s+(as\s+)?(a|an|the)?\s*(parting\s+(word|advice)|call to action|motto|slogan|reminder)\b", re.I)
    for i, k in enumerate(result["digest"]["key_points"]):
        if list_or_popular.search(k["text"]):
            errors.append(f"rule 9: key_points[{i}].text is a property list or popularity statement: {k['text'][:60]!r}")
        if not_a_claim.search(k["text"]):
            errors.append(f"rule 9: key_points[{i}].text describes the words as a message, not a claim: {k['text'][:60]!r}")
        if retell.search(k["detail"]):
            errors.append(f"rule 9: key_points[{i}].detail retells the speaker: {k['detail'][:60]!r}")
        for j, q in enumerate(result["digest"]["quotes"]):
            for cand in (q["text"], q.get("translation")):
                if cand and _dice(_normalize(k["text"]), _normalize(cand)) >= 0.8:
                    errors.append(f"rule 9: key_points[{i}].text repeats quotes[{j}]: {k['text'][:50]!r}")
                    break
    demonstrative = re.compile(r"^[«\"'“(]?\s*(это|этот|эта|эти|этим|этому|той|тот|та|те|this|that|these|those|it)\b", re.I)
    for i, q in enumerate(result["digest"]["quotes"]):
        if demonstrative.match(q["text"].strip()):
            errors.append(f"rule 9: quote[{i}].text starts with a demonstrative word: {q['text'][:50]!r}")
    translate = result["output_language"] != result["source"]["language"]
    for i, q in enumerate(result["digest"]["quotes"]):
        tr = q.get("translation")
        if translate and not (isinstance(tr, str) and tr.strip()):
            errors.append(f"rule 8: quote[{i}].translation is required when output_language != source.language")
        if not translate and tr is not None:
            errors.append(f"rule 8: quote[{i}].translation must be null when languages match")
    structure = result["digest"]["structure"]
    if structure:
        if abs(structure[0]["start"]) > 1e-6:
            errors.append(f"rule 7: structure[0].start={structure[0]['start']} must be 0")
        if abs(structure[-1]["end"] - duration) > 1e-6:
            errors.append(f"rule 7: last structure end={structure[-1]['end']} must equal duration_sec={duration}")
        for i, (a, b) in enumerate(zip(structure, structure[1:])):
            if a["start"] >= a["end"]:
                errors.append(f"rule 7: structure[{i}] start >= end")
            if abs(a["end"] - b["start"]) > 1e-6:
                errors.append(f"rule 7: structure[{i}].end={a['end']} != structure[{i + 1}].start={b['start']} (gap or overlap)")
    meta_tldr = re.compile(r"^\s*[«\"“]?\s*(в\s+(этом|данном|нашем|сегодняшнем)\s+(видео|ролике|выпуске|подкасте|докладе|разговоре|материале)|в\s+(этой|данной|сегодняшней)\s+(лекции|беседе|записи|встрече)|(это|данное)\s+видео|(видео|лекция|доклад|ролик|выпуск|подкаст|беседа|встреча|запись)[^.]{0,40}?\s(посвящен[аоы]?|посвящён|рассказывает|расскажет|разбирает|объясняет|показывает|знакомит)|in\s+this\s+(video|talk|lecture|episode|podcast|speech|session|recording)|(this|the)\s+(video|talk|lecture|episode|podcast|speech|session|recording)[^.]{0,30}?\s(is\s+about|covers|discusses|explores|presents|explains|focuses|describes|examines|tells|shows|walks|introduces))", re.I)
    if meta_tldr.match(result["digest"]["tldr"]):
        errors.append(f"rule 9: tldr starts with a meta opening: {result['digest']['tldr'][:60]!r}")
    if len(result["digest"]["tldr"].split()) > 80:
        errors.append(f"rule 5: tldr has {len(result['digest']['tldr'].split())} words (max 80)")
    stats = result["transcript"]["stats"]
    if stats["segments"] != len(result["transcript"]["segments"]):
        errors.append("stats.segments does not match transcript.segments length")
    return errors


def main(path: str) -> int:
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")), format_checker=FormatChecker())
    schema_errors = sorted(validator.iter_errors(result), key=lambda e: list(e.path))
    for err in schema_errors:
        print(f"schema: {'/'.join(str(p) for p in err.path) or '$'}: {err.message[:160]}")
    sem = semantic_errors(result)
    for err in sem:
        print(err)
    total = len(schema_errors) + len(sem)
    print(f"{path}: {'OK' if total == 0 else f'{total} problem(s)'} "
          f"(schema errors: {len(schema_errors)}, semantic: {len(sem)})")
    return 1 if total else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
