# run.sh 쌍따옴표 매칭 오류 수정 (2026-04-13)

## 문제
`run.sh` 실행 시 `unexpected EOF while looking for matching '"'` 에러 발생.

## 원인
CLI 인자(`--model ...`) 전달 시 `mlx-server serve` 명령어가 자동으로 추가되지 않아 `mlx-server`가 인자를 올바르게 해석하지 못함.

## 수정 사항
`run.sh` 43-55번째 줄 수정:

```bash
if [[ $# -gt 0 ]]; then
    echo "[Mode] CLI Arguments provided. Using: $*"
    # Auto-insert 'serve' command if not present
    if [[ "$1" == "--" || "$1" == -* ]]; then
        uv run mlx-server serve "$@"
    else
        uv run mlx-server "$@"
    fi
    exit_code=$?
    exit $exit_code
fi
```

## 검증
- `bash -n run.sh` 구문 검사 통과
- `run.sh --help` 실행 정상
- `run.sh --model "..."` 실행 정상
- `uv run pytest` 4/4 테스트 통과
