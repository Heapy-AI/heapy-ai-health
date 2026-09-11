"""Git 인덱스의 파일만으로 실행 소스를 구성하고 검증한다.

테스트 및 외부 서비스 호출 없이 컴파일, import, 타입 스키마,
정적 파일 참조와 소스 압축 패키지를 검증한다.
작성자: 김진우
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".local-dev" / "source-validation"


def git(*arguments: str) -> bytes:
    """현재 저장소의 인덱스를 읽는다. 작성자: 김진우."""
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
    )


def validate_assets(snapshot: Path) -> int:
    """화면별 정적 경로가 패키지에 존재하는지 확인한다. 작성자: 김진우."""
    count = 0
    for frontend in ("admin", "user"):
        base = snapshot / "app" / "frontends" / frontend
        for source in base.rglob("*"):
            if source.suffix not in {".html", ".css", ".js"}:
                continue
            content = source.read_text(encoding="utf-8")
            references = re.findall(r'''["'](/(?:assets|images)/[^"']+)["']''', content)
            for reference in references:
                path = urlsplit(reference).path
                if path.startswith("/images/"):
                    target = snapshot / "app/frontends/shared" / path.lstrip("/")
                else:
                    target = base / path.lstrip("/")
                if not target.is_file():
                    raise FileNotFoundError(f"정적 파일 누락: {source}: {reference}")
                count += 1
    return count


def main() -> None:
    """인덱스 스냅샷 검증 결과를 로컬 폴더에 저장한다. 작성자: 김진우."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in git("ls-files", "-z").decode().split("\0") if path)
    archive = OUTPUT / "heapy-source.zip"
    hashes: dict[str, str] = {}
    with ZipFile(archive, "w", ZIP_DEFLATED) as package:
        for path in files:
            content = git("show", f":{path}")
            hashes[path] = hashlib.sha256(content).hexdigest()
            package.writestr(path, content)
    with ZipFile(archive) as package:
        if package.testzip() is not None or sorted(package.namelist()) != files:
            raise RuntimeError("소스 압축 패키지 무결성 검증 실패")
        with tempfile.TemporaryDirectory(prefix="검증-", dir=OUTPUT) as temporary:
            snapshot = Path(temporary)
            package.extractall(snapshot)
            modules = []
            for path in files:
                if not path.endswith(".py"):
                    continue
                source = snapshot / path
                ast.parse(source.read_text(encoding="utf-8-sig"), filename=path)
                if path.startswith(("app/", "model/")) or path == "run_admin_ui.py":
                    modules.append(path[:-3].replace("/", ".").removesuffix(".__init__"))
            subprocess.run(
                [sys.executable, "-m", "compileall", "-q", str(snapshot)], check=True
            )
            javascript = [path for path in files if path.endswith(".js")]
            for path in javascript:
                subprocess.run(["node", "--check", str(snapshot / path)], check=True)
            asset_count = validate_assets(snapshot)
            environment = os.environ.copy()
            for key in tuple(environment):
                if key.startswith(("GOOGLE_", "GEMINI_", "SUPABASE_", "PINECONE_")):
                    environment.pop(key)
            environment.pop("PYTHONPATH", None)
            for key in ("RDB_DSN", "DATABASE_URL", "INTENT_MODEL_PATH"):
                environment.pop(key, None)
            environment.update(
                GOOGLE_API_KEY="local-validation-placeholder",
                PYTHONUTF8="1",
                PYTHON_DOTENV_DISABLED="1",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
            )
            # 스냅샷만 검색하며 비밀정보와 실제 외부 서비스를 사용하지 않는다.
            code = """
import importlib, json, pathlib, socket, sys
def deny_network(*args, **kwargs):
    raise RuntimeError('검증 중 외부 네트워크 호출은 허용하지 않습니다.')
socket.socket.connect = deny_network
socket.create_connection = deny_network
root = pathlib.Path.cwd().resolve()
for name in json.loads(sys.argv[1]):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(root), name
from app.core.config import ROOT, INTENT_MODEL_PATH
from app.services.intent_classifier import LinearIntentClassifier
assert ROOT == root
assert INTENT_MODEL_PATH.is_file()
for version in ('intent-v6', 'intent-v7'):
    LinearIntentClassifier.from_file(root / 'model/classifier/artifacts' / version / 'best_model.json', 0.55)
from app.main import app
from app.admin_frontend import app as admin_app
assert app.openapi()['paths']
assert admin_app.openapi()['info']
print('실제 모듈 import·모델 로드·API 타입 스키마 검증 완료')
"""
            subprocess.run(
                [sys.executable, "-c", code, json.dumps(sorted(set(modules)))],
                cwd=snapshot,
                env=environment,
                check=True,
            )
    result = {
        "추적_파일": len(files),
        "파이썬_파일": sum(path.endswith(".py") for path in files),
        "자바스크립트_파일": len(javascript),
        "정적_파일_참조": asset_count,
        "검증": "컴파일·문법·import·모델 로드·API 타입 스키마·소스 패키징 통과",
        "제한": "정적 타입 분석기와 단위·통합 테스트, 외부 서비스 실행은 포함하지 않음",
        "파일_SHA256": hashes,
    }
    (OUTPUT / "검증결과.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key != "파일_SHA256"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
