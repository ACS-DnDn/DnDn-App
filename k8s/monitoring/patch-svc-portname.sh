#!/bin/bash
# ServiceMonitor는 named port가 필요합니다.
# 기존 서비스에 포트 이름(http)을 추가하는 패치입니다.

echo "==> dndn-api 포트 이름 추가"
kubectl patch svc dndn-api -n dndn-api \
  --type='json' \
  -p='[{"op":"add","path":"/spec/ports/0/name","value":"http"}]'

echo "==> dndn-report 포트 이름 추가"
kubectl patch svc dndn-report -n dndn-report \
  --type='json' \
  -p='[{"op":"add","path":"/spec/ports/0/name","value":"http"}]'

echo "완료"
