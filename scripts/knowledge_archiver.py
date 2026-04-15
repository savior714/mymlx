#!/usr/bin/env python3
"""
Self-Enhancing System: 지식 자산화 자동화 스크립트

사용법:
    python scripts/knowledge_archiver.py --topic "mlx-lm API" --url "https://example.com" --content "..."

기능:
1. docs/knowledge/ 디렉토리 생성
2. docs/knowledge/{topic}.md 생성
3. docs/memory/MEMORY.md 링크 갱신
"""

import argparse
import os
import re
from datetime import datetime
from pathlib import Path


# 상수
KNOWLEDGE_DIR = Path("docs/knowledge")
MEMORY_INDEX = Path("docs/memory/MEMORY.md")


def ensure_directories():
    """필요한 디렉토리 생성"""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)


def generate_knowledge_filename(topic: str) -> str:
    """지식 파일명 생성: [topic].md"""
    # 제목에서 특수문자 제거 및 공백을 언더바로
    safe_name = re.sub(r'[^\w\s-]', '', topic).strip().lower().replace(' ', '_')
    return f"{safe_name}.md"


def create_knowledge_file(topic: str, url: str, content: str):
    """지식 파일 생성"""
    ensure_directories()
    
    filename = generate_knowledge_filename(topic)
    filepath = KNOWLEDGE_DIR / filename
    
    # 메타 정보
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 파일 내용
    file_content = f"""# Knowledge: {topic}

## §1. 메타 정보
- **Last Verified**: {today}
- **Source**: {url}
- **Author**: system
- **Created**: {today}

## §2. 핵심 솔루션
{content}

## §3. 프로젝트 적용
- **적용 위치**: pending
- **적용 일자**: {today}
- **관련 문서**: pending
"""
    
    filepath.write_text(file_content)
    print(f"✅ 지식 파일 생성: {filepath}")
    return filepath


def update_memory_index(knowledge_path: Path):
    """MEMORY.md에 지식 링크 추가"""
    if not MEMORY_INDEX.exists():
        print(f"⚠️ MEMORY.md가 존재하지 않습니다: {MEMORY_INDEX}")
        return
    
    # 기존 내용 읽기
    content = MEMORY_INDEX.read_text()
    
    # 지식 파일명 추출
    filename = knowledge_path.name
    topic = knowledge_path.stem.replace('_', ' ').title()
    
    # 링크 형식: - **[Topic]**: `docs/knowledge/{filename}`
    new_link = f"- **[{topic}]**: `docs/knowledge/{filename}`"
    
    # §4. Information Index 섹션 찾기
    section_pattern = r'(## §4\. Information Index \(Shortcuts\)\n)'
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
        print("⚠️ MEMORY.md에 §4. Information Index 섹션을 찾을 수 없습니다")


def main():
    parser = argparse.ArgumentParser(description="지식 자산화 자동화 스크립트")
    parser.add_argument("--topic", "-t", required=True, help="주제 제목")
    parser.add_argument("--url", "-u", required=True, help="출처 URL")
    parser.add_argument("--content", "-c", required=True, help="핵심 솔루션 내용")
    
    args = parser.parse_args()
    
    print(f"📚 지식 아카이브 시작: {args.topic}")
    
    # 1. 지식 파일 생성
    knowledge_path = create_knowledge_file(args.topic, args.url, args.content)
    
    # 2. MEMORY.md 갱신
    update_memory_index(knowledge_path)
    
    print("\n✅ 지식 자산화 완료!")


if __name__ == "__main__":
    main()
