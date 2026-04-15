# Knowledge: apply_diff 안전 가이드라인

## §1. 메타 정보
- **Last Verified**: 2026-04-15
- **Author**: mlx-server Team
- **Created**: 2026-04-13
- **Category**: Tool Usage Safety

## §2. 문제 정의

### 2.1 apply_diff의 엄격한 일치 요구
`apply_diff` 도구는 **정확한 100% 일치**를 요구하며, 아래 조건 중 하나라도 충족하면 에러가 발생합니다:

| 에러 유형 | 원인 | 예시 |
|-----------|------|------|
| `No sufficiently similar match` | 검색 내용과 실제 파일 내용이 다름 | "설정 저장/로드" vs "이전 값 자동 적용" |
| `Search and replace content are identical` | 검색/대체 내용이 동일 | 변경 사항이 없음 |
| `No match found` | 줄 번호 오류 또는 내용 불일치 | 파일이 변경된 후 재사용 |

### 2.2 주요 에러 사례
```
No sufficiently similar match found at line: 5 (94% similar, needs 100%)
- Similarity Score: 94%
- Required Threshold: 100%
```

## §3. 안전 가이드라인

### 3.1 5단 체크 프로토콜
`apply_diff` 사용 전 **반드시** 아래 체크리스트를 수행:

1. **[체크1] 파일 존재 확인**: `list_files` 또는 `read_file`으로 파일 존재 확인
2. **[체크2] 최신 내용 읽기**: `read_file`으로 **정확한 줄 번호** 확인
3. **[체크3] 정확한 일치 검증**: 검색 내용과 실제 내용이 **문자 단위로 동일**한지 확인
4. **[체크4] 변경 여부 확인**: 검색/대체 내용이 **실제로 다름**을 확인
5. **[체크5] 줄 번호 정확성**: `start_line`이 **정확한 시작 줄**인지 확인

### 3.2 줄 번호 추적 규칙
```
파일 내용:
 1 | # Header
 2 |
 3 | ## Section
 4 | - Item A
 5 | - Item B  ← start_line: 5
 6 | - Item C
```

- **`start_line`은 검색 내용의 첫 줄 번호**
- **공백/빈 줄도 줄 번호에 포함**
- **한 줄이라도 내용이 다르면 100% 일치 불가**

### 3.3 Diff 작성 패턴
```markdown
<<<<<<< SEARCH
:start_line:5
- **Active Task**: run.sh 설정 저장/로드 버그 수정 및 인터페이스 개선 완료 ([@2026-04-13])
=======
- **Active Task**: run.sh 이전 값 자동 적용 기능 구현 완료 ([@2026-04-13])
>>>>>>> REPLACE
```

**규칙**:
- `=======` 위: **현재 파일의 실제 내용**
- `=======` 아래: **수정 후 원하는 내용**
- **한 줄이라도 다르면 에러**

### 3.4 파일 변경 감지 프로토콜
파일을 수정한 후 **반드시** 다음 절차를 따른다:

1. `read_file`으로 **최신 내용 재확인**
2. **기존 diff 재사용 금지** → **새로운 diff 작성**
3. `start_line`이 **정확한 위치**인지 재검증

> **경고**: 이전에 실패한 diff는 **파일 변경 후 재사용 금지**

## §4. 에러 복구 절차

### 4.1 에러 발생 시 대응
```
에러: No sufficiently similar match found at line: 5
```

**복구 절차**:
1. `read_file`으로 파일 최신 내용 확인
2. 에러 메시지의 "Best Match Found" 확인
3. **유사도 94%** → **6% 차이** → 실제 내용과 비교
4. **정확한 내용으로 diff 재작성**

### 4.2 복구 예시
```bash
# 1. 최신 내용 확인
read_file(path="docs/memory/MEMORY.md", mode="slice", offset=1, limit=10)

# 2. 실제 내용 확인
5 | - **Active Task**: run.sh 이전 값 자동 적용 기능 구현 완료 ([@2026-04-13])

# 3. 정확한 diff 작성
<<<<<<< SEARCH
:start_line:5
- **Active Task**: run.sh 이전 값 자동 적용 기능 구현 완료 ([@2026-04-13])
=======
- **Active Task**: run.sh 설정 저장/로드 버그 수정 및 인터페이스 개선 완료 ([@2026-04-13])
>>>>>>> REPLACE
```

## §5. 프로젝트 적용

### 5.1 적용 위치
- **대상 파일**: `docs/memory/MEMORY.md`, `docs/memory/project_changelog.md`
- **적용 도구**: `apply_diff`
- **적용 시점**: 세션 중 파일 수정 시

### 5.2 관련 문서
- [`docs/memory/MEMORY.md`](docs/memory/MEMORY.md)
- [`docs/memory/project_changelog.md`](docs/memory/project_changelog.md)
- [`docs/knowledge/apply_diff_escape_rules.md`](docs/knowledge/apply_diff_escape_rules.md)

## §6. 체크리스트 (최종 확인)

`apply_diff` 사용 전 **반드시** 아래를 확인:

- [ ] `read_file`으로 최신 내용 확인
- [ ] 검색 내용과 실제 내용이 **100% 일치**
- [ ] `start_line`이 **정확한 시작 줄**
- [ ] 검색/대체 내용이 **실제로 다름**
- [ ] 이전 실패 diff는 **재사용하지 않음**
