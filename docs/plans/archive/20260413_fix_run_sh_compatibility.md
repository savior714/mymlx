# 구현 계획: run.sh macOS Bash 호환성 수정

## 1. 개요
현재 `run.sh`는 `mapfile` 명령어를 사용하여 모델 목록을 배열로 로드합니다. 그러나 macOS의 기본 Bash 버전인 3.2에는 `mapfile`이 포함되어 있지 않아 실행 중 오류가 발생합니다. 이를 전형적인 `for` 루프 방식으로 교체하여 호환성을 확보합니다.

## 2. 변경 사항
- **Target**: `run.sh`
- **수정 내용**: 
    - `mapfile -t models < <(...)` 구문을 `for` 루프와 `models+=()` 구문으로 변경.
    - 불필요한 `ls` 및 `xargs basename` 파이프라인을 제거하고 셸 글로빙 및 `basename` 호출로 단순화.

## 3. 작업 절차
1. `run.sh` 파일의 모델 목록 생성 로직(Line 37)을 수정합니다.
2. `docs/memory/project_changelog.md`에 버그 수정 내역을 기록합니다.
3. 사용자가 `./run.sh`를 다시 실행하도록 안내합니다.

## 4. 기대 결과
- macOS 기본 터미널 환경에서 오류 없이 대화형 모델 선택 화면이 출력됩니다.
- 비정상적인 파이프 중단(`signal 13`) 현상이 해결됩니다.
