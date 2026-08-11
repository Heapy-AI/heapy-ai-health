"""JSONL corpus에서 medical_term/medical_term_alias 적재 SQL을 생성한다.

사용법:
    python database/build_medical_term_catalog.py \
        --chunk-root vdb/chunk > /tmp/medical_term_catalog.sql
    psql "$RDB_DSN" -f /tmp/medical_term_catalog.sql

표준명과 관련어를 원천 metadata/본문에서 읽을 뿐, 의료용어를 코드에
직접 매핑하지 않는다. 초성·trigram 키는 DB migration의 생성 컬럼과
검색 함수가 처리한다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.medical_term_catalog import build_term_catalog, load_jsonl_corpus


def sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def render_sql(catalog: list[dict]) -> str:
    lines = [
        "BEGIN;",
        "",
        "-- generated from the configured JSONL corpus; do not hand-edit term mappings.",
    ]
    for term in sorted(catalog, key=lambda item: str(item["canonical_key"])):
        key = sql_literal(term["canonical_key"])
        name = sql_literal(term["canonical_name"])
        term_type = sql_literal(term["term_type"])
        lines.extend(
            [
                "",
                "INSERT INTO medical_term (canonical_key, canonical_name, term_type)",
                f"VALUES ({key}, {name}, {term_type})",
                "ON CONFLICT (canonical_key) DO UPDATE SET",
                "    canonical_name = EXCLUDED.canonical_name,",
                "    term_type = EXCLUDED.term_type,",
                "    is_active = TRUE,",
                "    updated_at = NOW();",
            ]
        )
        for alias in term.get("aliases", []):
            lines.extend(
                [
                    "INSERT INTO medical_term_alias",
                    "    (canonical_key, alias_display, alias_type, priority)",
                    "VALUES",
                    "    ("
                    f"{key}, {sql_literal(alias['display'])}, "
                    f"{sql_literal(alias.get('alias_type', 'USER_ALIAS'))}, "
                    f"{int(alias.get('priority', 0))}),",
                    "ON CONFLICT (canonical_key, alias_normalized) DO UPDATE SET",
                    "    alias_display = EXCLUDED.alias_display,",
                    "    alias_type = EXCLUDED.alias_type,",
                    "    priority = EXCLUDED.priority,",
                    "    is_active = TRUE;",
                ]
            )
    lines.extend(["", "COMMIT;", ""])
    # The comma above is intentionally replaced per statement so the generated
    # SQL remains easy to inspect and valid for every alias row.
    return _remove_insert_comma(lines)


def _remove_insert_comma(lines: list[str]) -> str:
    rendered: list[str] = []
    for line in lines:
        if line == "ON CONFLICT (canonical_key, alias_normalized) DO UPDATE SET":
            if rendered and rendered[-1].endswith(","):
                rendered[-1] = rendered[-1][:-1]
        rendered.append(line)
    return "\n".join(rendered)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chunk-root",
        type=Path,
        default=PROJECT_ROOT / "vdb" / "chunk",
        help="표준명/관련어를 읽을 JSONL chunk 디렉터리",
    )
    args = parser.parse_args()
    corpus = load_jsonl_corpus(args.chunk_root.resolve())
    catalog = build_term_catalog(corpus)
    sys.stdout.write(render_sql(catalog))
    print(
        f"-- catalog_terms={len(catalog)} source={args.chunk_root}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
