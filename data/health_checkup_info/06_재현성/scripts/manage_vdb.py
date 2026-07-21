#!/usr/bin/env python3
"""Build, validate, inspect, and search the local development VDB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vdb.local_store import (  # noqa: E402
    audit,
    build_index,
    corpus_checksum,
    get_by_key,
    load_json,
    search_index,
    write_index,
)


DEFAULT_CORPUS = ROOT / "vdb/corpus/screening_core_v1.json"
DEFAULT_INDEX = ROOT / "vdb/index/screening_core_v1.local.json"
DEFAULT_REPORT = ROOT / "vdb/reports/screening_core_v1_quality.json"


def load_or_build(corpus_path: Path, index_path: Path) -> tuple[dict, dict]:
    corpus = load_json(corpus_path)
    if index_path.exists():
        index = load_json(index_path)
        if index.get("corpus_sha256") == corpus_checksum(corpus):
            return corpus, index
    index = build_index(corpus)
    write_index(index, index_path)
    return corpus, index


def write_report(report: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def command_build(args: argparse.Namespace) -> int:
    corpus = load_json(args.corpus)
    index = build_index(corpus, dimension=args.dimension)
    write_index(index, args.index)
    report = audit(corpus, index)
    write_report(report, args.report)
    print(f"built {len(index['chunks'])} vectors -> {args.index}")
    print(f"quality {report['status']} -> {args.report}")
    return 0 if report["status"] == "PASS" else 1


def command_validate(args: argparse.Namespace) -> int:
    corpus = load_json(args.corpus)
    index = load_json(args.index) if args.index.exists() else None
    report = audit(corpus, index)
    if args.report:
        write_report(report, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


def command_search(args: argparse.Namespace) -> int:
    _, index = load_or_build(args.corpus, args.index)
    rows = search_index(
        index,
        args.query,
        route=args.route,
        domain=args.domain,
        limit=args.limit,
        min_score=args.min_score,
    )
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("검색 결과가 없습니다.")
        return 0
    for rank, row in enumerate(rows, start=1):
        print(f"[{rank}] {row['heading']} ({row['canonical_key']}) score={row['score']:.4f}")
        print(row["content"])
        for evidence in row["evidence"]:
            print(f"  - {evidence['label']} · {evidence['locator']} · {evidence['url']}")
        print()
    return 0


def command_get(args: argparse.Namespace) -> int:
    _, index = load_or_build(args.corpus, args.index)
    row = get_by_key(index, args.canonical_key, route=args.route)
    if row is None:
        print("허용된 청크를 찾지 못했습니다.", file=sys.stderr)
        return 1
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def command_stats(args: argparse.Namespace) -> int:
    corpus, index = load_or_build(args.corpus, args.index)
    report = audit(corpus, index)
    print(json.dumps({"dataset": report["dataset"], "index": report["index"]}, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    root.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    subparsers = root.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build deterministic local vectors")
    build.add_argument("--dimension", type=int, default=1536)
    build.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    build.set_defaults(handler=command_build)

    validate = subparsers.add_parser("validate", help="run corpus and vector quality checks")
    validate.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    validate.set_defaults(handler=command_validate)

    search = subparsers.add_parser("search", help="hybrid-search the local index")
    search.add_argument("query")
    search.add_argument("--route", default="SIMPLE_LOOKUP")
    search.add_argument("--domain")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--min-score", type=float, default=0.04)
    search.add_argument("--json", action="store_true")
    search.set_defaults(handler=command_search)

    get = subparsers.add_parser("get", help="retrieve one chunk by canonical key")
    get.add_argument("canonical_key")
    get.add_argument("--route", default="SIMPLE_LOOKUP")
    get.set_defaults(handler=command_get)

    stats = subparsers.add_parser("stats", help="show corpus and index statistics")
    stats.set_defaults(handler=command_stats)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

