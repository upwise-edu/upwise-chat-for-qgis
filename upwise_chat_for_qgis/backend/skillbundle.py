"""자체 스킬 번들 공급 (0.2.0, 설계 docs/2 6-1 경로 P-A).

무엇을 하는가
    `--plugin-dir` 로 넘길 Claude Code 플러그인 번들을 **QGIS 사용자 프로필
    아래에** 만든다. 번들 레이아웃은 S9a 가 실측한 규약 그대로다
    (`.claude-plugin/plugin.json` + `skills/<이름>/SKILL.md`, 장부 V28-37 M-2).
    등재 문자열은 접두 포함 정확명(`upwise-chat-for-qgis:qgis-data-collect`)
    이고, 프리셋 매칭 키가 그 문자열을 쓴다.

왜 패키지 안의 번들을 그대로 쓰지 않는가 (설계에서 벗어난 결정 1건)
    설계 6-1 은 P-A 를 "디스크 쓰기 0" 으로 적었다. 그런데 배포 zip 빌더가
    **이름이 점으로 시작하는 경로 조각을 전부 제외**하고(packaging/build_zip
    `collect_members`), 패키징 하네스 Z3 이 "숨김 이름 0건" 을 단정한다. 번들
    규약이 요구하는 `.claude-plugin/` 을 패키지에 그대로 넣으면 개발 트리에서는
    돌고 **설치본에서는 조용히 빠진다.** 그 실패 모드가 가장 비싸다.
    그래서 점 없는 원본(`<패키지>/skills/...`)을 담아 배포하고, 런타임에
    프로필 아래로 한 번 펼친다.

왜 cwd 가 아니라 프로필인가
    설계 6-1 이 P-B(cwd 설치)를 2순위로 내린 근거는 **cwd 가 사용자의 QGIS
    프로젝트 폴더**라는 것이다(장부 G8). 사용자 자료 폴더 오염, git 리포 오염,
    기존 `.claude/skills` 충돌 세 가지가 거기서 나온다. 프로필 아래
    `upwise_chat/` 은 이미 MCP 설정과 로그를 쓰는 우리 자리이고 세 근거가
    전부 해당하지 않는다. 그래서 동의를 묻지 않는다.

멱등성과 소유 마커
    펼친 `SKILL.md` 에는 소유 마커 한 줄이 들어 있다. 버전이 같으면 아무 것도
    하지 않고, 다르면 덮어쓴다. **마커가 없는 파일은 절대 덮어쓰지 않는다** -
    사용자가 손댄 파일로 보고 사유만 돌려준다(설계 docs/2 6-3).

설계 정본: docs/2.collect_feature_design_v1.md 6-1, 6-2, 6-3
"""

import json
import os
import re
from pathlib import Path

# 번들 플러그인 이름. 등재 문자열의 접두사가 되므로 프리셋 키와 한 쌍이다
# (detect.OWN_PLUGIN_NAME 이 같은 값을 들고 있다).
BUNDLE_PLUGIN_NAME = "upwise-chat-for-qgis"

# 자체 스킬 이름. 마커는 `[qgis-data-collect <버전>]` 이고 기존 MARKER_RE
# (`^\[qgis-[a-z-]+ \d+\.\d+\.\d+\]`)에 그대로 맞는다 - 정규식 수정이 없다.
BUNDLE_SKILL_NAME = "qgis-data-collect"

# 프로필 아래 번들 위치. MCP 설정(upwise_chat/qgis_mcp.json)과 같은 층이다.
BUNDLE_SUBDIR = ("upwise_chat", "plugin_bundle")

# 패키지 안 원본 위치. 점으로 시작하지 않으므로 배포 zip 에 들어간다.
SOURCE_SUBDIR = ("skills", BUNDLE_SKILL_NAME, "SKILL.md")

# 소유 마커. 이 문자열이 없는 파일은 사용자 파일로 본다.
OWNER_MARKER_PREFIX = "<!-- UPWISE-CHAT-OWNED skill=%s version=" % BUNDLE_SKILL_NAME
OWNER_MARKER_RE = re.compile(
    r"<!--\s*UPWISE-CHAT-OWNED\s+skill=([a-z0-9-]+)\s+version=([^\s>]+)\s*-->")

# 원본 템플릿의 버전 치환자. 빌드 시점 치환(설계 6-3)이 아니라 런타임 치환이다
# - 번들을 런타임에 펼치므로 그 자리에서 metadata 버전을 넣는 것이 사본을
#   하나로 유지한다.
VERSION_PLACEHOLDER = "{{version}}"

STATUS_WRITTEN = "WRITTEN"
STATUS_CURRENT = "CURRENT"
STATUS_FOREIGN = "FOREIGN"
STATUS_FAILED = "FAILED"


def package_root():
    """플러그인 패키지 폴더(`upwise_chat_for_qgis`)."""
    return Path(__file__).resolve().parent.parent


def source_skill_path():
    """패키지 안 SKILL.md 원본 경로."""
    return package_root().joinpath(*SOURCE_SUBDIR)


def plugin_version(metadata_path=None):
    """metadata.txt 의 version 값. 버전 정의는 거기 하나뿐이다.

    Args:
        metadata_path: metadata.txt 경로. None 이면 패키지 루트의 것.

    Returns:
        str: 버전 문자열. 못 읽으면 빈 문자열.
    """
    path = Path(metadata_path) if metadata_path else (package_root() / "metadata.txt")
    if not path.is_file():
        return ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    return ""


def marker_of(text):
    """파일 본문에서 소유 마커를 읽는다.

    Returns:
        tuple: (스킬 이름, 버전). 마커가 없으면 ("", "").
    """
    hit = OWNER_MARKER_RE.search(str(text or ""))
    if hit is None:
        return "", ""
    return hit.group(1), hit.group(2)


def bundle_dir(profile_root):
    """번들 루트 경로. `--plugin-dir` 에 이 경로를 넘긴다.

    Args:
        profile_root: QGIS 사용자 프로필 폴더.

    Returns:
        Path
    """
    return Path(profile_root).joinpath(*BUNDLE_SUBDIR, BUNDLE_PLUGIN_NAME)


def registered_skill_name():
    """init.skills 에 올라오는 등재 문자열(접두 포함 정확명).

    S9a M-2 실측: `--plugin-dir` 번들의 스킬은 `<플러그인>:<스킬>` 로 등재된다
    (장부 V28-37). 프리셋 매칭 키를 추측하지 않고 이 함수로 만든다.
    """
    return "%s:%s" % (BUNDLE_PLUGIN_NAME, BUNDLE_SKILL_NAME)


def ensure_bundle(profile_root, version=None, source_path=None):
    """번들을 프로필 아래에 펼친다. 멱등이다.

    Args:
        profile_root: QGIS 사용자 프로필 폴더.
        version: 넣을 버전. None 이면 metadata.txt 에서 읽는다.
        source_path: SKILL.md 원본. None 이면 패키지 안의 것.

    Returns:
        tuple: (상태, 번들 경로 문자열, 근거 문자열)
            상태는 STATUS_WRITTEN / STATUS_CURRENT / STATUS_FOREIGN /
            STATUS_FAILED 중 하나다. FOREIGN 은 사용자 파일을 발견해 손대지
            않은 경우이고, 그때도 번들 경로는 돌려준다(스킬 없이도 기능이
            동작하므로 - 설계 6-1 P-C).
    """
    root = bundle_dir(profile_root)
    src = Path(source_path) if source_path else source_skill_path()
    ver = version if version is not None else plugin_version()
    if not src.is_file():
        return STATUS_FAILED, str(root), "source SKILL.md missing: %s" % src
    if not ver:
        return STATUS_FAILED, str(root), "plugin version unreadable"

    body = src.read_text(encoding="utf-8").replace(VERSION_PLACEHOLDER, ver)
    skill_path = root / "skills" / BUNDLE_SKILL_NAME / "SKILL.md"
    manifest_path = root / ".claude-plugin" / "plugin.json"

    if skill_path.is_file():
        current = skill_path.read_text(encoding="utf-8", errors="replace")
        name, have = marker_of(current)
        if not name:
            # 마커가 없으면 사용자 파일이다. 경고만 하고 덮지 않는다.
            return STATUS_FOREIGN, str(root), \
                "existing SKILL.md has no owner marker: %s" % skill_path
        if name == BUNDLE_SKILL_NAME and have == ver and manifest_path.is_file():
            return STATUS_CURRENT, str(root), "version %s already installed" % ver

    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps({"name": BUNDLE_PLUGIN_NAME, "version": ver,
                        "description": "UPWISE Chat for QGIS bundled skills."},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        # Path.write_text 의 newline 인자는 CPython 3.10 신설이라 구판 번들
        # 파이썬에서 TypeError 가 난다(V28-P20). open 의 newline 은 3.9 이전부터
        # 유효하므로 이쪽으로 LF 를 고정한다.
        with open(str(skill_path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
    except OSError as exc:
        return STATUS_FAILED, str(root), "write failed: %r" % (exc,)
    return STATUS_WRITTEN, str(root), "wrote version %s" % ver


def bundle_present(profile_root):
    """번들 두 파일이 다 있는가. 전제조건 판정이 읽는다.

    Returns:
        bool
    """
    root = bundle_dir(profile_root)
    return (root / ".claude-plugin" / "plugin.json").is_file() and \
        (root / "skills" / BUNDLE_SKILL_NAME / "SKILL.md").is_file()


def source_has_marker():
    """패키지 원본에 소유 마커 치환자가 들어 있는가. 하네스가 읽는다."""
    src = source_skill_path()
    if not src.is_file():
        return False
    text = src.read_text(encoding="utf-8")
    return OWNER_MARKER_PREFIX in text and VERSION_PLACEHOLDER in text


def profile_env_paths(profile_root):
    """수집 서버에 넘길 프로필 기준 경로 묶음.

    키는 여기 없다. INI 경로와 작업 폴더, 로그 경로만 담는다
    (설계 docs/2 5-3 K6: 키는 서버가 INI 에서 직접 읽는다).

    Args:
        profile_root: QGIS 사용자 프로필 폴더.

    Returns:
        dict: ini, workspace, log 키.
    """
    root = Path(profile_root)
    return {
        "ini": str(root / "QGIS" / "QGIS3.ini"),
        "workspace": str(root / "upwise_chat" / "workspace"),
        "log": str(root / "upwise_chat" / "logs"
                   / ("collect_server_%d.log" % os.getpid())),
    }
