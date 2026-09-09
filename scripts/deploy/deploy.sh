#!/usr/bin/env bash
# 작성자: 김진우 — FastAPI만 교체하며 백엔드·Nginx·공유 DB를 변경하지 않는다.
set -Eeuo pipefail
APP=heapy-fastapi
BACKUP=heapy-fastapi-rollback
REGISTRY=577638373354.dkr.ecr.ap-northeast-2.amazonaws.com
ENV_FILE=/opt/heapy/fastapi.env
IMAGE_DIGEST=${SSM_ImageDigest:?다이제스트가 필요합니다.}
[[ "$IMAGE_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]
exec 9>/var/lock/heapy-fastapi-deploy.lock
flock -n 9 || { echo '이미 배포 중입니다.' >&2; exit 1; }
test -f "$ENV_FILE"
test "$(stat -c '%a' "$ENV_FILE")" = 600
test "$(stat -c '%u' "$ENV_FILE")" = 0
test "$(df -Pm / | awk 'NR==2 {print $4}')" -ge 6000
test "$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)" -ge 1400000
# 임의 명령·환경 파일 경로·외부 이미지·호스트 포트는 매개변수로 받지 않는다.
docker network inspect heapy-app >/dev/null 2>&1 || docker network create heapy-app >/dev/null
if docker container inspect "$BACKUP" >/dev/null 2>&1; then
  echo '이전 복원 컨테이너를 먼저 점검해 주세요.' >&2
  exit 1
fi
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
docker pull "$REGISTRY/heapy-fastapi@$IMAGE_DIGEST" >/dev/null
HAD_PREVIOUS=0
CHANGING=0
healthy() {
  for attempt in $(seq 1 90); do
    if [[ "$(docker inspect --format '{{.State.Health.Status}}' "$APP" 2>/dev/null)" == healthy ]]; then
      return 0
    fi
    sleep 3
  done
  return 1
}
rollback() {
  code=$?
  trap - EXIT
  if [[ "$CHANGING" == 1 ]]; then
    docker rm -f "$APP" >/dev/null 2>&1 || true
    if [[ "$HAD_PREVIOUS" == 1 ]]; then
      if docker rename "$BACKUP" "$APP" && docker start "$APP" >/dev/null && healthy; then
        echo '이전 FastAPI 복구 완료.' >&2
      else
        echo 'FastAPI 복구 실패: 운영자 확인 필요.' >&2
      fi
    fi
    exit 1
  fi
  exit "$code"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if docker container inspect "$APP" >/dev/null 2>&1; then
  docker rename "$APP" "$BACKUP"
  HAD_PREVIOUS=1
  CHANGING=1
  docker stop --time 30 "$BACKUP" >/dev/null
else
  CHANGING=1
fi
docker run -d --name "$APP" --network heapy-app --network-alias heapy-fastapi \
  --restart unless-stopped --user 10001:10001 --read-only \
  --tmpfs /tmp:rw,nosuid,noexec,size=128m --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 1600m --memory-swap 1600m \
  --cpus 1 --pids-limit 128 --log-opt max-size=5m --log-opt max-file=2 \
  --env-file "$ENV_FILE" "$REGISTRY/heapy-fastapi@$IMAGE_DIGEST" >/dev/null
healthy
CHANGING=0
if [[ "$HAD_PREVIOUS" == 1 ]]; then
  docker rm "$BACKUP" >/dev/null
fi
echo "FastAPI 배포 및 준비 상태 확인 완료: $IMAGE_DIGEST"
