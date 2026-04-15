#!/usr/bin/env python3
"""
Self-Enhancing System: 피드백 루프 자동화 스크립트

사용법:
    python scripts/feedback_processor.py --input "피드백 내용" [--type behavioral]
    python scripts/feedback_processor.py --detect --path "파일 경로"

기능:
1. docs/memory/feedback_*.md 생성
2. docs/memory/MEMORY.md 링크 갱신
3. docs/memory/BEHAVIORAL_GUARDRAILS.md 자동 반영
4. 정적 분석 기반 위반 감지
"""

import argparse
import os
import re
from datetime import datetime
from pathlib import Path


# 상수
MEMORY_DIR = Path("docs/memory")
FEEDBACK_DIR = MEMORY_DIR / "feedback"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
BEHAVIORAL_GUARDRAILS = MEMORY_DIR / "BEHAVIORAL_GUARDRAILS.md"


def ensure_directories():
    """필요한 디렉토리 생성"""
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)


def generate_feedback_filename(title: str) -> str:
    """피드백 파일명 생성: feedback_[YYYYMMDD]_[title].md"""
    date_str = datetime.now().strftime("%Y%m%d")
    # 제목에서 특수문자 제거 및 공백을 언더바로
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().lower().replace(' ', '_')
    return f"feedback_{date_str}_{safe_title}.md"


def create_feedback_file(title: str, content: str, feedback_type: str = "behavioral"):
    """피드백 파일 생성"""
    ensure_directories()
    
    filename = generate_feedback_filename(title)
    filepath = FEEDBACK_DIR / filename
    
    # 메타 정보
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 파일 내용
    file_content = f"""# Feedback: {title}

## §1. 메타 정보
- **Last Verified**: {today}
- **Type**: {feedback_type}
- **Source**: user
- **Created**: {today}

## §2. 피드백 내용
{content}

## §3. 적용 결과
- **BEHAVIORAL_GUARDRAILS.md**: pending
- **MEMORY.md**: pending
- **적용 일자**: {today}
"""
    
    filepath.write_text(file_content)
    print(f"✅ 피드백 파일 생성: {filepath}")
    return filepath


def update_memory_index(feedback_path: Path):
    """MEMORY.md에 피드백 링크 추가"""
    if not MEMORY_INDEX.exists():
        print(f"⚠️ MEMORY.md가 존재하지 않습니다: {MEMORY_INDEX}")
        return
    
    # 기존 내용 읽기
    content = MEMORY_INDEX.read_text()
    
    # 피드백 파일명 추출
    filename = feedback_path.name
    title = feedback_path.stem.replace('feedback_', '').replace('_', ' ').title()
    
    # 링크 형식: - **[Title]**: `docs/memory/feedback/{filename}`
    new_link = f"- **[{title}]**: `docs/memory/feedback/{filename}`"
    
    # §2. Memory Modules 섹션 찾기
    section_pattern = r'(## §2\. Memory Modules \(SSOT\)\n)'
    match = re.search(section_pattern, content)
    
    if match:
        insert_pos = match.end()
        # 기존 링크 중복 체크
        if filename not in content:
            new_content = content[:insert_pos] + f"{new_link}\n" + content[insert_pos:]
            MEMORY_INDEX.write_text(new_content)
            print(f"✅ MEMORY.md 갱신: {new_link}")
        else:
            print(f"⚠️ 이미 존재하는 링크: {filename}")
    else:
        print("⚠️ MEMORY.md에 §2. Memory Modules 섹션을 찾을 수 없습니다")


def update_behavioral_guardrails(feedback_path: Path):
    """BEHAVIORAL_GUARDRAILS.md에 피드백 내용 반영"""
    if not BEHAVIORAL_GUARDRAILS.exists():
        print(f"⚠️ BEHAVIORAL_GUARDRAILS.md가 존재하지 않습니다: {BEHAVIORAL_GUARDRAILS}")
        return
    
    # 피드백 내용 읽기
    content = feedback_path.read_text()
    
    # 피드백 내용 추출 (## §2. 피드백 내용 뒤의 내용)
    match = re.search(r'## §2\. 피드백 내용\s*\n(.+?)(?=## §3|\Z)', content, re.DOTALL)
    if not match:
        print("⚠️ 피드백 내용을 찾을 수 없습니다")
        return
    
    feedback_text = match.group(1).strip()
    
    # BEHAVIORAL_GUARDRAILS에 추가할 섹션
    today = datetime.now().strftime("%Y-%m-%d")
    new_section = f"""
## [{today}] {feedback_path.stem.replace('_', ' ').title()}

> [!NOTE]
> 이 섹션은 피드백 루프를 통해 자동 생성되었습니다.

{feedback_text}
"""
    
    # 기존 내용에 추가
    existing = BEHAVIORAL_GUARDRAILS.read_text()
    # §3. 수칙 준수 검증 섹션 앞에 삽입
    insert_marker = "## 🛠️ 수칙 준수 검증 (Behavioral Verification)"
    
    if insert_marker in existing:
        pos = existing.find(insert_marker)
        new_content = existing[:pos] + new_section + "\n" + existing[pos:]
        BEHAVIORAL_GUARDRAILS.write_text(new_content)
        print(f"✅ BEHAVIORAL_GUARDRAILS.md 업데이트")
    else:
        print("⚠️ BEHAVIORAL_GUARDRAILS.md에 검증 섹션을 찾을 수 없습니다")


def main():
    parser = argparse.ArgumentParser(description="피드백 루프 자동화 스크립트")
    parser.add_argument("--input", "-i", required=True, help="피드백 내용")
    parser.add_argument("--title", "-t", default="새로운 피드백", help="피드백 제목")
    parser.add_argument("--type", "-y", default="behavioral", 
                       choices=["behavioral", "process", "workflow"],
                       help="피드백 타입")
    
    args = parser.parse_args()
    
    print(f"📝 피드백 처리 시작: {args.title}")
    
    # 1. 피드백 파일 생성
    feedback_path = create_feedback_file(args.title, args.input, args.type)
    
    # 2. MEMORY.md 갱신
    update_memory_index(feedback_path)
    
    # 3. BEHAVIORAL_GUARDRAILS.md 업데이트
    update_behavioral_guardrails(feedback_path)
    
    print("\n✅ 피드백 루프 완료!")


# === 위반 감지 기능 ===

VIOLATION_PATTERNS = {
    "planner_violation": {
        "patterns": [r"docs/plans/.*\.md"],
        "violation": "#1 SDD 설계 문서화",
        "message": "docs/plans/ 외부에 계획 문서가 생성되었습니다"
    },
    "docs_first_violation": {
        "patterns": [r"TODO:\s*docs", r"FIXME:\s*specs"],
        "violation": "#2 Docs-First",
        "message": "문서화가 TODO/FIXME로 남아 있습니다"
    },
    "language_violation": {
        "patterns": [r"#[A-Z][a-z]+\s+[A-Z][a-z]+"],
        "violation": "#4 Language",
        "message": "영문 주석/문서가 감지되었습니다"
    },
    "memory_drift": {
        "patterns": [r"200"],
        "violation": "#3 Memory Density",
        "message": "MEMORY.md가 200라인을 초과할 수 있습니다"
    }
}


def detect_violations(file_path: str) -> list:
    """
    정적 분석 기반 위반 감지
    
    Args:
        file_path: 감지할 파일 경로
        
    Returns:
        감지된 위반 목록
    """
    violations = []
    
    try:
        content = Path(file_path).read_text()
    except Exception as e:
        print(f"⚠️ 파일 읽기 실패: {file_path} ({e})")
        return violations
    
    for violation_type, config in VIOLATION_PATTERNS.items():
        for pattern in config["patterns"]:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append({
                    "type": violation_type,
                    "violation": config["violation"],
                    "message": config["message"],
                    "file": file_path
                })
    
    return violations


def create_violation_feedback(violations: list) -> Path:
    """
    감지된 위반을 피드백 파일로 생성
    
    Args:
        violations: 감지된 위반 목록
        
    Returns:
        생성된 피드백 파일 경로
    """
    if not violations:
        return None
    
    today = datetime.now().strftime("%Y-%m-%d")
    hash_str = datetime.now().strftime("%H%M%S")
    title = f"위반_감지_{hash_str}"
    
    content = f"""# Feedback: 위반 감지 - {today}

## §1. 메타 정보
- **Last Verified**: {today}
- **Type**: violation
- **Source**: system
- **Created**: {today}

## §2. 감지된 위반
"""
    
    for v in violations:
        content += f"""
- **위반 유형**: {v["type"]}
- **위반 수칙**: {v["violation"]}
- **위반 내용**: {v["message"]}
- **파일 위치**: {v["file"]}
"""
    
    content += f"""
## §3. 해결 방안
- **수정 제안**: 위반된 수칙을 준수하도록 수정
- **우선순위**: High

## §4. 적용 결과
- **BEHAVIORAL_GUARDRAILS.md**: pending
- **MEMORY.md**: pending
- **적용 일자**: {today}
"""
    
    return create_feedback_file(title, content, "violation")


def detect_command(args):
    """--detect 옵션 처리"""
    if not args.path:
        print("⚠️ --path 옵션이 필요합니다")
        return
    
    violations = detect_violations(args.path)
    
    if violations:
        print(f"⚠️ {len(violations)}개 위반 감지:")
        for v in violations:
            print(f"  - {v['violation']}: {v['message']} ({v['file']})")
        
        # 피드백 파일 생성
        feedback_path = create_violation_feedback(violations)
        if feedback_path:
            update_memory_index(feedback_path)
            update_behavioral_guardrails(feedback_path)
            print(f"✅ 자동 보고 생성: {feedback_path}")
    else:
        print("✅ 위반 없음")


def main():
