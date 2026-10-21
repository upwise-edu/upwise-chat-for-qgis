"""전제조건 탐지 (설계 6-4).

아홉 가지를 본다(0.3.0 에서 내장 서버·T1 공존 둘이 늘고 uvx 축이 빠졌다).

    claude CLI   파일 경로. 유일하게 spawn 전에 알 수 있는 것이다.
    내장 서버    내장 QGIS 소켓 서버가 떴는가와 실포트. init 과 무관하게
                 **플러그인 적재 시점에** 정해진다(0.3.0).
    상류 플러그인 T1(`qgis_mcp_plugin`) 공존 여부. 안내 1줄용이고 비활성
                 사유가 아니다(0.3.0).
    내장 파이썬  수집 서버와 QGIS 브리지를 띄울 인터프리터. 존재 + `-I` 부트
                 프로브다(0.2.0 신설, 0.3.0 에서 두 서버 공용으로 격상).
    툴킷         `init.plugins` 1순위. 2순위는 사용자 settings.json 의 부분문자열.
    MCP 연결     `init.mcp_servers` 에서 name=qgis 와 name=upwise_collect 의 status.
    스킬         툴킷 5종과 자체 번들 1종. 등재 문자열은 접두 포함 정확명이다.
    cwd 전제     프리셋마다 다른 폴더 조건(설계 6-3 표).
    공공 API 키  제공자별 키가 설정에 있는가(0.2.1). **값은 읽지 않는다** -
                 `keystore.key_state()` 가 돌려주는 id 목록만 본다.

0.2.0 이 더한 것과 걷어낸 것
    더한 것: 수집 서버 축(인터프리터 해석, 서버 연결, 번들 공급), 소속별 슬래시
    접두사, 서버 전제조건 일반화(`PRESET_NEEDS_SERVERS`).
    걷어낸 것: `PRESET_NEEDS_PACKAGE`, `PRACTICE_PACKAGE_DEFAULT`,
    `package_present()`, `summary()` 의 `package_*` 두 칸. 강의용 collect 가
    프리셋에서 빠져 쓰는 프리셋이 0 이 됐으므로 잔여 scaffolding 이다
    (설계 docs/2 7-2).
    고친 것: `preset_state()` 의 스킬 등재 검사를 **툴킷 프리셋에만** 걸게 했다.
    안 고치면 자체 스킬이 영구 비활성된다(설계 docs/2 7-3).

0.3.0 이 걷어낸 것과 더한 것
    걷어낸 것: **uvx 축 전량**(`UVX_*` 3상수·`find_uvx_exe`·`Prerequisites`
    의 uvx 3필드·`summary()` 의 uvx 3칸·`unmet_items()` 의 uvx 행). 상류
    stdio 브리지를 `uvx` 로 띄우던 축이고, 0.3.0 의 브리지는 패키지 안
    단일 파일이라 그 런처가 필요 없다(설계 5-2). 그리고 `PRESET_*` 표의
    `qgis-connect-check` 1행(설계 5-4 (b)).
    이름을 바꾼 것: `COLLECT_PYTHON_*` -> `EMBEDDED_PYTHON_*`. 같은
    인터프리터가 수집 서버와 QGIS 브리지를 둘 다 띄운다(설계 4-3 공용화).
    더한 것: 내장 서버 축, T1 공존 탐지, 워커 스레드 프로브 수신구
    (`note_embedded_python`).

    **T3 는 그대로다.** `TOOLKIT_*`·`skills_*`·`SLASH_PREFIX` 는 Claude Code
    플러그인 축이고 그 제거는 S9d 소관이다 - "툴킷 의존 제거" 를 B 혼자
    선언하면 틀린다(설계 함정 12).

왜 init 이 1순위인가
    툴킷 탐지에 `claude plugin` 하위명령을 쓰면 프로세스를 하나 더 띄워야 하고
    출력 형식이 미측이다(D19). S2 녹화에서 init 에 plugins 가 실려 온 것이
    관측됐으므로(장부 V28-18) 이미 받는 이벤트로 끝낼 수 있다.

왜 첫 턴 전에는 알 수 없는가
    입력을 보내기 전에는 init 이 오지 않는다(D06 FAIL). 그래서 툴킷, MCP,
    스킬 세 항목은 첫 턴까지 UNKNOWN 이고 UI 는 "확인 중" 으로 둔다.
    탐지 실패를 "없음" 으로 단정하지 않는다 - 오탐으로 기능을 막지 않는다.

하지 않는 것
    포트 9876 을 직접 열어 보지 않는다. QGIS MCP 는 단일 소켓 직렬이라
    탐지용 연결이 슬롯을 점유해 실제 클라이언트를 wedge 시킬 위험이 있다.
    이득(이미 init 으로 알 수 있다)보다 손실이 비대칭으로 크다(설계 6-4).
    로그인 상태도 탐지하지 않는다 - `claude auth` 가 미측이라(D07) 없는 명령을
    지어내지 않는다. 기동 실패 시 stderr 원문을 보여 주는 것이 전부다.

S6 이 더한 것
    프리셋 5종의 슬래시 문자열(6-1), 마커 판정식(6-2), 전제조건 표의 나머지
    축(6-3: 실습 패키지), 그리고 전제조건 바가 읽는 미충족 목록(7-1 [2]).
    전부 문자열과 경로 판정뿐이고 프로세스를 띄우지 않는다. 그래서 과금 없이
    재생으로 검증된다.

설계 정본: docs/1.mvp_design_v1.md 6-1, 6-2, 6-3, 6-4, 7-1
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import adapter_registry, keystore, posture, skillbundle

# 세 상태. 탐지 실패와 "없음" 을 구분한다. UNKNOWN 은 기능을 막지 않는다.
FOUND = "FOUND"
MISSING = "MISSING"
UNKNOWN = "UNKNOWN"

# 툴킷 플러그인 이름. 툴킷 `.claude-plugin/plugin.json` 의 name 이고 프리셋
# 슬래시 명령의 접두사와 같다(설계 6-1). **T3 다**(설계 5-1) - Claude Code
# 플러그인이고, 그 제거는 S9d 소관이다.
TOOLKIT_NAME = "upwise-qgis-mcp-toolkit"

# 상류 QGIS MCP 플러그인의 **설치 폴더명**(0.3.0). **T1 이다**(설계 5-1) -
# QGIS 플러그인이고 소켓 서버 126종을 들고 있다. 0.3.0 은 그 역할을 패키지
# 안 `mcpserver/` 로 가져왔으므로 T1 이 없어도 제품이 완결된다. 그런데
# 사용자가 강의용으로 계속 깔아 둘 수 있어서 **공존 여부만** 본다(설계 2-5).
#
# 폴더명이 정본 식별자다 - 상류 `handlers/system.py` 가 `qgis.utils` 의
# `available_plugins`/`active_plugins` 멤버십으로 검사하고 그 둘은 폴더명
# 목록이다. `metadata.txt` 의 `name=QGIS MCP` 는 표시 이름일 뿐이다.
UPSTREAM_PLUGIN_NAME = "qgis_mcp_plugin"

# 툴킷 스킬 5종 정확명(설계 6-1). init.skills / init.slash_commands 사전 판정에 쓴다.
#
# 0.2.0: **5종을 그대로 유지한다.** `qgis-collect` 가 프리셋 버튼에서 빠졌어도
# (설계 docs/2 7-2) 툴킷 탐지와 init.skills 사전 판정의 증거이고, 사용자가
# 슬래시 명령을 손으로 타이핑하는 경로를 막지 않는다.
TOOLKIT_SKILLS = (
    "qgis-connect-check",
    "qgis-collect",
    "qgis-preprocess",
    "qgis-verify",
    "qgis-style",
)

# 자체 번들 플러그인 이름과 스킬(0.2.0, 설계 docs/2 6-1 P-A).
# 등재 문자열은 접두 포함 정확명이다(S9a M-2 실측, 장부 V28-37).
OWN_PLUGIN_NAME = skillbundle.BUNDLE_PLUGIN_NAME
OWN_SKILLS = (skillbundle.BUNDLE_SKILL_NAME,)

# 프리셋의 소속. 슬래시 접두사와 "스킬 미등재가 비활성 사유인가" 가 여기서
# 갈린다(설계 docs/2 7-3 이 지적한 결함의 수정 지점).
OWNER_TOOLKIT = "toolkit"
OWNER_PLUGIN = "plugin"

# claude CLI 알려진 위치. shutil.which 가 먼저이고 이것은 폴백이다.
# 실측 경로다(1차 스파이크에서 확인된 설치 위치).
CLAUDE_KNOWN_PATHS = (
    r"%USERPROFILE%\.local\bin\claude.exe",
    r"%LOCALAPPDATA%\Programs\claude\claude.exe",
)

# 0.3.0: uvx 축 3종(`UVX_SETTINGS_KEY`·`UVX_KNOWN_RELPATHS`·`UVX_UNMET_TEXT`)과
# `find_uvx_exe()` 를 **삭제했다**(설계 5-2). 그 축은 상류 stdio 브리지를
# `uvx --from <github zip>` 으로 띄우던 0.1.1~0.2.x 의 것이다. 0.3.0 의 브리지는
# 패키지 안 단일 파일이고 QGIS 번들 파이썬이 띄우므로(backend/posture
# .qgis_bridge_entry) uvx 가 경로에 있든 없든 상관이 없다. 삭제로 닫히는 것:
# 0.1.1 PATH 사고 · 0.1.2 PYTHONEXECUTABLE 사고 · 고아 uvx · 버전 드리프트
# 경고 · 하네스 14 C8 의 잠재 FAIL 원인(장부 V28-A43).
#
# **T2(uvx 브리지)만 사라진다.** T3(Claude Code 플러그인 `upwise-qgis-mcp-
# toolkit`, 스킬 5종·QML 22)는 그대로 탐지한다 - 그쪽 제거는 S9d 소관이고,
# 아래 `TOOLKIT_*` 는 전부 T3 다(설계 5-1 꼬리표 표).

# 버튼 순서와 라벨(설계 6-1 의 나열 순서).
#
# 0.2.0(설계 docs/2 7-2): 수집 버튼의 대상이 툴킷 `qgis-collect` 에서 자체
# 스킬 `qgis-data-collect` 로 바뀌었다. 라벨 "수집" 은 그대로다 - 사용자에게는
# 같은 자리에서 더 넓은 기능이 된다. 강의용 collect 는 실습 패키지 절대경로에
# 종속되고 수집 실행이 셸 전제라 독에서 성립하지 않았다(장부 V28-A50).
#
# 0.3.0(설계 5-4 결정 D-B6 (b)): `qgis-connect-check` **1행을 삭제했다.**
# 그 스킬은 "QGIS MCP 플러그인 0.15.0 / uvx / 포트 9876 / Run MCP" 를 본문
# 상수로 박고 **남의 플러그인 버전**을 조회해 3갈래로 보고했다. 내장 서버
# 아래에서 그 전제가 전부 거짓이 되고, 연결 점검은 플러그인이 **직접** 안다 -
# 서버 핸들러를 직접 불러 포트·버전·레이어 수를 답한다(모델 0턴·유료 0토큰·
# 결정적). 그 배선은 `embedded.EmbeddedServer.self_check()` 와 독의 점검
# 버튼이다. **다른 키는 바꾸지 않는다** - 프리셋 키 교체는 S9d 소관이고
# 설계 6-3 이 그것을 사전 명세로 박았다.
PRESET_ORDER = (
    "qgis-data-collect",
    "qgis-preprocess",
    "qgis-verify",
    "qgis-style",
)

PRESET_LABELS = {
    "qgis-data-collect": "수집",
    "qgis-preprocess": "전처리",
    "qgis-verify": "검증",
    "qgis-style": "스타일",
}

# 프리셋의 소속 플러그인(0.2.0). 슬래시 접두사가 다르다.
#
# 0.3.0 주의: 설계 5-4 는 "(b) 의 귀결로 T3 소속 프리셋이 0 이 된다" 고 적었는데
# **그것은 S9d 완료 후의 상태다.** B 시점에는 전처리·검증·스타일 3종이 여전히
# T3 소속이므로 `preset_state()` 의 `OWNER_TOOLKIT` 분기와 `skills_status`
# 하드 게이트를 **남겨 둔다**. 지금 지우면 툴킷 미설치 환경에서 없는 스킬
# 버튼이 활성으로 보인다.
PRESET_OWNER = {
    "qgis-data-collect": OWNER_PLUGIN,
    "qgis-preprocess": OWNER_TOOLKIT,
    "qgis-verify": OWNER_TOOLKIT,
    "qgis-style": OWNER_TOOLKIT,
}

# 프리셋별 cwd 전제조건(설계 6-3 표). 값은 cwd 기준 상대 경로이고, 빈 튜플은
# 폴더 조건이 없다는 뜻이다. 수집은 폴더 조건이 없다 - 산출물 위치를 서버가
# 정하므로 사용자 폴더 구조에 의존하지 않는다.
PRESET_PATH_REQS = {
    "qgis-style": (),
    "qgis-preprocess": ("00.origins",),
    "qgis-verify": ("04.verify",),
    "qgis-data-collect": (),
}

# 프리셋별 MCP 서버 전제조건(설계 docs/2 7-2). `PRESET_NEEDS_MCP` 의 일반화다.
# 값은 ((서버 이름, "hard"|"soft"), ...) 이고, hard 는 비활성 사유가 되고
# soft 는 단서 문구만 붙는다.
#
# 수집은 `upwise_collect` 가 하드다(서버 없이는 아무 것도 못 받는다). `qgis` 는
# soft 다 - 받기만 하고 적재는 건너뛸 수 있으므로 기능이 반은 산다.
PRESET_NEEDS_SERVERS = {
    "qgis-style": ((posture.QGIS_MCP_SERVER_NAME, "hard"),),
    "qgis-preprocess": ((posture.QGIS_MCP_SERVER_NAME, "hard"),),
    "qgis-verify": ((posture.QGIS_MCP_SERVER_NAME, "hard"),),
    "qgis-data-collect": ((posture.COLLECT_MCP_SERVER_NAME, "hard"),
                          (posture.QGIS_MCP_SERVER_NAME, "soft")),
}

# 수집에 필요한 포스처(설계 docs/2 3-3). 버튼을 누를 때 R 이면 확인 바를 거쳐
# 재spawn 한다. C 또는 W 면 전환 없이 주입한다.
PRESET_POSTURE = {
    "qgis-data-collect": posture.POSTURE_C,
}

# 마커 바를 띄울 프리셋 집합(설계 docs/2 7-2 `preset_for_text` 행).
# 버튼 목록 + 툴킷 collect. 버튼이 없어져도 사용자가 슬래시를 손으로
# 타이핑하는 경로는 남으므로, 그 턴에도 마커 판정이 돌아야 한다.
MARKER_WATCH_PRESETS = PRESET_ORDER + ("qgis-collect",)

# 타이핑 경로로만 인식하는 프리셋의 소속. 버튼은 없지만 슬래시 접두사는
# 알아야 한다.
MARKER_WATCH_OWNER = dict(PRESET_OWNER)
MARKER_WATCH_OWNER["qgis-collect"] = OWNER_TOOLKIT

# 자동 전송하는 프리셋. **0.3.0 에서 비었다**(설계 5-4 귀결).
#
# 0.2.x 는 `qgis-connect-check` 하나를 자동 전송했다 - 전제조건이 없고
# 나머지의 선행 점검이라 사용자가 인자를 적을 것이 없었기 때문이다. 그 프리셋이
# 플러그인 자체 점검으로 대체되면서(유료 1턴 -> 0턴) 자동 전송 대상이 사라졌다.
# 남은 4개는 대상(어느 pN, 어느 레이어)을 암묵 인자로 받으므로(F10) 자동
# 전송하면 범위가 틀린 실행이 된다. 그래서 입력 박스에 넣고 포커스만 준다.
#
# 빈 튜플로 **남겨 둔다.** 지우면 `_inject_preset` 의 분기가 사라지고, S9d 가
# 자동 전송 프리셋을 다시 만들 때 그 자리를 새로 찾아야 한다.
PRESET_AUTOSEND = ()

# 슬래시 명령 접두사. 툴킷 plugin.json 의 name 과 같다(설계 6-1).
SLASH_PREFIX = "/" + TOOLKIT_NAME + ":"

# 자체 번들의 슬래시 접두사(0.2.0). 번들 plugin.json 의 name 과 같다.
OWN_SLASH_PREFIX = "/" + OWN_PLUGIN_NAME + ":"

# 소속별 접두사 조회표. 접두사를 두 군데에 적지 않기 위한 단일 창구다.
SLASH_PREFIXES = {
    OWNER_TOOLKIT: SLASH_PREFIX,
    OWNER_PLUGIN: OWN_SLASH_PREFIX,
}

# 스킬 출력 마커 판정식(설계 6-2, F9). 스킬 5종 전부 첫 줄에
# `[qgis-<이름> 2.1.0]` 을 쓰도록 강제한다("예외 없다"). 그래서 슬래시 명령이
# stdin 경로에서 먹는지가 미측(D02)인 채로도 호출 성공을 런타임에 판정할 수 있다.
#
# 사전 명세: 판정식은 **이 정규식 하나**다. 마커의 스킬 이름이 누른 프리셋과
# 같은지는 판정에 넣지 않는다(설계 6-2 가 요구한 식이 아니다). 이름 불일치는
# 진단 로그에만 남긴다.
#
# 0.1.4(V28-A48): 정규식 **자체는 불변**이고 탐색 범위만 바꿨다. re.MULTILINE
# 을 켜서 `^` 가 응답의 모든 줄 시작에 걸린다. 0.1.3 까지는 응답의 첫 줄만
# 봤고, 모델이 스킬을 부르기 전에 안내 문장을 먼저 말하면 마커가 중간 줄에
# 찍혀 거짓 음성이 났다(18:20 세션 turn=1: ok=False 인데 같은 턴에 마커 2회,
# 도구 10회, success). 줄 시작 앵커는 그대로 두므로 "결과: [qgis-style 2.1.0]"
# 처럼 줄 중간에 인용된 마커는 여전히 안 걸린다.
MARKER_RE = re.compile(r"^\[qgis-[a-z-]+ \d+\.\d+\.\d+\]", re.MULTILINE)

# 마커를 못 찾았을 때의 안내와 버튼(설계 6-2).
MARKER_OK_TEXT = "스킬이 호출되었습니다: %s"
MARKER_FAIL_TEXT = "스킬이 호출되지 않았습니다. 자연어로 다시 요청할 수 있습니다."
MARKER_FALLBACK_BUTTON = "자연어로 다시 요청"

# 폴백 프롬프트(설계 6-2 의 예문을 그대로 쓴다). 스킬 이름과 출력 규칙을
# 풀어 써서 슬래시 경로가 아니어도 같은 절차를 타게 한다.
FALLBACK_PROMPT = (
    "%s 의 %s 스킬 절차대로 수행하고 첫 줄에 스킬 마커를 적어라."
)


def preset_owner(preset):
    """프리셋의 소속. 모르는 이름은 툴킷으로 본다(0.1.x 호출 호환)."""
    return MARKER_WATCH_OWNER.get(str(preset), OWNER_TOOLKIT)


def slash_command(preset):
    """프리셋 하나의 슬래시 명령 문자열(설계 6-1, docs/2 6-2).

    0.2.0: 접두사가 소속에 따라 갈린다. 툴킷 스킬은
    `/upwise-qgis-mcp-toolkit:`, 자체 번들 스킬은 `/upwise-chat-for-qgis:` 다.
    번들 스킬의 등재 문자열이 접두 포함 정확명이라는 것이 S9a M-2 실측이고
    (장부 V28-37), 슬래시 문자열도 그 접두사를 따른다.

    Args:
        preset: 스킬 front matter name. 예: "qgis-style".

    Returns:
        str: 예 "/upwise-qgis-mcp-toolkit:qgis-style".
    """
    return SLASH_PREFIXES[preset_owner(preset)] + str(preset)


def registered_skill_name(preset):
    """프리셋 하나의 init.skills 등재 문자열(접두 포함 정확명).

    툴킷과 자체 번들 모두 `<플러그인>:<스킬>` 로 등재된다(S6 실측 V28-18,
    S9a M-2 실측 V28-37). 사전 판정이 이 문자열로 교집합을 잡는다.
    """
    owner = preset_owner(preset)
    base = OWN_PLUGIN_NAME if owner == OWNER_PLUGIN else TOOLKIT_NAME
    return "%s:%s" % (base, preset)


def preset_for_text(text):
    """보낸 문장이 어느 프리셋에서 나왔는지 본다.

    버튼을 눌러도 사용자가 손으로 고쳐 보낼 수 있으므로(자동 전송은
    connect-check 하나뿐이다) 전송 시점의 문장으로 판정한다. 그래야 마커
    판정(6-2)을 프리셋 턴에만 걸 수 있다.

    0.2.0: 순회 대상이 PRESET_ORDER 가 아니라 **MARKER_WATCH_PRESETS** 다
    (설계 docs/2 7-2). 그래야 버튼이 없어진 툴킷 collect 를 손으로 타이핑
    했을 때도 마커 바가 뜬다.

    Returns:
        str: 프리셋 이름. 프리셋 호출이 아니면 빈 문자열.
    """
    body = (text or "").lstrip()
    for preset in MARKER_WATCH_PRESETS:
        prefix = SLASH_PREFIXES[preset_owner(preset)]
        if not body.startswith(prefix):
            continue
        rest = body[len(prefix):]
        if rest == preset or rest.startswith(preset + " ") \
                or rest.startswith(preset + "\n"):
            return preset
    return ""


def find_marker(text):
    """응답 전체에서 스킬 마커를 찾는다(설계 6-2 판정식, 0.1.4 V28-A48).

    0.1.3 까지는 첫 줄만 봤다. 그런데 모델은 슬래시 명령을 받고도 스킬을
    부르기 전에 안내 문장을 먼저 말할 수 있고, 그러면 마커가 중간 줄에
    찍힌다. 그 턴을 "스킬이 호출되지 않았습니다" 로 읽은 것이 결함이다.
    이제 줄 시작 앵커를 유지한 채 모든 줄을 본다.

    첫 매칭만 쓴다. 한 턴에 마커가 여러 번 나올 수 있지만(스킬이 단계마다
    찍는다) 판정은 "호출됐는가" 하나이고, 사용자에게 보여 줄 이름도 하나다.

    Args:
        text: 판정 대상 턴의 응답 텍스트 전체(여러 줄).

    Returns:
        tuple: (맞았는가, 스킬 이름, 버전, 줄 번호). 줄 번호는 1부터이고
            안 맞으면 (False, "", "", 0).
    """
    body = (text or "")
    hit = MARKER_RE.search(body)
    if hit is None:
        return False, "", "", 0
    matched = hit.group(0)
    inner = matched[1:matched.index("]")]
    name, _sep, version = inner.partition(" ")
    # 줄 번호는 매칭 시작 앞의 줄바꿈 수 + 1. 진단 로그에만 쓰고 판정에는
    # 넣지 않는다(판정식은 정규식 하나다).
    line_no = body.count("\n", 0, hit.start()) + 1
    return True, name, version, line_no


def parse_marker(text):
    """find_marker 의 3-튜플 판정 부분(설계 6-2 판정식).

    줄 번호가 필요 없는 호출자와 앞 회차 하네스가 쓴다.

    Args:
        text: 판정 대상 턴의 응답 텍스트 전체.

    Returns:
        tuple: (맞았는가, 스킬 이름, 버전). 안 맞으면 (False, "", "").
    """
    ok, name, version, _line_no = find_marker(text)
    return ok, name, version


def fallback_prompt(preset):
    """마커가 안 보일 때 보낼 자연어 프롬프트(설계 6-2).

    0.2.0: 플러그인 이름도 소속에 따라 갈린다. 자체 스킬에 툴킷 이름을 적으면
    모델이 없는 스킬을 찾는다.

    Args:
        preset: 프리셋 이름.

    Returns:
        str
    """
    owner = preset_owner(preset)
    base = OWN_PLUGIN_NAME if owner == OWNER_PLUGIN else TOOLKIT_NAME
    return FALLBACK_PROMPT % (base, str(preset))


def find_claude_exe(configured=None):
    """claude 실행 파일을 찾는다(설계 6-4).

    순서는 설정값 -> PATH -> 알려진 위치다. 설정값을 먼저 보는 이유는 사용자가
    고른 것을 PATH 가 덮지 않게 하기 위함이다.

    `--version` 을 여기서 돌리지 않는다. 259 MB PE 라 최초 실행이 느리고
    Defender 스캔이 겹친다. 검증이 필요하면 verify_claude_exe 를 워커
    스레드에서 부른다.

    Args:
        configured: 설정에 저장된 경로. 빈 값이면 건너뛴다.

    Returns:
        tuple: (상태, 경로 또는 "", 근거 문자열)
    """
    if configured:
        p = Path(os.path.expandvars(str(configured)))
        if p.is_file():
            return FOUND, str(p), "configured"
        return MISSING, "", "configured path not a file: %s" % p

    which = shutil.which("claude")
    if which:
        return FOUND, which, "PATH"

    for raw in CLAUDE_KNOWN_PATHS:
        p = Path(os.path.expandvars(raw))
        if p.is_file():
            return FOUND, str(p), "known path"
    return MISSING, "", "not in PATH and not at known locations"


def qgs_setting(key, default=""):
    """QgsSettings 값 하나를 문자열로 읽는다. QGIS 밖에서는 default 다.

    logbook.qgis_profile_root 와 같은 방식이다 - qgis.core 를 함수 안에서
    import 하고 실패하면 떨어뜨린다. 검증 하네스가 QGIS 없이 이 모듈을
    import 할 수 있어야 하고, 설정을 못 읽는 것이 탐지를 중단시킬 이유는 아니다.

    Args:
        key: 설정 키. 예: EMBEDDED_PYTHON_SETTINGS_KEY.
        default: 없을 때 돌려줄 값.

    Returns:
        str
    """
    try:
        from qgis.core import QgsSettings

        value = QgsSettings().value(key, default)
    except Exception:  # noqa: BLE001 - 설정 읽기 실패가 탐지를 막지 않는다
        return default
    if value is None:
        return default
    return str(value)


def upstream_plugin_loaded(utils=None):
    """상류 QGIS MCP 플러그인(T1)이 이 QGIS 에 적재돼 있는가(0.3.0).

    왜 보나
        같은 QGIS 프로세스에 소켓 서버 객체가 둘이면(우리 내장 서버 + 사용자가
        설치한 상류 플러그인의 서버) 한쪽의 긴 핸들러가 이벤트 루프를 펌프하는
        동안 다른 쪽 타이머가 발화해 **교차 디스패치**가 가능하다(설계 2-5,
        E5). 우리 사본의 재진입 가드는 프로세스 전역으로 올려 두었으나
        (VENDOR.md 수정 7) **남의 인스턴스는 우리가 막을 수 없다.** 설치된
        코드를 수정하지 않는 것이 불간섭의 내용이므로, 독 머리에 공존 안내
        1줄을 띄우는 것이 조치다.

        **비활성 사유로 쓰지 않는다.** T1 이 있어도 우리 기능은 다 돈다.

    `qgis.utils` 의 두 키를 다 본다(설계 [미측] 11 을 여기서 닫는다).
    `plugins` 는 **적재된 모듈** 표이고 `active_plugins` 는 활성 목록이다.
    서버 객체가 사는 조건은 `initGui()` 가 돌았다는 것이므로 둘 중 하나라도
    이름이 있으면 공존으로 본다.

    Args:
        utils: `qgis.utils` 대역. None 이면 실제 모듈을 import 한다.
            하네스가 QGIS 없이 분기를 재는 주입점이다.

    Returns:
        tuple: (적재 여부 또는 None, 근거 문자열). None 은 판정 불가다 -
            모듈을 못 읽은 것을 "없음" 으로 단정하지 않는다.
    """
    mod = utils
    if mod is None:
        try:
            from qgis import utils as mod  # noqa: PLC0415 - QGIS 밖 import 허용
        except Exception as exc:  # noqa: BLE001 - 판정 불가는 UNKNOWN 이다
            return None, "qgis.utils unreadable: %r" % (exc,)
    hits = []
    for key in ("plugins", "active_plugins"):
        try:
            container = getattr(mod, key, None)
            if container is not None and UPSTREAM_PLUGIN_NAME in container:
                hits.append(key)
        except Exception:  # noqa: BLE001 - 멤버십 검사 실패는 미발견이다
            continue
    if hits:
        return True, "seen in %s" % ",".join(hits)
    return False, "not in qgis.utils plugins/active_plugins"


# 플러그인이 띄우는 자식 서버의 인터프리터 경로 override 를 담는 QgsSettings
# 키. UI 는 없다 - 고급 설정은 설정으로만 둔다(설계 9).
#
# 0.3.0(설계 4-3·5-2 "공용화"): 이 축이 **수집 서버와 QGIS 브리지 둘 다**를
# 띄운다. 그래서 상수 이름을 중립화했다(`COLLECT_PYTHON_*` ->
# `EMBEDDED_PYTHON_*`). **저장 키 문자열은 바꾸지 않는다** - 바꾸면 이미
# override 를 넣어 둔 설치본에서 그 값이 조용히 무시된다. 이름과 키가 어긋나는
# 것은 의도된 선택이고 그 사유가 이 주석이다.
EMBEDDED_PYTHON_SETTINGS_KEY = "upwise_chat/collect_python"

# QGIS 설치 루트 기준 인터프리터 후보의 상대 조각(0.2.0). **순서가 사전
# 명세**다. S9a M-4 가 잰 순서와 같다(장부 V28-37, V28-P18).
#
# `bin/python3.exe` 를 **넣지 않는다.** 그 실행파일은 `-I` 아래에서 표준
# 라이브러리를 못 찾아 rc=1 로 즉사한다(verifier 요인실험 28조합, 가름 요인은
# `-E`). GUI 의 PYTHONEXECUTABLE 실측값이 바로 그 경로라 상속 의존도 금지다.
EMBEDDED_PYTHON_RELPATHS = (
    ("apps", "Python312", "python.exe"),
    ("apps", "Python311", "python.exe"),
    ("apps", "Python313", "python.exe"),
    ("apps", "Python39", "python.exe"),
)

# 부트 프로브. 두 서버가 실제로 import 하는 stdlib 를 그대로 불러 본다.
# "파일이 있다" 로는 판정하지 않는다 - 0.1.1 uvx 사고가 존재 판정만 하고
# 실행 가능성을 안 본 사례다.
#
# 0.3.0: `struct` 와 `time` 을 더했다. QGIS 브리지가 소켓 프레이밍에
# `struct` 를, 접속 재시도 백오프에 `time` 을 쓴다(`qgis_bridge.py` 상단
# import). 프로브가 서버의 import 목록보다 좁으면 "프로브는 통과했는데
# 실제 기동에서 죽는" 경로가 생긴다 - 장부 V28-P18 이 그 실패 모드다.
EMBEDDED_PROBE_CODE = (
    "import configparser,csv,json,os,re,socket,ssl,struct,sys,time,"
    "urllib.request;print('UPWISE-EMBEDDED-PY-OK')")
EMBEDDED_PROBE_MARKER = "UPWISE-EMBEDDED-PY-OK"
EMBEDDED_PROBE_TIMEOUT_S = 60.0

# 인터프리터 미해석 시 전제조건 바에 올리는 한 줄.
#
# 0.3.0 에서 **심각도를 격상했다**(설계 5-2). 0.2.x 에서 이 축은 소프트였다 -
# 수집만 꺼지고 채팅과 지도 제어는 uvx 브리지가 맡았다. 이제 같은 인터프리터가
# QGIS 브리지도 띄우므로, 미해석이면 `qgis` 서버 항목이 설정에 들어가지 않고
# 게이트 4 가 하드 FAIL 을 낸다. 문구가 그 사실을 말해야 사용자가 입력이
# 막힌 이유를 첫 전송 전에 읽는다.
EMBEDDED_PYTHON_UNMET_TEXT = (
    "플러그인이 쓸 파이썬을 찾지 못했습니다. 지도 제어와 수집이 둘 다 꺼집니다 "
    "- 채팅만 쓸 수 있습니다."
)

# 내장 QGIS 서버 미기동·미연결 시의 한 줄(0.3.0, 설계 5-2 문구 교체).
#
# 0.2.x 는 "QGIS 에서 Run MCP 를 누르세요" 였다. 그 버튼은 **상류 플러그인의
# UI** 이고 내장 서버에는 없다. 사용자가 할 수 있는 조치는 하나뿐이다 -
# 로그를 보고 사유를 읽는 것. 그래서 로그 위치를 가리킨다.
EMBEDDED_SERVER_UNMET_TEXT = (
    "내장 QGIS 서버가 기동하지 않아 지도 제어를 쓸 수 없습니다. QGIS 로그 "
    "패널의 'UPWISE Chat' 탭에서 사유를 확인하세요."
)

# 상류 플러그인(T1) 과 한 QGIS 에 같이 있을 때의 공존 안내 1줄(설계 2-5 조치 2).
# **미충족이 아니다** - 전제조건 바에 올리지 않고 독 머리에 둔다.
#
# U12(0.3.x UI 패스 2차): 문구를 **행위자 기준**으로 다시 썼다. 전 문구
# ("두 서버의 긴 작업이 겹치면 ... 한쪽만 쓰세요")는 두 가지로 잘못 읽혔다.
# (1) "두 서버" 의 실체가 안 드러난다 - 사용자가 보는 것은 서버가 아니라 이
# 채팅과 외부 AI 클라이언트다. (2) "한쪽만 쓰세요" 가 플러그인을 하나만
# 설치하라는 뜻으로 읽힌다 - 공존 자체는 막을 일이 아니고(기능은 다 돈다)
# 겹치면 안 되는 것은 **동시 조작**이다. 그래서 주체를 사람이 아는 이름으로
# 적고, 금지 대상을 "동시 조작" 으로 좁혔다.
UPSTREAM_COEXIST_TEXT = (
    "QGIS MCP 플러그인(qgis_mcp_plugin)이 함께 설치돼 있습니다. 이 채팅과, 그 "
    "플러그인에 연결된 외부 AI(Claude 앱 등)가 같은 프로젝트를 동시에 조작하면 "
    "상태가 섞일 수 있습니다. 긴 작업은 한 번에 한쪽에서만 돌리세요."
)

# 수집 서버 미연결 시의 한 줄(게이트 4 소프트 판정과 같은 사유).
COLLECT_SERVER_UNMET_TEXT = (
    "수집 서버가 연결되지 않았습니다. 수집 버튼만 비활성이고 채팅은 그대로 "
    "쓸 수 있습니다."
)

# 공공 API 키 미설정 시의 한 줄(0.2.1, 설계 docs/2 8 완료 판정).
# 첫 문구를 "키가 설정되지 않았습니다" 로 고정한다 - 완료 판정이 그 문장을
# 전제조건 바에서 찾고, 설정 패널의 행 상태 문구와도 같은 말이어야 한다.
COLLECT_KEYS_UNMET_TEXT = (
    "키가 설정되지 않았습니다. 독 머리의 [키 설정] 에서 공공 API 키를 넣으세요. "
    "키는 이 PC 의 QGIS 설정에만 저장되고 채팅에는 들어가지 않습니다."
)

# 키가 **일부** 제공자에만 있을 때의 한 줄(0.5.0, 설계 docs/8 2-1).
# 전제조건은 ANY 다 - 제공자 하나라도 키가 있으면 수집은 활성이고, 키가 없는
# 제공자의 데이터셋만 목록에서 비활성이다. 이 문구는 **새 상수**다:
# `COLLECT_KEYS_UNMET_TEXT` 의 "키가 설정되지 않았습니다" 는 0건 경로의 고정
# 문구이고(완료 판정과 키 패널 행 문구가 그 문장을 찾는다) 부분 충족에 같은
# 문장을 쓰면 "기능이 고장났다" 로 읽힌다.
COLLECT_KEYS_PARTIAL_FMT = (
    "%s 키가 없어 %s 데이터셋은 목록에서 비활성입니다. 나머지 제공자의 수집은 "
    "그대로 쓸 수 있습니다."
)


# ------------------------------------------------------------------
# Claude Code 미로그인 가드 (0.4.0, 2026-10-15 노트북 실기)
# ------------------------------------------------------------------
#
# 새 기기에서 CLI 가 미로그인이면 플러그인 안에서는 탈출 불가 루프였다.
# 플러그인은 CLI 를 `-p --input-format stream-json` 비대화형으로 띄우므로
# 매 턴 result 텍스트로 "Not logged in . Please run /login" 이 오고,
# 사용자가 독 입력창에 `/login` 을 치면 "/login isn't available in this
# environment" 가 온다(대화형 전용 커맨드). 전제조건 바는 로그인 축을
# 검사하지 않는다 - 검사 축은 cwd 폴더·MCP 서버·스킬 번들·내장 서버·
# 인터프리터 다섯뿐이다(README 5 함정 첫 항목).
#
# 가드 셋은 **전부 안내이고 차단이 아니다.** 아래 soft 판정은 추정이라
# 오탐이 날 수 있고(apiKeyHelper, 기업 프록시, 다른 자격 저장 경로),
# 추정으로 전송을 막으면 멀쩡히 로그인된 환경에서 플러그인이 못 쓰게
# 된다. 그래서 판정 실패의 비용이 작은 쪽으로 기운다 - 문구도
# "확인되지 않습니다" 로 단정하지 않는다.

# A: soft 사전검사 1줄. **미충족이 아니라 경고**이므로 전제조건 바가
# 아니라 독 머리에 둔다(UPSTREAM_COEXIST_TEXT 와 같은 자리·같은 근거).
LOGIN_SOFT_NOTICE_TEXT = (
    "Claude Code 로그인이 확인되지 않습니다 - 터미널에서 claude 를 실행해 "
    "/login 하세요"
)

# B: 실제로 미로그인 신호를 본 뒤의 공지. 사용자가 할 조치는 하나다 -
# 터미널에서 /login 하고 독에서 새 대화. 새 대화를 덧붙이는 이유는 지금
# 떠 있는 CLI 자식이 미인증 상태 그대로라 재spawn 전에는 안 풀리기 때문이다.
#
# C 도 0.4.1 까지 이 문구를 **같이** 썼다. 2026-10-17 사용자 실기에서 그것이
# 결함으로 드러났다 - 로그인된 사용자가 `/login` 을 치면 "Claude Code
# 미로그인" 이라는 **거짓 단정**을 본다. C 는 로그인 상태를 본 적이 없고
# "이 입력은 비대화형 CLI 에서 안 돈다" 는 사실만 안다. 그래서 C 는 아래
# LOGIN_SLASH_NOTICE_TEXT 로 갈라졌고, 이 상수는 B 전용이다(B 는 본문에서
# 신호를 실제로 봤으므로 이 단정이 참이다).
LOGIN_HARD_NOTICE_TEXT = (
    "Claude Code 미로그인 - 터미널에서 claude 를 실행해 /login 한 뒤, "
    "독에서 새 대화를 시작하세요"
)

# C: 자격의 흔적이 **있을 때** 쓰는 가로채기 공지(0.4.2, 2026-10-17 실기).
#
# 단정하지 않는 문면이다. 말하는 것은 두 가지뿐이고 둘 다 확인된 사실이다.
#   (1) 이 독은 비대화형 모드라 `/login` 류가 동작하지 않는다(설계 2-1)
#   (2) 로그인 상태를 바꾸려면 터미널에서 해야 한다
# 로그인 여부를 말하지 않는 이유는 가드 A 의 탐지가 추정이기 때문이다 -
# 자격 파일 1개와 환경변수 1개만 보므로 "있다" 쪽도 단정이 못 된다
# (login_evidence docstring). 가로채기 자체는 두 경우 모두 유지한다 -
# 보내 봐야 CLI 가 같은 막다른 답을 돌려주고 턴 하나가 과금된다.
#
# 문자열 치환자를 두지 않는다 - 공지가 어느 커맨드에서 왔는지는 전사 바로
# 위에 사용자가 친 줄이 말한다. 치환자를 두면 B 공지와 달리 포맷 경로가
# 하나 더 생기고, 그 경로가 깨지면 사용자가 보는 것은 %s 다.
LOGIN_SLASH_NOTICE_TEXT = (
    "/login 과 /logout 은 이 창에서 동작하지 않습니다 - 독은 Claude Code 를 "
    "비대화형으로 띄웁니다. 로그인 상태를 바꾸려면 터미널에서 claude 를 "
    "실행해 거기서 하고, 독에서는 새 대화를 시작하세요."
)

# B 의 본문 신호. 2026-10-15 실기 원문은 "Not logged in . Please run /login"
# 이었다. 뒤 문장(Please run ...)까지 요구하지 않는 이유는 CLI 판본마다
# 안내 문장이 바뀔 수 있어서다 - 앞머리 한 구절이 더 안정적이다.
# 소문자로 둔다. 판정이 lower() 뒤에 비교한다(EXCLUSION_MARKER 와 같은 관용구).
NOT_LOGGED_IN_MARKER = "not logged in"

# C 의 가로채기 대상. 비대화형 모드에서 동작하지 않는 대화형 전용 슬래시다.
# 목록을 좁게 유지한다 - 실기로 확인된 것은 /login 이고 /logout 은 같은
# 대화형 인증 축이라 함께 넣는다. 확인되지 않은 커맨드를 넣으면 멀쩡히
# 도는 입력을 플러그인이 삼킨다.
INTERACTIVE_ONLY_SLASHES = ("/login", "/logout")

# A 의 자격 파일. 로그인된 PC 에서 실재를 2026-10-15 실측했다.
CREDENTIALS_RELPATH = (".claude", ".credentials.json")

# A 의 둘째 경로. 키가 환경변수로 들어오는 구성에서는 자격 파일이 없다.
LOGIN_API_KEY_ENV = "ANTHROPIC_API_KEY"


def credentials_path(home=None):
    """Claude Code 자격 파일의 추정 경로.

    Args:
        home: 홈 폴더. None 이면 `USERPROFILE` 을 읽고, 그것도 없으면
            `~` 를 확장한다. 하네스가 임시 폴더를 넣는 자리다.

    Returns:
        str: 자격 파일 경로.
    """
    base = home
    if not base:
        base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(str(base), *CREDENTIALS_RELPATH)


def login_evidence(home=None, env=None):
    """로그인 자격의 흔적이 있는가를 추정한다(A, soft).

    **있다/없다를 단정하지 않는다.** 자격 파일 1개와 환경변수 1개만 보므로
    다른 인증 경로(apiKeyHelper, 기업 프록시, 사내 게이트웨이)를 쓰는
    환경에서는 거짓 음성이 난다. 그래서 돌려주는 값은 전송 차단에 쓰지
    않고 안내 1줄을 띄울지에만 쓴다.

    Args:
        home: 홈 폴더. None 이면 `credentials_path` 의 기본 해석이다.
        env: 환경변수 매핑. None 이면 `os.environ`.

    Returns:
        tuple: (found, reason). found 는 bool, reason 은 어느 축이 걸렸는지
            적은 짧은 문자열("credentials" / "env" / "none").
    """
    environ = os.environ if env is None else env
    path = credentials_path(home)
    try:
        has_file = os.path.isfile(path)
    except Exception:  # noqa: BLE001 - 경로 판정 실패를 "로그인 됨" 으로 읽지 않는다
        has_file = False
    if has_file:
        return True, "credentials"
    if (environ.get(LOGIN_API_KEY_ENV) or "").strip():
        return True, "env"
    return False, "none"


def text_shows_not_logged_in(text):
    """닫힌 턴의 본문에 미로그인 신호가 있는가(B, hard).

    대소문자를 무시한다. CLI 원문의 대문자 표기가 판본마다 다를 수 있고,
    여기서 가르는 것은 표기가 아니라 사실이기 때문이다.

    Args:
        text: result 와 assistant 텍스트를 이어 붙인 본문.

    Returns:
        bool: 신호가 있으면 True.
    """
    if not isinstance(text, str):
        return False
    return NOT_LOGGED_IN_MARKER in text.lower()


def interactive_only_slash(text):
    """입력이 대화형 전용 슬래시 1개인가(C).

    **그 단어 단독일 때만** 걸린다. 앞뒤 공백은 허용하지만 `/login2` 나
    본문 중간의 `/login` 은 아니다. 사용자가 "/login 이 왜 안 되나요" 라고
    물을 수도 있고, 그 질문까지 삼키면 플러그인이 대화를 먹는다.

    대소문자는 가리지 않는다 - CLI 슬래시가 소문자 전용이라 `/LOGIN` 은
    어차피 CLI 에서도 안 돈다. 가로채서 같은 안내를 주는 쪽이 낫다.

    Args:
        text: 독 입력창의 원문.

    Returns:
        str: 걸린 슬래시 명령("/login" 등). 아니면 빈 문자열.
    """
    if not isinstance(text, str):
        return ""
    token = text.strip().lower()
    for name in INTERACTIVE_ONLY_SLASHES:
        if token == name:
            return name
    return ""


def login_slash_notice(home=None, env=None):
    """가드 C 가 띄울 공지를 자격 탐지 결과로 고른다 (0.4.2).

    0.4.1 까지 C 는 B 와 같은 `LOGIN_HARD_NOTICE_TEXT` 를 썼다. 그래서
    **로그인된 사용자가 `/login` 을 치면 "Claude Code 미로그인" 이라는 거짓
    단정**을 봤다(2026-10-17 사용자 실기). C 가 실제로 아는 것은 "이 입력이
    비대화형 CLI 에서 안 돈다" 하나뿐이고 로그인 여부는 본 적이 없다.

    자격의 흔적이 있으면 미로그인을 말하지 않는 문구로, 없으면 기존 문구로
    간다. **가로채기 자체는 두 경로 모두에서 유지된다** - 이 함수는 무엇을
    적을지만 고르고 보낼지 말지는 고르지 않는다.

    탐지는 `login_evidence` 의 soft 판정이라 양쪽 다 틀릴 수 있다. 그래서
    고르는 두 문구 중 어느 쪽도 "로그인돼 있습니다" 를 말하지 않는다.

    Args:
        home: 홈 폴더. None 이면 `credentials_path` 의 기본 해석이다.
        env: 환경변수 매핑. None 이면 `os.environ`.

    Returns:
        tuple: (공지 문구, found, reason). 뒤 둘은 `login_evidence` 의
            반환 그대로다 - 기계 로그가 어느 가지로 갔는지 남긴다.
    """
    found, reason = login_evidence(home, env)
    if found:
        return LOGIN_SLASH_NOTICE_TEXT, found, reason
    return LOGIN_HARD_NOTICE_TEXT, found, reason


def qgis_install_root():
    """QGIS 설치 루트. `apps/PythonNNN` 의 부모다.

    `sys.prefix` 는 QGIS 안에서 `<루트>/apps/PythonNNN` 을 가리키고
    `sys.executable` 은 런처의 `bin/python3.exe` 를 가리킨다(S9a M-4 실측).
    양쪽에서 거슬러 올라가 루트 후보를 모은다 - 설치 경로를 상수로 박으면
    다른 버전을 깐 수강생 환경에서 깨진다.

    Returns:
        tuple: 중복을 제거한 후보 경로 문자열들.
    """
    raw_roots = []
    for raw in (os.environ.get("QGIS_PREFIX_PATH", ""), sys.prefix,
                os.path.dirname(os.path.dirname(sys.executable or ""))):
        if not raw:
            continue
        here = Path(raw)
        # `<루트>/apps/qgis-ltr` 와 `<루트>/apps/Python312` 둘 다 2단 위가 루트다.
        for cand in (here, here.parent, here.parent.parent):
            text = str(cand)
            if text and text not in raw_roots:
                raw_roots.append(text)
    # `bin` 폴더가 있는 것만 남긴다. 2단 위로 올라가다 보면 `C:\Program Files`
    # 나 `C:\` 까지 닿는데, 거기 아래 `apps\Python312\python.exe` 가 우연히
    # 있으면 QGIS 와 무관한 인터프리터를 집는다. QGIS 설치 루트는 `bin` 을
    # 가진다(런처 python-qgis-ltr.bat 가 거기 있다).
    narrowed = [r for r in raw_roots if (Path(r) / "bin").is_dir()]
    return tuple(narrowed or raw_roots)


def embedded_python_candidates(roots=None):
    """자식 서버 인터프리터 후보를 사전 명세 순서로 돌려준다.

    Args:
        roots: QGIS 설치 루트 후보들. None 이면 qgis_install_root().

    Returns:
        tuple: 절대경로 문자열들(중복 제거, 순서 보존).
    """
    out = []
    for root in (roots if roots is not None else qgis_install_root()):
        for parts in EMBEDDED_PYTHON_RELPATHS:
            path = os.path.normpath(str(Path(root).joinpath(*parts)))
            if path.lower() not in [p.lower() for p in out]:
                out.append(path)
    return tuple(out)


def probe_embedded_python(exe, timeout_s=EMBEDDED_PROBE_TIMEOUT_S):
    """후보 하나를 `-I` 로 실제 띄워 본다.

    `-I` 로 재는 이유: 두 서버를 그 플래그로 띄우기 때문이다. 플래그 없이
    재면 통과했다가 실제 기동에서 죽는다(장부 V28-P18 의 실측 분기).

    Args:
        exe: 후보 경로.
        timeout_s: 상한.

    Returns:
        tuple: (통과 여부, 근거 문자열)
    """
    try:
        done = subprocess.run(
            [str(exe), "-I", "-c", EMBEDDED_PROBE_CODE],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_s,
            creationflags=0x08000000 if sys.platform == "win32" else 0)
    except Exception as exc:  # noqa: BLE001 - 프로브 실패가 기동을 막지 않는다
        return False, "probe raised %r" % (exc,)
    if done.returncode == 0 and EMBEDDED_PROBE_MARKER in (done.stdout or ""):
        return True, "rc=0"
    return False, "rc=%s stderr=%s" % (done.returncode,
                                       (done.stderr or "").strip()[:200])


def resolve_embedded_python(configured=None, settings_reader=None, roots=None,
                           prober=None):
    """자식 서버(수집 서버·QGIS 브리지)를 띄울 인터프리터를 해석한다.

    후보 순서는 **사전 명세**다. 실행 전에 박고 결과를 보고 바꾸지 않는다.

        1. 사용자 지정 override(설정 EMBEDDED_PYTHON_SETTINGS_KEY). 값이 있는데
           파일이 아니거나 프로브를 통과하지 못하면 거기서 MISSING 으로
           끝낸다 - 사용자 오타를 조용히 다른 파이썬으로 덮지 않는다.
        2. `<QGIS 루트>/apps/Python312|311|313|39/python.exe` 순서.
        각 후보는 존재 확인 **뒤에 `-I` 부트 프로브**를 통과해야 채택된다.

    `sys.executable` 과 `bin/python3.exe` 는 후보에 없다. 전자는 QGIS 안에서
    후자를 가리키고, 후자는 `-I` 에서 즉사한다(장부 V28-P18).

    Args:
        configured: 사용자 지정 경로. 빈 값이면 settings_reader 로 읽는다.
        settings_reader: callable(key) -> str. None 이면 qgs_setting.
        roots: QGIS 설치 루트 후보들. 하네스 주입점이다.
        prober: callable(exe) -> (bool, str). None 이면 probe_embedded_python.

    Returns:
        tuple: (상태, 경로 또는 "", 근거 문자열)
    """
    reader = settings_reader if settings_reader is not None else qgs_setting
    probe = prober if prober is not None else probe_embedded_python

    override = configured if configured else reader(EMBEDDED_PYTHON_SETTINGS_KEY)
    if override:
        path = Path(os.path.expandvars(str(override)))
        if not path.is_file():
            return MISSING, "", "configured path not a file: %s" % path
        ok, why = probe(str(path))
        if ok:
            return FOUND, str(path), "configured (%s)" % EMBEDDED_PYTHON_SETTINGS_KEY
        return MISSING, "", "configured path failed -I probe: %s" % why

    tried = []
    for cand in embedded_python_candidates(roots):
        if not os.path.isfile(cand):
            tried.append("%s:absent" % os.path.basename(os.path.dirname(cand)))
            continue
        ok, why = probe(cand)
        if ok:
            return FOUND, cand, "candidate probe ok"
        tried.append("%s:%s" % (cand, why))
    return MISSING, "", "no candidate passed the -I probe (%s)" % (
        "; ".join(tried)[:400] or "no candidates")


def verify_claude_exe(exe, runner, timeout_s=90.0):
    """`--version` 으로 실행 가능 여부를 본다. 워커 스레드에서 부른다.

    프로세스 기동을 이 모듈이 직접 하지 않는다. runner 를 받아서 부른다 -
    그래야 테스트가 가짜 runner 를 넣어 과금 없이 돌 수 있고, 플랫폼별
    creationflags 같은 정책이 process 계층에 한 군데로 모인다.

    Args:
        exe: 실행 파일 경로.
        runner: callable(argv, timeout_s) -> (returncode, stdout, stderr).
        timeout_s: 상한. 기본 90 s 는 PoC 에서 쓴 값이다(최초 실행이 느리다).

    Returns:
        tuple: (상태, 버전 문자열 또는 "", 근거)
    """
    if not exe:
        return MISSING, "", "no exe"
    try:
        rc, out, err = runner([str(exe), "--version"], timeout_s)
    except Exception as exc:  # noqa: BLE001 - 탐지 실패가 기동을 막지 않는다
        return UNKNOWN, "", "runner raised %r" % (exc,)
    if rc == 0:
        return FOUND, (out or "").strip()[:200], "rc=0"
    return UNKNOWN, "", "rc=%s stderr=%s" % (rc, (err or "").strip()[:200])


def toolkit_from_init(init_event):
    """init.plugins 에서 툴킷을 찾는다. 1순위 경로다(설계 6-4).

    plugins 의 스키마는 관측이고 보장이 아니다(장부 V28-18). 그래서 구조를
    가정하지 않고 직렬화한 문자열에서 이름을 찾는다. 수강생 환경에 필드가
    없으면 UNKNOWN 이고, 그때도 프리셋을 막지 않는다.

    Returns:
        tuple: (상태, 버전 문자열 또는 "", 근거)
    """
    if not isinstance(init_event, dict):
        return UNKNOWN, "", "init not a dict"
    plugins = init_event.get("plugins")
    if plugins is None:
        return UNKNOWN, "", "init has no plugins field"
    blob = json.dumps(plugins, ensure_ascii=False)
    if TOOLKIT_NAME not in blob:
        return MISSING, "", "plugins present but toolkit name absent"
    version = ""
    # 리스트 of dict 가 관측된 형태다. 아니면 버전 없이 FOUND 로 둔다.
    if isinstance(plugins, list):
        for entry in plugins:
            if not isinstance(entry, dict):
                continue
            if TOOLKIT_NAME in json.dumps(entry, ensure_ascii=False):
                version = str(entry.get("version") or "")
                break
    return FOUND, version, "init.plugins"


def toolkit_from_settings(settings_path=None):
    """2순위. 사용자 settings.json 의 직렬화 문자열에서 이름을 찾는다.

    `enabledPlugins` 키가 있는 것은 실측이고(F6) 그 스키마는 미측이다. 그래서
    키를 파고들지 않고 파일 전체 문자열에서 찾는다 - 둔감하게 둔 것이 의도다.
    """
    path = Path(settings_path) if settings_path else (
        Path(os.path.expanduser("~")) / ".claude" / "settings.json")
    if not path.is_file():
        return UNKNOWN, "", "settings.json not found: %s" % path
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return UNKNOWN, "", "read failed %r" % (exc,)
    if TOOLKIT_NAME in body:
        return FOUND, "", "settings.json substring"
    return MISSING, "", "settings.json has no toolkit name"


def mcp_status_from_init(init_event, server_name=posture.QGIS_MCP_SERVER_NAME):
    """init.mcp_servers 에서 서버 하나의 status 를 읽는다(설계 3-4 게이트 4).

    Returns:
        tuple: (상태, status 문자열, 근거)
    """
    if not isinstance(init_event, dict):
        return UNKNOWN, "", "init not a dict"
    servers = init_event.get("mcp_servers")
    if servers is None:
        return UNKNOWN, "", "init has no mcp_servers field"
    if not isinstance(servers, list):
        return UNKNOWN, "", "mcp_servers not a list"
    for entry in servers:
        if isinstance(entry, dict) and entry.get("name") == server_name:
            status = str(entry.get("status") or "")
            return (FOUND if status == "connected" else MISSING), status, "init.mcp_servers"
    return MISSING, "", "server %r absent (n=%d)" % (server_name, len(servers))


def skills_from_init(init_event):
    """init.skills / init.slash_commands 에서 툴킷 스킬 5종을 찾는다(설계 6-4).

    사전 판정용이다. 있으면 버튼을 누르기 전에 호출 가능 여부를 알 수 있고,
    없으면 6-2 의 사후 마커 판정만 쓴다. 관측 필드이므로 부재가 정상이다.

    S6 정정: 찾는 문자열을 **접두사까지 붙인 정확명**으로 바꿨다. 실녹화에서
    등재 형태가 `upwise-qgis-mcp-toolkit:qgis-collect` 였다(장부 V28-18).
    맨이름만 찾으면 다른 플러그인의 같은 이름 스킬도 걸린다.

    Returns:
        tuple: (상태, 찾은 스킬 이름들, 근거)
    """
    blob, why = _skills_blob(init_event)
    if blob is None:
        return UNKNOWN, (), why
    hits = tuple(name for name in TOOLKIT_SKILLS
                 if (TOOLKIT_NAME + ":" + name) in blob)
    if not hits:
        return MISSING, (), "fields present but no toolkit skill name"
    return FOUND, hits, "init fields"


def _skills_blob(init_event):
    """init 의 skills/slash_commands 를 한 문자열로 직렬화한다.

    Returns:
        tuple: (문자열 또는 None, 근거). None 은 필드가 아예 없다는 뜻이다.
    """
    if not isinstance(init_event, dict):
        return None, "init not a dict"
    parts = []
    for key in ("skills", "slash_commands"):
        value = init_event.get(key)
        if value is not None:
            parts.append(json.dumps(value, ensure_ascii=False))
    if not parts:
        return None, "init has neither skills nor slash_commands"
    return " ".join(parts), "init fields"


def own_skills_from_init(init_event):
    """init 에서 자체 번들 스킬을 찾는다(0.2.0, 설계 docs/2 6-1).

    찾는 문자열은 접두 포함 정확명(`upwise-chat-for-qgis:qgis-data-collect`)
    이다. S9a M-2 가 `--plugin-dir` 번들의 등재 형태를 그렇게 실측했다
    (장부 V28-37).

    **미등재가 수집 버튼의 비활성 사유가 아니다.** 수집 절차의 대부분이 도구
    스키마에 들어 있어 스킬 없이도 동작하므로(설계 docs/2 6-1 P-C), 이 값은
    진단과 단서 문구에만 쓴다.

    Returns:
        tuple: (상태, 찾은 스킬 이름들, 근거)
    """
    blob, why = _skills_blob(init_event)
    if blob is None:
        return UNKNOWN, (), why
    hits = tuple(name for name in OWN_SKILLS
                 if (OWN_PLUGIN_NAME + ":" + name) in blob)
    if not hits:
        return MISSING, (), "fields present but no bundled skill name"
    return FOUND, hits, "init fields"


def mcp_statuses_from_init(init_event, server_names=()):
    """여러 서버의 status 를 한 번에 읽는다(0.2.0).

    Args:
        init_event: init 이벤트 dict.
        server_names: 볼 서버 이름들.

    Returns:
        dict: 서버 이름 -> (상태, status 문자열, 근거)
    """
    return {name: mcp_status_from_init(init_event, name)
            for name in server_names}


def cwd_requirements(cwd, preset):
    """프리셋 하나의 cwd 폴더 전제조건을 본다(설계 6-3).

    Args:
        cwd: 백엔드 작업 폴더.
        preset: 스킬 이름(front matter name).

    Returns:
        tuple: (충족 여부, 빠진 경로들)
    """
    reqs = PRESET_PATH_REQS.get(preset, ())
    if not reqs:
        return True, ()
    if not cwd:
        return False, tuple(reqs)
    root = Path(cwd)
    missing = tuple(r for r in reqs if not (root / r).exists())
    return (not missing), missing


class Prerequisites(object):
    """탐지 결과 묶음. UI 가 읽는 단일 창구다.

    claude 경로만 spawn 전에 채워지고, 나머지는 첫 턴의 init 에서 채워진다
    (D06 FAIL). 그래서 note_init() 전에는 toolkit/mcp/skills 가 UNKNOWN 이다.
    """

    def __init__(self, cwd="", configured_exe=None, profile_root=None,
                 resolve_python=True, backend=None):
        """
        Args:
            cwd: 백엔드 작업 폴더. 프리셋 폴더 조건의 기준이다(설계 6-3).
            configured_exe: 설정에 저장된 백엔드 CLI 경로. 없으면 PATH 를 본다.
            profile_root: QGIS 사용자 프로필 폴더(0.2.0). 번들 상태 판정의
                기준이다. None 이면 번들 축을 UNKNOWN 으로 둔다.
            resolve_python: 자식 서버 인터프리터를 지금 해석할지(0.2.0).
                False 면 UNKNOWN 으로 두고 부트 프로브를 돌리지 않는다 -
                하네스가 프로세스를 띄우지 않고 import 할 수 있어야 하고,
                **0.3.0 의 제품 경로도 False 로 부른다** - 프로브가
                `initGui()` 를 블록하지 않게 워커 스레드로 내렸기 때문이다
                (설계 함정 15). 결과는 `note_embedded_python()` 으로 온다.

        0.3.0: `configured_uvx` 인자를 삭제했다. uvx 축이 없다(설계 5-2).

        Args(이어서):
            backend: 백엔드 어댑터(0.5.5, docs/7 2-10 경계 1). None 이면
                기본 백엔드다. 실행 파일 탐지가 어댑터로 가므로 제2 백엔드가
                들어와도 이 클래스를 고치지 않는다. **필드 이름은
                `claude_*` 로 남는다** - 독과 앞 회차 하네스가 그 이름으로
                읽고, 중립 이름은 아래 `backend_*` 별칭으로 더했다.
        """
        self.cwd = str(cwd or "")
        self.backend = backend or adapter_registry.default()
        self.backend_name = self.backend.name
        self.claude_status, self.claude_exe, self.claude_why = (
            self.backend.find_executable(configured_exe))
        self.claude_version = ""
        # 자식 서버 인터프리터도 spawn 전에 판정된다. 다만 `-I` 부트 프로브로
        # 프로세스를 띄우므로 한 번만 돌린다(장부 V28-P18).
        if resolve_python:
            (self.embedded_python_status, self.embedded_python,
             self.embedded_python_why) = resolve_embedded_python()
        else:
            self.embedded_python_status = UNKNOWN
            self.embedded_python = ""
            self.embedded_python_why = "probe skipped"
        self.profile_root = str(profile_root or "")
        self.bundle_status = UNKNOWN
        self.bundle_dir = ""
        self.bundle_why = "bundle not materialised yet"
        # 첫 init 을 받았는가. 받기 전에는 툴킷/MCP/스킬이 "확인 중" 이고
        # 전제조건 바에 미충족으로 적지 않는다(D06 FAIL).
        self.init_seen = False
        self.toolkit_status = UNKNOWN
        self.toolkit_version = ""
        self.toolkit_why = "init not received yet (D06)"
        self.mcp_status = UNKNOWN
        self.mcp_detail = ""
        self.mcp_why = "init not received yet (D06)"
        # 수집 서버 연결(0.2.0). 게이트 4 의 소프트 항목과 같은 사실을 본다.
        self.collect_status = UNKNOWN
        self.collect_detail = ""
        self.collect_why = "init not received yet (D06)"
        self.skills_status = UNKNOWN
        self.skills_found = ()
        self.skills_why = "init not received yet (D06)"
        self.own_skills_status = UNKNOWN
        self.own_skills_found = ()
        self.own_skills_why = "init not received yet (D06)"
        # 공공 API 키 축(0.2.1). init 과 무관하게 설정만 보면 알 수 있으므로
        # claude/내장 파이썬과 같은 조에 있다. 다만 **UNKNOWN 에서 시작
        # 한다** - refresh_keys() 를 부르기 전에 MISSING 으로 단정하면 QGIS
        # 밖(하네스)에서 import 만 해도 수집 버튼이 꺼진 것으로 보인다.
        self.keys_status = UNKNOWN
        self.keys_configured = ()
        self.keys_missing = ()
        self.keys_why = "keys not checked yet"
        # 내장 QGIS 서버 축(0.3.0, 설계 5-2 "신설"). **init 과 무관하다** -
        # 플러그인 적재 시점에 참·거짓이 정해지므로 claude·인터프리터와 같은
        # 조다. 그래서 전제조건 바가 **첫 전송 전에** "지도 제어가 가능한가"
        # 를 말할 수 있다(0.2.x 의 `mcp` 축은 첫 턴까지 UNKNOWN 이었다).
        self.server_status_embedded = UNKNOWN
        self.server_port = 0
        self.server_why = "embedded server not started yet"
        # 상류 플러그인(T1) 적재 여부(0.3.0, 설계 2-5 조치 2).
        # **비활성 사유로 쓰지 않는다** - 공존 안내 1줄의 근거일 뿐이다.
        # 남의 서버 인스턴스는 우리가 막을 수 없고, 우리 쪽 재진입 가드는
        # 프로세스 전역이라 우리 인스턴스끼리는 안전하다.
        self.upstream_plugin_status = UNKNOWN
        self.upstream_plugin_why = "not checked yet"

    # ------------------------------------------------------------------
    # 백엔드 중립 별칭 (0.5.5, docs/7 2-10 경계 1)
    # ------------------------------------------------------------------
    #
    # `claude_*` 네 필드는 **이름을 바꾸지 않는다.** 독·plugin.py·앞 회차
    # 하네스가 그 이름으로 읽고, 이름 변경은 행동 불변 증명의 비용을
    # 키운다. 대신 중립 이름을 property 로 더해 둔다 - 제2 백엔드가 들어온
    # 뒤 새로 쓰는 코드는 이쪽을 쓴다.

    @property
    def backend_status(self):
        """백엔드 CLI 탐지 상태(FOUND/MISSING/UNKNOWN)."""
        return self.claude_status

    @property
    def backend_exe(self):
        """백엔드 CLI 실행 파일 경로. 못 찾았으면 빈 문자열."""
        return self.claude_exe

    @property
    def backend_why(self):
        """탐지 근거 문자열."""
        return self.claude_why

    @property
    def backend_version(self):
        """`--version` 검증이 돌았으면 그 문자열. 아니면 빈 문자열."""
        return self.claude_version

    def note_embedded_python(self, status, path, why):
        """워커 스레드가 끝낸 `-I` 부트 프로브 결과를 받는다(0.3.0).

        `initGui()` 에서 동기로 돌면 후보마다 `subprocess.run` 이 UI 를
        블록한다(설계 함정 15: `plugin.py` -> `detect.py` ->
        `subprocess.run(timeout=60)`). 0.2.x 에서는 실패해도 수집만 꺼지는
        소프트 축이라 비용이 보이지 않았는데, 0.3.0 은 같은 인터프리터를
        **지도 제어의 전제**로 올리므로 "플러그인 적재가 멈춘 것처럼 보이는"
        경로가 된다. 그래서 해석을 스레드로 내리고 결과를 여기로 받는다.

        결과가 오기 전에는 축이 UNKNOWN 이고, UNKNOWN 은 기능을 막지 않는다.
        """
        self.embedded_python_status = str(status)
        self.embedded_python = str(path or "")
        self.embedded_python_why = str(why or "")

    def note_embedded_server(self, running, port, why):
        """내장 QGIS 서버 기동 결과를 받는다(0.3.0).

        Args:
            running: 소켓이 열렸는가.
            port: bind 후 회수한 실포트. 안 떴으면 0.
            why: 실패 사유 또는 성공 근거.
        """
        self.server_status_embedded = FOUND if running else MISSING
        self.server_port = int(port or 0)
        self.server_why = str(why or "")

    def note_upstream_plugin(self, loaded, why):
        """상류 QGIS MCP 플러그인(T1) 적재 여부를 받는다(0.3.0).

        Args:
            loaded: `qgis.utils` 에서 보였는가. None 이면 판정 불가(UNKNOWN).
            why: 어느 키에서 봤는지.
        """
        if loaded is None:
            self.upstream_plugin_status = UNKNOWN
        else:
            self.upstream_plugin_status = FOUND if loaded else MISSING
        self.upstream_plugin_why = str(why or "")

    def refresh_keys(self, reader=None):
        """공공 API 키 설정 상태를 다시 읽는다(0.2.1).

        키 저장/삭제 직후와 플러그인 적재 시에 불린다. **값을 보관하지
        않는다** - 어느 제공자가 설정됐는지만 들고 있는다.

        Args:
            reader: callable() -> (설정된 id 들, 비어 있는 id 들).
                None 이면 keystore.key_state. 하네스가 QgsSettings 없이
                두 상태를 재게 하는 주입점이다.

        Returns:
            str: 갱신된 상태(FOUND/MISSING/UNKNOWN).
        """
        fn = reader if reader is not None else keystore.key_state
        try:
            configured, missing = fn()
        except Exception as exc:  # noqa: BLE001 - 읽기 실패는 UNKNOWN 이다
            self.keys_status = UNKNOWN
            self.keys_configured = ()
            self.keys_missing = ()
            self.keys_why = "key state unreadable: %r" % (exc,)
            return self.keys_status
        self.keys_configured = tuple(configured or ())
        self.keys_missing = tuple(missing or ())
        # 판정은 **ANY** 다(0.5.0, 설계 docs/8 2-1). 종전 ALL 판정은 제공자가
        # 하나(vworld)일 때만 무해했다 - 레지스트리에 둘째 제공자가 들어오는
        # 순간 V-World 키만 가진 사용자의 수집 버튼이 영구 비활성되고 바에는
        # "키가 설정되지 않았습니다" 가 떴다. docs/2 7-3 의 `skills_found`
        # 결함과 같은 모양(전건 요구가 부분 충족을 죽인다)이다.
        # 데이터셋 수준 게이트는 이미 있다 - `list_datasets` 가 행마다
        # `key_configured` 를 돌려주고 스킬이 "false 면 멈추고 알려라" 를 적는다.
        if self.keys_configured:
            self.keys_status = FOUND
            self.keys_why = "keys set for %s" % ",".join(self.keys_configured)
            if self.keys_missing:
                self.keys_why += " (missing %s)" % ",".join(self.keys_missing)
        elif self.keys_missing:
            self.keys_status = MISSING
            self.keys_why = "no key for %s" % ",".join(self.keys_missing)
        else:
            # 키가 필요한 제공자가 애초에 없는 카탈로그(전부 auth=none)도
            # 여기로 온다 - MISSING 으로 두면 설정할 것이 없는데 버튼이 꺼진다.
            self.keys_status = FOUND
            self.keys_why = "no provider needs a key"
        return self.keys_status

    def keys_partial_text(self):
        """일부 제공자만 키가 있을 때의 경고 한 줄. 아니면 빈 문자열이다.

        Returns:
            str: 전제조건 바에 적을 한 줄. 값(키)은 들어가지 않는다.
        """
        if not (self.keys_configured and self.keys_missing):
            return ""
        names = ", ".join(self.keys_missing)
        return COLLECT_KEYS_PARTIAL_FMT % (names, names)

    def note_bundle(self, status, bundle_dir_path, why):
        """자체 스킬 번들 공급 결과를 기록한다(0.2.0).

        플러그인이 번들을 펼치고 그 결과를 여기에 넘긴다. 독은 이 값을 읽어
        단서 문구에 쓴다 - **비활성 사유로는 쓰지 않는다**(P-C 로 동작한다).
        """
        self.bundle_status = str(status)
        self.bundle_dir = str(bundle_dir_path or "")
        self.bundle_why = str(why or "")

    def note_init(self, init_event):
        """첫 init 으로 툴킷, MCP 2종, 스킬 2종을 채운다."""
        self.toolkit_status, self.toolkit_version, self.toolkit_why = (
            toolkit_from_init(init_event))
        if self.toolkit_status == UNKNOWN:
            # init 에 필드가 없는 환경이면 2순위로 떨어진다.
            self.toolkit_status, self.toolkit_version, self.toolkit_why = (
                toolkit_from_settings())
        self.mcp_status, self.mcp_detail, self.mcp_why = mcp_status_from_init(
            init_event)
        self.collect_status, self.collect_detail, self.collect_why = (
            mcp_status_from_init(init_event, posture.COLLECT_MCP_SERVER_NAME))
        self.skills_status, self.skills_found, self.skills_why = (
            skills_from_init(init_event))
        self.own_skills_status, self.own_skills_found, self.own_skills_why = (
            own_skills_from_init(init_event))
        self.init_seen = True

    def set_cwd(self, cwd):
        """cwd 가 바뀌면 프리셋 활성 상태를 다시 계산해야 한다(설계 6-3)."""
        self.cwd = str(cwd or "")

    def server_status(self, server_name):
        """서버 이름으로 탐지 상태를 돌려준다. 모르는 이름은 UNKNOWN 이다.

        0.3.0: `qgis` 축은 **내장 서버가 안 떴으면 init 을 기다리지 않는다.**
        소켓이 없으면 브리지가 preflight 에서 비정상 종료하므로 `connected`
        가 올 길이 없다 - 그 사실을 첫 전송 전에 알 수 있게 됐다(설계 5-2
        "새로 생기는 좋은 성질"). 내장 서버가 떴거나 UNKNOWN 이면 종전처럼
        init 판정(`mcp_status`)으로 떨어진다.
        """
        if server_name == posture.QGIS_MCP_SERVER_NAME:
            if self.server_status_embedded == MISSING:
                return MISSING
            return self.mcp_status
        if server_name == posture.COLLECT_MCP_SERVER_NAME:
            return self.collect_status
        return UNKNOWN

    def _server_state(self, preset):
        """프리셋의 서버 전제조건을 본다(설계 docs/2 7-2).

        Returns:
            tuple: (하드 미충족 사유 또는 "", 소프트 단서 또는 "")
        """
        hard = ""
        soft = ""
        for name, severity in PRESET_NEEDS_SERVERS.get(preset, ()):
            status = self.server_status(name)
            if status != MISSING:
                continue
            if name == posture.COLLECT_MCP_SERVER_NAME:
                text = COLLECT_SERVER_UNMET_TEXT
            else:
                # 0.3.0: "QGIS 에서 Run MCP 를 누르세요" 를 교체했다. Run MCP
                # 버튼은 상류 플러그인(T1)의 UI 이고 내장 서버에는 없다 -
                # 없는 버튼을 누르라고 적으면 사용자가 찾다가 포기한다.
                text = EMBEDDED_SERVER_UNMET_TEXT
            if severity == "hard" and not hard:
                hard = text
            elif severity != "hard" and not soft:
                soft = "QGIS MCP 가 연결되지 않아 지도 적재는 건너뜁니다"
        return hard, soft

    def preset_state(self, preset):
        """프리셋 하나가 지금 활성인가. 비활성이면 이유를 함께 준다.

        오탐으로 기능을 막지 않는다 - 툴킷이 UNKNOWN 이면 활성으로 둔다(설계 6-4).

        0.2.0(설계 docs/2 7-3 예고 결함 수정): **스킬 등재 검사를 툴킷 소속
        프리셋에만 적용한다.** `skills_found` 는 TOOLKIT_SKILLS 와의 교집합만
        담으므로, 자체 스킬에 그 검사를 걸면 툴킷이 정상 탐지된 환경에서
        수집 버튼이 **영구 비활성**된다. 자체 스킬은 (a) 번들 공급과
        (b) 수집 서버 연결로 판정하고, 스킬 미등재는 비활성 사유가 아니다
        (P-C 로 동작한다).

        Returns:
            tuple: (활성 여부, 이유 문자열)
        """
        owner = preset_owner(preset)
        if self.claude_status != FOUND:
            return False, "claude CLI 를 찾지 못했습니다"
        if owner == OWNER_TOOLKIT and self.toolkit_status == MISSING:
            return False, "툴킷(%s)이 설치되어 있지 않습니다" % TOOLKIT_NAME
        if owner == OWNER_PLUGIN and self.embedded_python_status == MISSING:
            return False, EMBEDDED_PYTHON_UNMET_TEXT
        # 키 축(0.2.1). 인터프리터 바로 뒤에 둔다 - 둘 다 init 전에 알 수 있고
        # 플러그인 소속 프리셋에만 걸린다. UNKNOWN 은 막지 않는다.
        if owner == OWNER_PLUGIN and self.keys_status == MISSING:
            return False, COLLECT_KEYS_UNMET_TEXT
        hard, soft = self._server_state(preset)
        if hard:
            return False, hard
        ok, missing = cwd_requirements(self.cwd, preset)
        if not ok:
            return False, "작업 폴더에 %s 가 없습니다" % ", ".join(missing)
        # 사전 판정(설계 6-4). init 이 스킬 목록을 실어 왔을 때만 보고,
        # **툴킷 프리셋에만** 적용한다(위 docstring).
        if owner == OWNER_TOOLKIT:
            if self.skills_status == MISSING:
                return False, "이 세션에 툴킷 스킬이 등재되지 않았습니다"
            if self.skills_status == FOUND and preset not in self.skills_found:
                return False, "이 세션에 %s 스킬이 등재되지 않았습니다" % preset
        if soft:
            return True, soft
        # 아직 모르는 서버가 있으면 활성으로 두고 단서만 붙인다. 탐지 실패를
        # "없음" 으로 단정하지 않는다(설계 6-4 마지막 원칙).
        if any(self.server_status(n) == UNKNOWN
               for n, _sev in PRESET_NEEDS_SERVERS.get(preset, ())):
            return True, "확인 중 (첫 턴의 init 에서 확인됩니다)"
        return True, ""

    def preset_states(self):
        """프리셋 5종의 (활성, 이유) 를 순서대로 돌려준다(설계 7-1 [3]).

        Returns:
            list[tuple]: (프리셋 이름, 활성 여부, 이유 문자열)
        """
        return [(p,) + tuple(self.preset_state(p)) for p in PRESET_ORDER]

    def unmet_items(self):
        """전제조건 바가 띄울 미충족 항목만 돌려준다(설계 7-1 [2]).

        첫 init 전에는 툴킷/MCP/스킬을 적지 않는다. 그때는 "미충족" 이 아니라
        "확인 중" 이고(D06 FAIL), 확인 중인 것을 미충족으로 적으면 기동할 때마다
        경고가 떠 있다.

        Returns:
            list[tuple]: (코드, 사용자에게 보일 한 줄)
        """
        items = []
        if self.claude_status != FOUND:
            items.append((
                "claude",
                "claude CLI 를 찾지 못했습니다. 터미널에서 claude 를 한 번 실행해 "
                "설치와 로그인 상태를 확인하세요.",
            ))
        # 0.3.0: uvx 행을 삭제했다(설계 5-2). 그 행이 하네스 14 C8 의 잠재
        # FAIL 원인이었고(장부 V28-A43) 삭제로 그 open 행이 닫힌다.
        #
        # 자식 서버 인터프리터는 init 전에 판정된다(파일 존재 + `-I` 프로브).
        # 이것이 없으면 **두 서버 항목이 다 설정에서 빠지므로** 지도 제어와
        # 수집이 함께 꺼진다. 그래서 init_seen 조기 반환보다 앞에 둔다 -
        # 게이트 4 FAIL 로 입력이 막히는 것이 설명돼야 한다.
        if self.embedded_python_status == MISSING:
            items.append(("embedded_python", EMBEDDED_PYTHON_UNMET_TEXT))
        # 내장 QGIS 서버 축도 init 전에 판정된다(0.3.0). 플러그인 적재 시점에
        # 소켓이 열렸는지가 정해지므로, 지도 제어 불가를 첫 전송 전에 알린다.
        if self.server_status_embedded == MISSING:
            items.append(("embedded_server", EMBEDDED_SERVER_UNMET_TEXT))
        # 키도 init 전에 판정된다(설정 읽기 하나다). 수집 버튼이 꺼진 이유를
        # 첫 전송 전에 읽을 수 있어야 한다 - 0.2.0 베타에서 사용자가 수집을
        # 시도한 뒤 도구 결과의 key_configured=false 로 알게 됐다(유료 1턴).
        if self.keys_status == MISSING:
            items.append(("collect_keys", COLLECT_KEYS_UNMET_TEXT))
        else:
            # 부분 충족은 **막지 않고 알린다**(설계 docs/8 2-1). 버튼은 활성인
            # 상태로 어느 제공자가 비었는지 한 줄 적는다.
            partial = self.keys_partial_text()
            if partial:
                items.append(("collect_keys_partial", partial))
        if not self.init_seen:
            return items
        if self.toolkit_status == MISSING:
            items.append((
                "toolkit",
                "툴킷(%s)이 설치되어 있지 않습니다." % TOOLKIT_NAME,
            ))
        elif self.toolkit_status == UNKNOWN:
            items.append((
                "toolkit",
                "툴킷(%s)을 확인하지 못했습니다. 프리셋은 그대로 쓸 수 있습니다."
                % TOOLKIT_NAME,
            ))
        # 0.3.0: 문구를 교체했다. init 이 `qgis` 미연결을 보고했는데 내장
        # 서버는 떠 있는 경우다 - 브리지가 못 붙었거나 인터프리터가 문제다.
        # "Run MCP" 를 누르라고 적을 수 없다(그 버튼이 없다).
        if self.mcp_status == MISSING and self.server_status_embedded != MISSING:
            items.append((
                "mcp",
                "QGIS 브리지가 연결되지 않았습니다. QGIS 로그 패널의 "
                "'UPWISE Chat' 탭과 브리지 로그를 확인하세요.",
            ))
        # 수집 서버는 **소프트**다(설계 docs/2 3-2 항목 2). 바에 한 줄을 적고
        # 수집 버튼만 비활성이며 입력은 열려 있다. 문구가 MCP 축과 달라야
        # 사용자가 "채팅도 막혔나" 를 묻지 않는다.
        if self.collect_status == MISSING:
            items.append(("collect_server", COLLECT_SERVER_UNMET_TEXT))
        return items

    def summary(self):
        """진단 로그와 검증 하네스가 읽는 한 dict."""
        return {
            # 0.5.5 신설. 어느 백엔드로 탐지했는가. **값이 아니라 식별자**다 -
            # GPT 모드가 들어오면 사용자 로그만 보고 어느 CLI 였는지 가른다.
            "backend": self.backend_name,
            "claude": self.claude_status,
            "claude_exe": self.claude_exe,
            "claude_why": self.claude_why,
            # 0.3.0: uvx 3칸을 삭제했다(설계 5-2). 그 자리에 내장 서버 축이
            # 온다 - 독이 첫 init 에서 prereq_detect 한 줄로 이 dict 를
            # 찍으므로(dock._note_init_detect) 사용자 로그만 보고 서버가
            # 어느 포트에 떴는지 알 수 있다. **토큰은 넣지 않는다.**
            "embedded_server": self.server_status_embedded,
            "embedded_server_port": self.server_port,
            "embedded_server_why": self.server_why,
            "upstream_plugin": self.upstream_plugin_status,
            "upstream_plugin_why": self.upstream_plugin_why,
            "toolkit": self.toolkit_status,
            "toolkit_version": self.toolkit_version,
            "toolkit_why": self.toolkit_why,
            "mcp": self.mcp_status,
            "mcp_detail": self.mcp_detail,
            "skills": self.skills_status,
            "skills_found": list(self.skills_found),
            "cwd": self.cwd,
            "init_seen": self.init_seen,
            # 0.2.0 수집 축. `package_*` 두 칸을 걷어낸 자리다(설계 docs/2
            # 7-2: 쓰는 프리셋이 0 이 되면 잔여 scaffolding 이다).
            "embedded_python": self.embedded_python_status,
            "embedded_python_exe": self.embedded_python,
            "embedded_python_why": self.embedded_python_why,
            "collect_server": self.collect_status,
            "collect_detail": self.collect_detail,
            "bundle": self.bundle_status,
            "bundle_dir": self.bundle_dir,
            "bundle_why": self.bundle_why,
            "own_skills": self.own_skills_status,
            "own_skills_found": list(self.own_skills_found),
            # 0.2.1 키 축. **값이 들어가지 않는다** - 제공자 id 와 상태뿐이다.
            # 이 dict 는 독이 진단 로그에 한 줄로 찍으므로(dock._note_init_detect)
            # 값이 들어가면 그 줄이 유출면이 된다.
            "collect_keys": self.keys_status,
            # 부분 충족 축(0.5.0). `unmet_items()` 의 코드와 **같은 이름**이어야
            # 바의 심각도 조회(dock._leveled_items)가 맞는다.
            "collect_keys_partial": (MISSING if self.keys_partial_text()
                                     else FOUND),
            "collect_keys_configured": list(self.keys_configured),
            "collect_keys_missing": list(self.keys_missing),
        }
