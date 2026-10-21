"""전사 내보내기 - 행 목록을 마크다운 한 장으로 (0.2.3).

무엇을 맡는가
    독이 모은 전사 행 목록을 마크다운 문자열로 조립하고, 고정 경로에 파일로
    쓴다. **Qt 를 import 하지 않는다** - 그래야 하네스가 위젯 없이 조립 결과를
    대조할 수 있고, 문자열 규칙(울타리 길이, 접힘 블록)을 UI 와 따로 잴 수 있다.

어디에 쓰는가 (QFileDialog 금지. 설계 3-5 금지 API 목록)
    `<QGIS 프로필>/upwise_chat/workspace/exports/transcript_<세션8자>_<시각>.md`
    사용자에게 저장 위치를 묻지 않는다. 모달도 파일 대화상자도 쓰지 않으므로
    고정 경로가 유일한 선택이고, 쓴 다음 경로를 비모달 바로 알린다.
    workspace 는 수집 산출물과 같은 뿌리다(skillbundle.profile_env_paths).

레다크션 (설계 docs/2 5-4)
    **조립한 본문 전체를 레다크터에 한 번 더 통과시킨 뒤 쓴다.** 행 글은 이미
    전사 렌더 시점에 치환됐지만(적용 지점 2), 레다크터가 붙기 **전에** 그려진
    행은 치환되지 않은 채 장부에 남아 있다(chat_view.set_redactor 의 비소급
    규약). 내보내기는 그 행까지 디스크로 복제하므로 쓰기 직전이 마지막 관문이
    된다. 즉 이 한 번은 중복이 아니라 새 유출면(L4 축의 파일)을 막는 것이다.

울타리 길이를 왜 계산하는가
    도구 결과 본문에 ``` 가 들어오는 일이 흔하다(모델이 코드를 설명한 결과,
    Read 도구가 읽은 마크다운). 세 겹 고정으로 감싸면 그 자리에서 블록이 닫혀
    뒤 본문이 전부 깨진다. 그래서 본문의 최장 백틱 연속보다 한 겹 긴 울타리를
    쓴다.

py3.9 호환: `Path.write_text(newline=...)` 는 3.10 신설이다(장부 V28-P20).
파일 쓰기는 `open(..., newline="")` 으로 한다.

설계 정본: docs/1.mvp_design_v1.md 3-5, 7-4 / docs/2 5-4
"""

import datetime as dt
import os

# 내보내기 폴더 이름. workspace 아래에 둔다 - 수집 산출물(collected)과 형제다.
EXPORT_SUBDIR = "exports"

# 파일명. 세션 앞 8자와 시각으로 한 세션에 여러 장을 구분한다.
FILENAME_TEMPLATE = "transcript_%s_%s.md"

# 파일명에 넣는 세션 식별자 길이. uuid 앞 8자면 사람이 로그의 session_ 파일과
# 짝지을 수 있고(로그북 jsonl 이 전체 uuid 를 쓴다) 파일명이 길어지지 않는다.
SESSION_SHORT_LEN = 8

# 백엔드가 아직 안 떴을 때의 세션 자리표시. 전사만 그린 상태에서도 내보내기가
# 되어야 한다 - 그 전사도 사용자가 읽은 글이다.
NO_SESSION = "nosession"

# 내보낸 마크다운의 머리글(U15). 사용자 노출 문구이므로 내부 용어를 쓰지
# 않는다 - 화면 버튼도 "대화 지우기"·"내보내기" 로 말한다.
EXPORT_TITLE = "# UPWISE Chat 대화"

# 역할 제목. 전사 위젯의 행 종류를 사람이 읽는 말로 옮긴다.
ROLE_TITLES = {
    "user": "나",
    "notice": "플러그인 공지",
    "assistant": "모델",
    "thinking": "생각",
}

# 접힘 블록 머리. 마크다운 뷰어가 details 를 접어 준다 - 도구 카드는 화면에서도
# 접혀 있으므로(설계 4-2) 내보낸 글의 기본 상태도 같아야 한다.
DETAILS_OPEN = "<details>"
DETAILS_SUMMARY = "<summary>%s</summary>"
DETAILS_CLOSE = "</details>"

# 코드 울타리 최소 겹수.
FENCE_MIN = 3


def session_short(session_id):
    """세션 식별자의 파일명용 짧은 형태.

    Args:
        session_id: `--session-id` 값. 빈 값이면 NO_SESSION.

    Returns:
        str: 앞 8자(영숫자와 하이픈만 남긴 값) 또는 NO_SESSION.
    """
    text = "" if session_id is None else str(session_id)
    kept = "".join(ch for ch in text if ch.isalnum() or ch == "-")
    if not kept:
        return NO_SESSION
    return kept[:SESSION_SHORT_LEN]


def export_dir(workspace):
    """내보내기 폴더 경로 문자열.

    Args:
        workspace: skillbundle.profile_env_paths()["workspace"].

    Returns:
        str: `<workspace>/exports`.
    """
    return os.path.join(str(workspace), EXPORT_SUBDIR)


def export_path(workspace, session_id, stamp=None):
    """내보낼 파일의 전체 경로.

    Args:
        workspace: 작업 폴더.
        session_id: 지금 세션 식별자. 없으면 NO_SESSION 이 들어간다.
        stamp: 파일명 시각 문자열. None 이면 지금 시각(`%y%m%d_%H%M%S`).

    Returns:
        str: 절대 또는 상대 경로(workspace 가 준 형태를 따른다).
    """
    stamp = stamp or dt.datetime.now().strftime("%y%m%d_%H%M%S")
    name = FILENAME_TEMPLATE % (session_short(session_id), stamp)
    return os.path.join(export_dir(workspace), name)


def fence_for(body):
    """본문을 감쌀 코드 울타리.

    본문 안의 최장 백틱 연속보다 한 겹 길게 만든다. 고정 3겹으로 감싸면 결과
    본문에 들어 있는 ``` 가 블록을 조기에 닫는다.

    Args:
        body: 감쌀 본문.

    Returns:
        str: 백틱 울타리 문자열.
    """
    longest = 0
    run = 0
    for ch in body or "":
        if ch == "`":
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    return "`" * max(FENCE_MIN, longest + 1)


def _code_block(label, body):
    """제목 한 줄 + 울타리 코드 블록 줄들.

    Args:
        label: 블록 위에 적을 말. 빈 값이면 제목을 생략한다.
        body: 블록 본문.

    Returns:
        list[str]: 줄 목록. 본문이 비면 빈 목록이다.
    """
    if not (body or "").strip():
        return []
    fence = fence_for(body)
    lines = []
    if label:
        lines.append("%s:" % label)
    lines.append(fence)
    lines.extend((body or "").rstrip("\n").split("\n"))
    lines.append(fence)
    return lines


def _hhmmss(ts):
    """epoch 초를 시:분:초 문자열로. 0 이나 None 이면 빈 문자열."""
    if not ts:
        return ""
    try:
        return dt.datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return ""


def _heading(row):
    """행 하나의 제목 줄.

    Args:
        row: export 행 dict.

    Returns:
        str: `### 나 (02:30:11)` 같은 한 줄.
    """
    title = row.get("title") or ""
    stamp = _hhmmss(row.get("ts"))
    if stamp:
        return "### %s (%s)" % (title, stamp)
    return "### %s" % title


def build_markdown(rows, meta=None):
    """행 목록을 마크다운 한 장으로 조립한다.

    형식
        머리글    제목 + 메타 불릿(세션, 내보낸 시각, 작업 폴더, 포스처, 행 수)
        턴 구분   `## 턴 N`
        말풍선    `### 나 (시각)` + 본문
        모델 블록 `### 모델 (시각)` + 본문
        생각 블록 `### 생각 (시각)` + 접힘 블록
        도구 카드 접힘 블록. 머리에 카드 제목(= 도구 이름과 상태), 안에 인자
                  전문과 결과 전문. 화면에서 접혀 있는 것과 같은 상태다

    Args:
        rows: ChatView.export_rows() 결과.
        meta: 머리글에 적을 (이름, 값) 쌍 목록. None 이면 생략한다.

    Returns:
        str: 마크다운 본문. 끝에 줄바꿈 하나가 붙는다.
    """
    # U15(0.3.x UI 패스 2차): 내보낸 파일의 머리글도 사용자가 읽는 글이다.
    # 상수로 올려 두는 이유는 하네스 28(E10·E3)이 이 문구를 단정하기 때문이다 -
    # 다음에 또 바뀌면 고칠 자리가 한 군데여야 한다.
    lines = [EXPORT_TITLE, ""]
    for name, value in (meta or ()):
        lines.append("- %s: %s" % (name, value))
    if meta:
        lines.append("")

    for row in rows or ():
        kind = row.get("kind")
        if kind == "separator":
            turn_no = row.get("turn_no")
            lines.extend(["---", "",
                          "## 턴 %s" % ("?" if turn_no is None else turn_no), ""])
            continue
        if kind == "card":
            # 카드는 접힘 하나로 묶는다. 머리에 제목만 보이고 인자/결과는 안에
            # 둔다 - 전문을 빼면 감사 경로가 끊기고, 펼친 채로 두면 도구가 많은
            # 세션에서 읽히지 않는다.
            lines.append(DETAILS_OPEN)
            lines.append(DETAILS_SUMMARY % ("%s %s" % (row.get("title") or "도구",
                                                       _hhmmss(row.get("ts")))).strip())
            lines.append("")
            lines.extend(_code_block("", row.get("body") or ""))
            lines.extend(_code_block("", row.get("detail") or ""))
            lines.append("")
            lines.append(DETAILS_CLOSE)
            lines.append("")
            continue
        if kind == "block" and row.get("block_kind") == "thinking":
            lines.append(_heading(row))
            lines.append("")
            lines.append(DETAILS_OPEN)
            lines.append(DETAILS_SUMMARY % "생각 전문")
            lines.append("")
            lines.extend(_code_block("", row.get("body") or ""))
            lines.append("")
            lines.append(DETAILS_CLOSE)
            lines.append("")
            continue
        lines.append(_heading(row))
        lines.append("")
        body = (row.get("body") or "").rstrip("\n")
        lines.append(body if body else "(빈 글)")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def write_markdown(path, body):
    """마크다운을 파일로 쓴다. 폴더가 없으면 만든다.

    `open(..., newline="")` 로 쓴다. `Path.write_text(newline=...)` 는 3.10
    신설이라 구판 번들 파이썬에서 TypeError 다(장부 V28-P20).

    Args:
        path: 쓸 경로.
        body: 파일 내용.

    Returns:
        int: 쓴 문자 수.

    Raises:
        OSError: 폴더 생성이나 쓰기가 실패하면 그대로 올린다. 호출자가
            사용자에게 알린다 - 조용히 삼키면 "저장됐다" 가 거짓이 된다.
    """
    folder = os.path.dirname(str(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    return len(body)
