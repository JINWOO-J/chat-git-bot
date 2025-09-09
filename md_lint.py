#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import fnmatch
import json
import os
import re
import sys
import urllib.parse
import http.client
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict




CODE_FENCE_PAT = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
HEADING_PAT = re.compile(r"^(#{1,6})\s*(.*)$")
LINK_PAT = re.compile(r"!?\[([^\]]*)\]\(([^)]+)\)")
INLINE_CODE_PAT = re.compile(r"`[^`]*`")
TRAILING_SPACE_PAT = re.compile(r"[ \t]+$")
LIST_MARKER_PAT = re.compile(r"^(\s*)([-+*]|\d+\.)\s+")
TABLE_LINE_PAT = re.compile(r"^\s*\|.*\|\s*$")
CRLF_PAT = re.compile(r"\r\n")



@dataclass
class Issue:
    file: str
    line: int
    col: int
    code: str
    message: str
    context: str

def get_md_files(path: str) -> List[str]:
    if os.path.isdir(path):
        return [os.path.join(path, f) for f in os.listdir(path) if is_markdown_file(f)]
    return [path]

def is_ignored(path: str, ignore_patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in ignore_patterns)

def is_markdown_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in {".md", ".markdown", ".mdown", ".mkdn"}

def iter_md_files(paths: List[str], ignore_patterns: List[str]) -> List[str]:
    found = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                # 숨김 폴더는 기본적으로 무시
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in files:
                    full = os.path.join(root, f)
                    if any(fnmatch.fnmatch(full, pat) for pat in ignore_patterns):
                        continue
                    if is_markdown_file(full):
                        found.append(full)
        else:
            if any(fnmatch.fnmatch(p, pat) for pat in ignore_patterns):
                continue
            if is_markdown_file(p):
                found.append(p)
    return sorted(set(found))

def check_file(path: str, max_len: int, check_links: bool) -> List[Issue]:
    issues: List[Issue] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception as e:
        issues.append(Issue(path, 0, 0, "E-READ", f"파일을 열 수 없습니다: {e}", ""))
        return issues

    # CRLF 경고
    if CRLF_PAT.search(raw):
        issues.append(Issue(path, 1, 1, "W-CRLF", "윈도우 CRLF 줄바꿈 감지(가능하면 LF 권장).", ""))

    # 마지막 개행
    if not raw.endswith("\n"):
        issues.append(Issue(path, 0, 0, "W-NOEOFNL", "파일 끝에 개행(Newline)이 없습니다.", ""))

    lines = raw.splitlines()
    in_fence = False
    fence_marker = None
    fence_indent = ""
    last_heading_level = 0
    seen_h1 = False

    # 테이블 블록 추적
    table_block_pipe_counts: List[int] = []

    for i, orig_line in enumerate(lines, start=1):
        line = orig_line

        # 코드 블록(펜스) 추적
        m_f = CODE_FENCE_PAT.match(line)
        if m_f:
            indent, marker, info = m_f.groups()
            if not in_fence:
                in_fence = True
                fence_marker = marker[0]  # ` 또는 ~
                fence_indent = indent
            else:
                # 닫힘은 같은 문자여야 함
                if marker[0] == fence_marker and indent == fence_indent:
                    in_fence = False
                    fence_marker = None
                    fence_indent = ""
            # 코드 펜스 라인은 다른 검사 대부분 제외
            continue

        # 코드 블록 안은 스킵(트레일링 공백만 검사)
        if in_fence:
            if TRAILING_SPACE_PAT.search(line):
                issues.append(Issue(path, i, len(line), "W-TRAIL", "코드블록 내 트레일링 공백.", line[-40:]))
            continue

        # 트레일링 공백
        if TRAILING_SPACE_PAT.search(line):
            issues.append(Issue(path, i, len(line), "W-TRAIL", "트레일링 공백.", line[-40:]))

        # 과도한 빈 줄(3줄 이상 연속)
        if i >= 3 and lines[i-2].strip() == "" and lines[i-1].strip() == "" and line.strip() == "":
            issues.append(Issue(path, i, 1, "W-MULTIBLANK", "빈 줄이 2줄 초과로 연속됩니다.", ""))

        # 줄 길이
        logical_line = INLINE_CODE_PAT.sub("", line)  # 인라인 코드 제외한 길이로 판단
        if len(logical_line) > max_len:
            issues.append(Issue(path, i, max_len+1, "W-LINELEN", f"줄 길이 {len(logical_line)} > {max_len}.", line[:max_len+20]))

        # 탭 사용
        if "\t" in line:
            issues.append(Issue(path, i, line.index("\t")+1, "W-TAB", "탭 문자가 감지되었습니다(스페이스 권장).", line.replace("\t", "\\t")[:80]))

        # 헤딩 검사
        m_h = HEADING_PAT.match(line)
        if m_h:
            hashes, text = m_h.groups()
            # '#' 뒤 공백
            if not line.startswith(hashes + " "):
                issues.append(Issue(path, i, len(hashes)+1, "E-HEADSPACE", "헤딩의 '#' 다음에는 공백이 필요합니다.", line[:80]))

            level = len(hashes)
            if text.strip() == "":
                issues.append(Issue(path, i, len(hashes)+2, "E-EMPTYHEAD", "빈 헤딩 텍스트.", line[:80]))

            # H1 중복
            if level == 1:
                if seen_h1:
                    issues.append(Issue(path, i, 1, "W-MULTIH1", "문서 내 H1 헤딩이 2개 이상입니다.", line[:80]))
                seen_h1 = True

            # 레벨 점프(2 이상)
            if last_heading_level and (level - last_heading_level) > 1:
                issues.append(Issue(path, i, 1, "W-HEADJUMP", f"헤딩 레벨이 {last_heading_level}→{level}로 2 이상 점프.", line[:80]))
            last_heading_level = level

        # 링크/이미지 문법
        for lm in LINK_PAT.finditer(line):
            text, url = lm.groups()
            is_image = line[lm.start()] == "!"
            if not text.strip():
                code = "E-NOALTTEXT" if is_image else "W-EMPTYLINKTEXT"
                msg = "이미지의 대체텍스트(alt)가 비어 있습니다." if is_image else "링크 텍스트가 비어 있습니다."
                issues.append(Issue(path, i, lm.start()+1, code, msg, line[:120]))
            if not url.strip():
                issues.append(Issue(path, i, lm.start()+1, "E-EMPTYURL", "링크/이미지 URL이 비어 있습니다.", line[:120]))

            # 잘못된 스킴
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme and parsed.scheme not in {"http", "https", "mailto"}:
                issues.append(Issue(path, i, lm.start()+1, "W-SCHEME", f"비표준/의도치 않은 스킴 '{parsed.scheme}'.", url[:120]))

        # 테이블 파이프 검사: 연속 테이블 블록에서 파이프 수 일관성
        if TABLE_LINE_PAT.match(line):
            pipes = line.count("|")
            if not table_block_pipe_counts:
                table_block_pipe_counts.append(pipes)
            else:
                table_block_pipe_counts.append(pipes)
            # 구분선 라인(| --- | --- |)은 대략 허용. 그래도 파이프 개수만 맞으면 OK
        else:
            if table_block_pipe_counts:
                # 블록 종료 시 검사
                exp = max(set(table_block_pipe_counts), key=table_block_pipe_counts.count)
                for j, cnt in enumerate(table_block_pipe_counts):
                    if cnt != exp:
                        issues.append(Issue(path, i, 1, "W-TABLEPIPES", f"테이블 블록의 파이프 수 불일치(기대 {exp}, 실제 {cnt}).", ""))
                table_block_pipe_counts = []

        # 목록 들여쓰기 스타일
        m_list = LIST_MARKER_PAT.match(line)
        if m_list:
            indent = m_list.group(1)
            if "\t" in indent:
                issues.append(Issue(path, i, 1, "W-LISTTAB", "목록 들여쓰기에 탭 사용.", line[:80]))

    # 파일 끝에서 열린 코드펜스
    if in_fence:
        issues.append(Issue(path, len(lines), 1, "E-FENCE", "열린 코드 펜스가 닫히지 않았습니다.", ""))

    # 마지막 테이블 블록이 열린 채 종료되었을 때 검사
    if table_block_pipe_counts:
        exp = max(set(table_block_pipe_counts), key=table_block_pipe_counts.count)
        for j, cnt in enumerate(table_block_pipe_counts):
            if cnt != exp:
                issues.append(Issue(path, len(lines), 1, "W-TABLEPIPES", f"테이블 블록의 파이프 수 불일치(기대 {exp}, 실제 {cnt}).", ""))




    # 선택적: 외부 링크 HEAD 검사
    if check_links:
        issues.extend(check_http_links(path, lines))

    return issues

def check_http_links(path: str, lines: List[str]) -> List[Issue]:
    issues: List[Issue] = []
    for i, line in enumerate(lines, start=1):
        for lm in LINK_PAT.finditer(line):
            url = lm.group(2)
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                continue
            host = parsed.netloc
            if not host:
                continue
            try:
                conn: http.client.HTTPConnection | http.client.HTTPSConnection
                if parsed.scheme == "http":
                    conn = http.client.HTTPConnection(host, timeout=5)
                else:
                    conn = http.client.HTTPSConnection(host, timeout=5)
                path_q = parsed.path or "/"
                if parsed.query:
                    path_q += "?" + parsed.query
                conn.request("HEAD", path_q, headers={"User-Agent": "md-lint/1.0"})
                resp = conn.getresponse()
                if resp.status >= 400:
                    issues.append(Issue(path, i, lm.start()+1, "W-LINK", f"링크 상태 코드 {resp.status} ({resp.reason}).", url))
                conn.close()
            except Exception as e:
                issues.append(Issue(path, i, lm.start()+1, "W-LINKERR", f"링크 검사 실패: {e}", url))
    return issues

def main():
    parser = argparse.ArgumentParser(description="단순 마크다운 검증/린트 스크립트")
    parser.add_argument("paths", nargs="+", help="검사할 파일/디렉터리 경로")
    parser.add_argument("--ignore", action="append", default=[], help="무시할 글롭 패턴 (여러 번 지정 가능)")
    parser.add_argument("--max-line-length", type=int, default=120, help="허용 줄 길이(기본 120)")
    parser.add_argument("--check-links", action="store_true", help="HTTP(S) 링크에 대해 HEAD 요청으로 확인(느릴 수 있음)")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 결과 출력")
    args = parser.parse_args()

    files = iter_md_files(args.paths, args.ignore)
    all_issues: List[Issue] = []
    for f in files:
        all_issues.extend(check_file(f, args.max_line_length, args.check_links))

    if args.json:
        payload = [asdict(x) for x in all_issues]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for iss in all_issues:
            loc = f"{iss.file}:{iss.line}:{iss.col}"
            print(f"{loc}\t{iss.code}\t{iss.message}")
            if iss.context:
                print(f"  ↳ {iss.context}")

        print(f"\n검사 파일: {len(files)}개, 발견된 문제: {len(all_issues)}개")

    # 문제가 있으면 1로 종료
    sys.exit(1 if all_issues else 0)

if __name__ == "__main__":
    main()
