"""승인된 고정 SSM 문서만 호출한다. 작성자: 김진우."""
import json
import os
import re
import subprocess
import time


def aws(*args):
    result = subprocess.run(["aws", *args, "--region", "ap-northeast-2", "--output", "json", "--no-cli-pager"],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def main():
    digest = os.environ["DEPLOY_DIGEST"]
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("다이제스트 형식을 확인해 주세요.")
    result = aws("ssm", "send-command", "--document-name", "heapy-fastapi-dev-deploy",
                 "--document-version", "$DEFAULT", "--instance-ids", "i-055b8632e5b93fd96",
                 "--parameters", json.dumps({"ImageDigest": [digest]}), "--timeout-seconds", "900",
                 "--comment", "HEAPY FastAPI dev deployment")
    command = result["Command"]["CommandId"]
    print("배포 명령:", command)
    for _ in range(100):
        time.sleep(10)
        result = aws("ssm", "get-command-invocation", "--command-id", command,
                     "--instance-id", "i-055b8632e5b93fd96")
        status = result["Status"]
        if status == "Success":
            print("FastAPI 배포 및 컨테이너 준비 확인 성공:", digest)
            return
        if status not in {"Pending", "InProgress", "Delayed"}:
            # 작성자: 김진우 — 원격 출력이나 애플리케이션 로그를 Actions에 복제하지 않는다.
            raise RuntimeError("FastAPI 배포 실패: " + status + ". SSM 명령 상태를 확인해 주세요.")
    raise RuntimeError("배포 확인 시간 초과. 재실행 전 원격 명령 상태를 확인해 주세요.")


if __name__ == "__main__":
    main()
