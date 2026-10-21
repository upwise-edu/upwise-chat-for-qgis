"""공공 API 수집 전담 MCP stdio 서버 (0.2.0, 설계 docs/2 2-3 결정 E4).

왜 별도 프로세스인가
    수집 1회는 바깥 HTTP GET 을 해야 한다. 독은 셸을 노출하지 않고 `WebFetch`
    도 노출하지 않으므로(설계 docs/2 2-3) 모델이 직접 네트워크를 칠 수단이
    없다. 그래서 플러그인이 두 번째 MCP 서버를 띄워 **egress 를 자기가 소유**
    한다. 모델은 "무엇을 어디서 받을지" 만 고르고, 돌아온 경로를
    `add_vector_layer` 에 넘긴다.

키 불변식 (이 파일의 존재 이유)
    API 키는 모델 컨텍스트에 들어가지 않는다. 한 번 들어가면 모델 제공자
    서버, CLI 자신의 세션 저장소, 우리 jsonl, 전사 네 곳에 동시에 남고 앞의
    둘은 지울 수 없다(장부 V28-A52 실측). 그래서
        * 키는 argv 에도 `--mcp-config` 에도 환경변수에도 담기지 않는다.
        * 이 서버가 QGIS 설정 INI 를 configparser 로 **직접** 읽는다.
        * 도구 결과와 로그의 URL 은 키 자리를 마스킹한다.
    env 로 받는 것은 INI 경로와 키 접두사뿐이다(설계 docs/2 5-3 K6).

stdlib 전용인 이유
    백엔드가 자식 환경에서 PYTHON 오염 4키를 제거하고(0.1.2, 장부 V28-30) 그
    정화가 손자인 이 서버까지 상속된다. `PYTHONPATH` 가 없는 환경에서 자기
    모듈을 찾아야 하므로 **단일 파일**로 두고 `-I` 로 띄운다. 패키지 상대
    import 도 쓰지 않는다 - `-I` 는 sys.path 에 스크립트 폴더만 남긴다.

인터프리터
    이 파일을 띄우는 command 는 `<QGIS_ROOT>/apps/Python312/python.exe` 계열
    **절대경로**다. QGIS 런처의 `bin/python3.exe` 는 `-I` 아래에서 표준
    라이브러리를 못 찾아 즉사한다(장부 V28-P18). 해석과 부트 프로브는
    backend/detect.resolve_collect_python 이 한다.

노출 도구 3종 (설계 docs/2 4-1. 폴링 도구는 두지 않는다 - 동기 반환이다)
    list_datasets      무엇을 받을 수 있나 (제공자/질의/페이지 인자)
    describe_dataset   그 데이터셋의 필수 인자가 무엇인가
    collect            서버가 받고 저장하고 요약을 돌려준다

제공자가 늘어도 도구는 3종이다 (설계 docs/8 3-2 안 A)
    제공자별 코드가 아니라 **제공자별 데이터**로 간다. 카탈로그 파일이
    엔드포인트·인증·페이징·응답 봉투를 선언하고, 서버는 디스패치 3지점
    (카탈로그 조회 / 호출 조립 / 응답 파싱)에서 그 선언을 읽는다. 도구를
    더하면 `posture.COLLECT_TOOLS` 와 포스처 집합 수치가 함께 흔들린다.

응답 봉투는 선언이고, 선언이 빗나가면 큰 소리로 실패한다 (설계 docs/8 2-4)
    봉투가 다른 제공자에서 `features` 를 고정으로 훑으면 예외가 아니라
    **0건**이 나오고, 사용자 눈에는 "그 지역에 데이터가 없다" 와 같아진다.
    그래서 선언된 경로가 응답에 없으면 성공으로 끝내지 않는다 - 원본은
    남기고, `incomplete` 를 세우고, 본 최상위 **키 이름**만 돌려준다.

페이징도 선언이다 (설계 docs/8 3-1)
    `paging` 은 문자열("none" / "tile_subdivide")이거나 dict 다. dict 의
    `mode=page_no` 는 **총건수로 끝을 알고, 못 읽으면 빈 페이지로 끝낸다.**
    한 조건만 두면 총건수를 안 주는 기관 API 에서 무한 루프가 된다. 상한은
    기존 `LIMIT_PAGES` 와 같은 자리이고, 선언의 `max_pages` 가 그보다 작은
    상한을 둘 수 있다. 상한에서 멈추면 `incomplete=true` 다.

키 형식은 제공자별이다 (설계 docs/8 3-5)
    전역 `KEY_RE` 를 넓히지 않는다. base64 계열 키를 받는 제공자는
    `providers.<id>.key_re` 로 자기 집합만 넓히고, 공백·줄바꿈과 퍼센트
    인코딩(`%XX`)은 어느 제공자에서도 거절한다 - 이중 인코딩으로 서비스키
    미등록 오류가 나는 실패 계열을 입력 단계에서 닫는다(사용자 결정 D7).

비밀 집합은 동적이다 (설계 docs/8 2-3 I-1)
    마스킹 대상은 저장된 키 하나가 아니라 **런타임 비밀 레지스터 전체**다
    (키 + 그 인코딩 변형 + 앞으로 발급될 토큰). 응답 본문도 같은 집합을
    통과한 뒤에 디스크와 도구 결과로 간다 - V-World GetCapabilities 가 요청
    URL 을 응답에 되돌린 실측이 있다(설계 docs/8 10 첫 항목).

쓰기 경로를 모델이 고르지 못한다
    저장 폴더는 서버가 정하고 돌려준다. 모델은 경로 인자를 받지 못한다
    (더미 서버 G3 패턴과 같다). 그래서 "파일이 생겼는가" 가 모델 발화가
    아니라 디스크 사실로 판정된다.

설계 정본: docs/2.collect_feature_design_v1.md 2, 4, 5
"""

import configparser
import csv
import io
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

PROTOCOL_FALLBACK = "2025-06-18"

# 서버 이름. 플래그 조립 쪽(backend/posture.COLLECT_MCP_SERVER_NAME)과 같은
# 문자열이어야 도구 이름 접두사가 allowlist 와 맞는다.
SERVER_NAME = "upwise_collect"
# 수집 산출물의 **유일한 빌드 출처 필드**다. `_summarize` 가 사이드카
# (`collect_meta.json`)에 `plugin_version` 으로 싣고 initialize 의
# serverInfo.version 으로도 나간다. 그래서 metadata.txt 의 version 과 같아야
# 하고, 어긋나면 산출물만 보고 어느 빌드가 만든 것인지 알 수 없다.
# 0.5.0 까지 "0.2.0" 으로 남아 세 마이너 낡아 있었다(V37-A09 적발).
# **이 서버는 `python -I` stdlib 전용 단일 파일**이라 런타임에 플러그인
# 모듈을 import 할 수 없어서, 상수로 두고 드리프트는 하네스가 잡는다
# (23 의 A6: SERVER_VERSION == metadata.txt 의 version, 양성 대조군 A6_pos).
# 릴리스 때 metadata.txt 를 올리면 여기도 같이 올린다.
SERVER_VERSION = "0.5.4"

# --------------------------------------------------------------- 환경변수 계약
# 전부 플러그인이 per-server env 블록으로 넣는다. **키는 여기 없다.**
ENV_SETTINGS_INI = "UPWISE_COLLECT_SETTINGS_INI"
ENV_KEY_PREFIX = "UPWISE_COLLECT_KEY_PREFIX"
ENV_WORKSPACE = "UPWISE_COLLECT_WORKSPACE"
ENV_REGISTRY = "UPWISE_COLLECT_REGISTRY"
ENV_LOG = "UPWISE_COLLECT_LOG"

# 산출물 고정 하위 폴더. cwd 가 아니라 **workspace 아래**다 - cwd 는 사용자의
# QGIS 프로젝트 폴더일 수 있고(장부 G8) 거기에 수집물을 쏟지 않는다.
COLLECTED_SUBDIR = "collected"
LOGS_SUBDIR = "_logs"

# 설정 키(QgsSettings 경로 표기). 서버는 INI 에서 이 경로를 찾는다.
SETTING_ENDPOINT_OVERRIDE = "upwise_chat/collect/endpoint_override"

# 한도 기본값(설계 docs/2 4-5). 측정값이 아니라 보수적으로 고른 설계 결정이다.
# 모델 루프가 키 쿼터와 디스크를 소모하는 경로를 서버가 막는 유일한 가드다.
LIMIT_PAGES = 50
LIMIT_BYTES = 50 * 1024 * 1024
LIMIT_SECONDS = 120.0
LIMIT_CALLS_PER_SESSION = 20

# HTTP 재시도(설계 docs/2 4-5). 401/403 은 재시도하지 않는다 - 키 거부를
# 반복해도 결과가 바뀌지 않고 쿼터만 쓴다.
RETRY_STATUS = (429, 500, 502, 503, 504)
RETRY_MAX = 3
RETRY_BACKOFF_S = (1.0, 2.0, 4.0)
HTTP_TIMEOUT_S = 60.0

# 타일 재귀 분할 상한(V-World WFS 는 maxFeatures 1000 상한만 있고 페이지
# 파라미터가 없다 - 강의 러너가 쓴 방식과 같다). 깊이를 제한해야 응답이
# 상한에 계속 걸리는 영역에서 무한 분할하지 않는다.
TILE_MAX_DEPTH = 3

# 키 형식 검사(설계 docs/2 5-3 단서 1). QSettings 는 INI 에서 특수문자를
# 인코딩하므로 디코딩이 애매할 수 있다. 공공 API 키는 영숫자와 하이픈이고,
# 그 밖이면 **추측하지 않고** 구조화 오류로 끝낸다.
#
# **전역 식을 넓히지 않는다**(설계 docs/8 3-5). data.go.kr 은 base64 계열
# (`+` `/` `=`)을 받아야 하지만 그 집합을 이 식에 더하면 V-World·SGIS 가
# 받아들이는 집합까지 함께 넓어져 오타 방어가 사라진다. 제공자별 완화는
# `providers.<id>.key_re` 선언으로만 한다(제공자별 코드가 아니라 데이터).
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

# 제공자 선언이 넓힐 수 있는 상한. 선언이 이 식을 벗어나는 문자를 허용하면
# 거절한다 - 카탈로그 한 줄로 "아무 문자나 키" 가 되는 길을 막는다. 공백·
# 제어문자·줄바꿈은 어떤 제공자에서도 허용하지 않는다(붙여넣기 부산물).
KEY_RE_CEILING = re.compile(r"^[A-Za-z0-9_\-+/=.~]{8,512}$")

# 퍼센트 인코딩 탐지(설계 docs/8 3-5, 사용자 결정 D7). data.go.kr 포털은
# Encoding 키와 Decoding 키를 둘 다 준다. 저장값이 Encoding 형이면 서버가
# urlencode 로 한 번 더 감싸 이중 인코딩이 되고 제공자가
# SERVICE_KEY_IS_NOT_REGISTERED_ERROR 를 돌려준다. 그 실패 계열을 입력
# 단계에서 닫는다.
KEY_PERCENT_RE = re.compile(r"%[0-9A-Fa-f]{2}")

# 공백·제어문자 탐지. 붙여넣기로 줄바꿈이 섞여 들어오는 사고를 잡는다.
KEY_BLANK_RE = re.compile(r"[\s\x00-\x1f\x7f]")

# D7 기본값(설계 docs/8 8). 제공자 선언이 `key_form` 을 적지 않으면 이 값이다.
# "형식 선택 라디오" 를 두지 않는 이유는 상태가 둘로 늘어 하네스 행이 2배가
# 되는 것에 비해 얻는 것이 없다는 판정이다(U8 측정으로 닫았다).
KEY_FORM_DEFAULT = "decoding"

# 토큰 재발급 상한. **1회뿐이다**(설계 docs/8 2-3). 제공자 오류를 토큰 만료로
# 읽고 무한 재인증하면 SGIS 일 50,000 회 쿼터를 한 번의 수집이 태운다.
TOKEN_REAUTH_MAX = 1

# 레다크션 최소 길이(설계 docs/2 5-4). 짧은 값을 치환하면 본문이 잠식된다.
REDACT_MIN_LEN = 12
REDACT_TOKEN = "***REDACTED***"

# 카탈로그 파일 구성(설계 docs/8 4-1). 레지스트리 파일 옆의 동봉 스냅샷 3개와
# 프로필 아래 사용자 등록 파일 1개를 더해 **5파일**을 병합한다. 없는 파일은
# 조용히 건너뛴다 - 스냅샷이 아직 전사되지 않은 회차에서도 서버가 떠야 한다.
# `collect_catalog_datago.json` 은 데이터셋이 0건이고 제공자 정의와 등록
# 프리셋만 담는다 - data.go.kr 은 공식 카탈로그 API 가 없어 데이터셋이
# 사용자 등록으로만 생긴다(설계 docs/8 3-5).
CATALOG_SIBLINGS = ("collect_catalog_vworld.json", "collect_catalog_sgis.json",
                    "collect_catalog_datago.json")
USER_CATALOG_SUBPATH = ("upwise_chat", "collect_user_registry.json")

# 사용자 등록 레코드 id 접두(설계 docs/8 4-1). 동봉 id 와 사용자 id 를 접두로
# 가르지 않으면 조용한 덮어쓰기가 "목록에는 보이는데 다른 데로 요청이 간다" 를
# 만든다. 그래서 접두를 양방향으로 강제하고 충돌은 거절한다.
USER_ID_PREFIX = "user."

# 목록 압축(설계 docs/8 2-5). 158 종 + 제공자 3사가 되면 전량 반환이 호출마다
# 수십 KB 를 모델 컨텍스트로 밀어 넣는다. 상세는 describe_dataset 이 맡는다.
LIST_LIMIT_DEFAULT = 30
LIST_LIMIT_MAX = 100

# 미지원 항목의 사유를 목록 행에 실을 때의 길이 상한. 카탈로그 `local.notes`
# 전문은 두 문장 이상이라 30행 전부에 실으면 압축형의 의미가 없어진다. 그래서
# **머리 1문장**만 자르고 이 길이에서 끊는다(2026-10-17 측정: V-World 미지원
# 4종의 머리 문장이 62자). 사유를 아예 안 실으면 모델이 "왜 못 받는지" 를
# describe_dataset 을 한 번 더 불러야 알 수 있다.
NOTES_HEAD_MAX = 120

# 응답 봉투 선언이 빗나갔을 때 진단으로 돌려줄 최상위 **키 이름** 수 상한
# (설계 docs/8 2-4). 이름만 싣는다 - 값을 실으면 그 자리가 유출면이 된다.
TOP_KEYS_MAX = 20

# 선언 가능한 응답 봉투(설계 docs/8 3-1). 이 밖의 값은 추측하지 않고 거절한다.
RESPONSE_KINDS = ("geojson", "json_records", "xml_records")

# 선언 가능한 페이징 방식(설계 docs/8 3-1). `paging` 은 문자열("none" /
# "tile_subdivide")이거나 dict({"mode": "page_no", ...})다 - 구 레지스트리
# 항목이 문자열을 쓰고 있어 두 모양을 다 받는다.
PAGING_MODES = ("none", "tile_subdivide", "page_no")

# 템플릿 참조로 물려받을 때 **얕은 병합이 아니라 키 단위 병합**이 필요한 필드.
# 항목이 params 한 칸을 더하려고 템플릿의 params 전체를 다시 적게 하지 않는다.
TEMPLATE_DICT_FIELDS = ("fixed_params", "params", "response", "paging")

# collect 의 `args` 맵에 들어오면 거절하는 이름(설계 docs/8 3-2). 이 셋은 전용
# 인자로 받으므로 args 로도 들어오면 같은 질의 파라미터가 두 번 조립된다.
ARGS_RESERVED = ("bbox", "max_features", "crs")

# args 값에서 거절하는 문자. 값은 전부 urlencode 를 거치므로 `&`·`?` 주입은
# 성립하지 않지만, 개행과 NUL 은 로그 한 줄을 쪼개므로 입구에서 막는다.
ARGS_FORBIDDEN_CHARS = ("\n", "\r", "\x00")

# 포털 검색 딥링크(조사 docs/3 4차 측정의 (c)). 검색어 길이 상한이다. 링크는
# 사람이 브라우저에서 열 주소라 긴 문장을 그대로 실을 이유가 없고, 상한이
# 없으면 모델이 넘긴 문단 전체가 도구 결과와 서버 로그 한 줄에 들어온다.
PORTAL_QUERY_MAX = 80

# 검색어에서 공백 한 칸으로 접는 문자. 개행·탭·제어문자는 CSV·서버 로그의
# 한 줄을 쪼개고, 링크에 실릴 이유도 없다.
PORTAL_QUERY_FOLD_RE = re.compile(r"[\s\x00-\x1f\x7f]+")


# ---------------------------------------------------------------------- 로깅
class ServerLog:
    """파일 전용 서버 로그. stderr 를 쓰지 않는다.

    stderr 는 claude CLI 가 읽어 독의 진단 패널로 흘리므로, 수집 서버의 수십
    줄짜리 프로토콜 기록이 그 채널을 메운다. 그래서 파일로만 남긴다.
    """

    def __init__(self, path):
        """로그 파일 경로를 잡는다. 열기는 쓸 때 한다.

        Args:
            path: 로그 파일 절대경로. 빈 값이면 아무 것도 쓰지 않는다.
        """
        self.path = str(path or "")

    def write(self, kind, detail=""):
        """한 줄 즉시 flush. 로깅 실패가 서버를 죽이지 않는다."""
        if not self.path:
            return
        line = "%s\t%s\t%s" % (
            time.strftime("%Y-%m-%dT%H:%M:%S"), kind,
            str(detail).replace("\r", " ").replace("\n", " | "))
        try:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
        except Exception:  # noqa: BLE001 - 로깅 실패가 수집을 막지 않는다
            pass


class CollectCsvLog:
    """수집 1건마다 한 줄 쌓는 CSV (저장소 ALWAYS LOG 규칙).

    위치는 `<workspace>/collected/_logs/collect_<시각>.csv` 다. 항목마다 즉시
    flush 하므로 중단되어도 완료분과 실패분이 남는다.
    """

    COLUMNS = ["ts", "dataset", "params", "pages", "bytes", "features",
               "crs", "status", "elapsed_s", "url_masked", "error"]

    def __init__(self, root):
        """로그 폴더를 만들고 파일 경로를 정한다.

        Args:
            root: `<workspace>/collected` 폴더.
        """
        self.dir = os.path.join(str(root), LOGS_SUBDIR)
        self.path = os.path.join(
            self.dir, "collect_%s.csv" % time.strftime("%y%m%d_%H%M%S"))

    def row(self, **fields):
        """한 줄 기록. 헤더는 파일이 비었을 때만 쓴다."""
        try:
            os.makedirs(self.dir, exist_ok=True)
            fresh = (not os.path.exists(self.path)
                     or os.path.getsize(self.path) == 0)
            with open(self.path, "a", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                if fresh:
                    writer.writerow(self.COLUMNS)
                writer.writerow([str(fields.get(c, "")) for c in self.COLUMNS])
                fh.flush()
        except Exception:  # noqa: BLE001 - 로깅 실패가 수집을 막지 않는다
            pass


# ------------------------------------------------------------------ 설정 읽기
def qsettings_unescape(raw):
    """QSettings INI 값에서 따옴표와 퍼센트 인코딩을 되돌린다.

    QSettings 는 공백이나 특수문자가 든 값을 따옴표로 싸고 비 ASCII 를
    `%XX` 또는 `%UXXXX` 로 적는다. 알 수 없는 이스케이프는 **추측하지 않고**
    예외로 올린다(설계 docs/2 5-3 단서 1).

    Args:
        raw: INI 에서 읽은 날 문자열.

    Returns:
        str: 되돌린 값.

    Raises:
        ValueError: 해석할 수 없는 이스케이프가 있을 때.
    """
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    if "%" not in text:
        return text
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue
        tail = text[i + 1:i + 2].upper()
        if tail == "U" and re.match(r"^[0-9A-Fa-f]{4}", text[i + 2:i + 6] or ""):
            out.append(chr(int(text[i + 2:i + 6], 16)))
            i += 6
            continue
        if re.match(r"^[0-9A-Fa-f]{2}", text[i + 1:i + 3] or ""):
            out.append(chr(int(text[i + 1:i + 3], 16)))
            i += 3
            continue
        raise ValueError("unknown QSettings escape at %d" % i)
    return "".join(out)


def read_setting(ini_path, dotted_key):
    """QGIS 설정 INI 에서 값 하나를 읽는다.

    QSettings 는 `a/b/c` 경로를 INI 의 `[a]` 섹션 + `b\\c` 옵션으로 적는다.
    사본이 하나뿐인 자리이므로 서버가 직접 읽는다 - 키를 env 나 argv 로
    옮기면 복제가 생긴다(설계 docs/2 5-3).

    Args:
        ini_path: `QGIS3.ini` 절대경로.
        dotted_key: `upwise_chat/keys/vworld` 같은 설정 경로.

    Returns:
        tuple: (값 또는 "", 근거 문자열)
    """
    if not ini_path or not os.path.isfile(ini_path):
        return "", "settings ini not found"
    parser = configparser.RawConfigParser(strict=False)
    # QSettings 는 옵션 이름의 대소문자를 보존한다. configparser 기본
    # optionxform 은 소문자로 접으므로 비교를 깨뜨린다.
    parser.optionxform = str
    try:
        with open(ini_path, "r", encoding="utf-8", errors="replace") as fh:
            parser.read_file(fh)
    except Exception as exc:  # noqa: BLE001 - 설정 파싱 실패는 사유로 돌려준다
        return "", "settings ini unreadable: %r" % (exc,)
    parts = [p for p in str(dotted_key).split("/") if p]
    if len(parts) < 2:
        return "", "setting key needs at least one group"
    section = parts[0]
    rest = parts[1:]
    # QSettings 표기와 사람이 손으로 적은 표기 양쪽을 본다.
    wanted = ("\\".join(rest), "/".join(rest))
    for sec in parser.sections():
        if sec.lower() != section.lower():
            continue
        for option in parser.options(sec):
            if option.lower() in tuple(w.lower() for w in wanted):
                try:
                    return qsettings_unescape(parser.get(sec, option)), "ini"
                except ValueError as exc:
                    return "", "value unescape failed: %s" % exc
    return "", "setting absent"


def registry_default_path():
    """동봉 레지스트리 JSON 경로. env 가 비었을 때의 기본값이다."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "collect_registry.json")


def catalog_paths(registry_env, ini_path):
    """병합 대상 카탈로그 파일 경로를 **적재 순서대로** 돌려준다.

    순서가 규칙이다(설계 docs/8 4-1): 동봉 레지스트리 -> 동봉 스냅샷 3개 ->
    사용자 등록 파일. 사용자 파일 경로는 프로필에서 나오고, 서버가 아는 유일한
    프로필 단서는 설정 INI 경로다(`<프로필>/QGIS/QGIS3.ini`).

    Args:
        registry_env: `UPWISE_COLLECT_REGISTRY` 값. 비면 동봉본.
        ini_path: 설정 INI 절대경로. 비면 사용자 파일을 찾지 않는다.

    Returns:
        tuple: 파일 경로 문자열들. 존재 여부는 보지 않는다.
    """
    base = str(registry_env or "") or registry_default_path()
    folder = os.path.dirname(os.path.abspath(base))
    out = [base] + [os.path.join(folder, name) for name in CATALOG_SIBLINGS]
    ini = str(ini_path or "")
    if ini:
        profile = os.path.dirname(os.path.dirname(os.path.abspath(ini)))
        out.append(os.path.join(profile, *USER_CATALOG_SUBPATH))
    return tuple(out)


def catalog_signature(paths):
    """카탈로그 전 파일의 (존재, mtime, 크기) 지문. 핫리로드 판정에 쓴다.

    MCP 서버는 CLI 가 띄우므로 플러그인이 단독으로 재시작할 수 없다. 사용자가
    등록 직후 수집하려면 호출마다 지문을 보는 것이 유일한 경로다(설계 docs/8
    4-1). 비용은 stat 5회다(동봉 4 + 사용자 1).
    """
    sig = []
    for path in paths:
        try:
            st = os.stat(path)
            sig.append((path, int(st.st_mtime_ns), int(st.st_size)))
        except OSError:
            sig.append((path, 0, -1))
    return tuple(sig)


def read_catalog_file(path):
    """카탈로그 파일 하나를 읽는다. 없으면 조용히 건너뛴다.

    Args:
        path: JSON 파일 경로.

    Returns:
        tuple: (본문 dict 또는 None, 사유 문자열)
    """
    if not os.path.isfile(path):
        return None, "absent"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            body = json.load(fh)
    except Exception as exc:  # noqa: BLE001 - 파일 오류는 사유로 돌려준다
        return None, "unreadable: %r" % (exc,)
    if not isinstance(body, dict):
        return None, "not a json object"
    return body, "ok"


def provider_key_pattern(providers, pid):
    """제공자별 키 형식 식을 돌려준다(설계 docs/8 3-5).

    전역 `KEY_RE` 를 넓히지 않는 이유가 이 함수의 존재 이유다 - data.go.kr 은
    base64 계열(`+` `/` `=`)을 받아야 하는데 그 집합을 전역 식에 더하면
    V-World·SGIS 의 오타 방어가 같이 사라진다. 그래서 완화는 **제공자 선언
    한 줄**로만 하고, 선언이 `KEY_RE_CEILING` 을 벗어나는 문자를 허용하면
    그 선언 자체를 쓰지 않는다.

    Args:
        providers: 병합된 providers dict.
        pid: 제공자 id.

    Returns:
        tuple: (컴파일된 정규식, key_form 문자열, 근거 문자열)
    """
    meta = (providers or {}).get(str(pid or "")) or {}
    form = str(meta.get("key_form") or KEY_FORM_DEFAULT)
    raw = str(meta.get("key_re") or "")
    if not raw:
        return KEY_RE, form, "global"
    try:
        pattern = re.compile(raw)
    except re.error as exc:
        return KEY_RE, form, "provider key_re unusable (%s), global used" % exc
    # 선언을 그대로 믿지 않는다. 식이 실제로 넓힌 집합을 상한으로 되짚는다 -
    # 상한 밖 문자를 한 글자라도 받으면 선언을 버리고 전역 식으로 돌아간다.
    # 탐침 본문을 40자로 두는 이유: 길이 하한이 긴 식에서 짧은 탐침은 문자
    # 집합이 아니라 **길이** 때문에 불일치해 검사가 공허해진다. 금지 문자를
    # 끝이 아니라 **가운데**에 끼우는 이유: 파이썬 `$` 는 끝의 개행 하나를
    # 허용하므로, 끝에 붙인 `\n` 탐침은 어떤 식에서도 적중해 전건 오판이 된다
    # (2026-10-17 실측으로 밟았다).
    for ch in ("\n", " ", "\t", "\x00", "<", ">", "&", "?", "#", "%"):
        probe = "A" * 20 + ch + "A" * 20
        if pattern.match(probe):
            return (KEY_RE, form,
                    "provider key_re accepts a forbidden char, global used")
    return pattern, form, "provider"


def validate_key_value(value, pattern=None, key_form=KEY_FORM_DEFAULT):
    """키 값 하나를 형식 검사한다. **값은 사유에 적지 않는다.**

    순서가 규칙이다. (1) 공백·제어문자는 어느 제공자에서도 거절한다
    (붙여넣기 부산물). (2) `%XX` 가 있으면 Encoding 키이므로 거절하고
    "Decoding 키를 넣으세요" 를 사유로 돌려준다(설계 docs/8 3-5, D7 기본값).
    (3) 그 다음에 제공자 식으로 본다.

    `key_form` 이 `encoding` 인 제공자는 (2) 를 건너뛴다. 지금 동봉 선언에
    그런 제공자는 없고, D7 이 "Decoding 전용" 으로 확정됐으므로 이 분기는
    선언이 바뀌었을 때를 위한 자리다.

    Args:
        value: 설정에서 읽은 키 값.
        pattern: 제공자별 컴파일된 식. None 이면 전역 `KEY_RE`.
        key_form: `decoding` 또는 `encoding`.

    Returns:
        tuple: (통과했는가, 사유 문자열). 통과면 사유는 빈 문자열이다.
    """
    text = "" if value is None else str(value)
    if not text:
        return False, "키가 비어 있습니다"
    if KEY_BLANK_RE.search(text):
        return False, ("키에 공백이나 줄바꿈이 섞여 있습니다. 앞뒤 공백 없이 "
                       "한 줄로 붙여넣으세요.")
    if str(key_form) != "encoding" and KEY_PERCENT_RE.search(text):
        return False, ("Decoding 키를 넣으세요. 지금 값은 퍼센트 인코딩(%XX)이 "
                       "들어간 Encoding 키 모양이고, 이대로 보내면 이중 "
                       "인코딩으로 서비스키 미등록 오류가 납니다.")
    if not (pattern or KEY_RE).match(text):
        return False, "키 형식을 읽지 못했습니다(설정 값의 인코딩 확인 필요)"
    return True, ""


def validate_base_url(url):
    """등록 레코드의 `base_url` 구조 검사(설계 docs/8 4-3, 불변식 I-2).

    셋 다 **네트워크 0회**로 끝나는 구조 검사다. 호출해 보고 판정하지 않는다 -
    저장 시점에 플러그인 프로세스가 egress 를 가지면 URL 로그 지점이 하나
    늘어난다(설계 docs/8 4-3).

    Args:
        url: 레코드가 적은 엔드포인트.

    Returns:
        str: 거절 사유. 통과면 빈 문자열이다.
    """
    text = str(url or "")
    if not text:
        return "base_url is empty"
    if "{" in text or "}" in text:
        return "path template"
    if not text.startswith("https://"):
        return "insecure url (https required)"
    if "?" in text or "#" in text:
        return "query string in url (use fixed_params/params)"
    return ""


def portal_query_clean(value):
    """포털 검색어를 링크에 실을 수 있는 한 줄로 정리한다.

    모델이 넘긴 `query` 를 그대로 쓰지 않는 이유는 둘이다. 개행·제어문자는
    도구 결과와 서버 로그의 한 줄을 쪼개고, 길이 상한이 없으면 문단 전체가
    링크에 실린다. 값 자체의 `&`·`?` 는 여기서 지우지 않는다 - 조립이
    `urlencode` 한 군데를 지나므로 파라미터 주입으로 자라지 못한다.

    Args:
        value: 검색어 원문.

    Returns:
        str: 공백 한 칸으로 접고 상한에서 끊은 검색어. 빈 값이면 빈 문자열.
    """
    text = PORTAL_QUERY_FOLD_RE.sub(" ", str(value or "")).strip()
    return text[:PORTAL_QUERY_MAX]


def portal_search_link(providers, query=""):
    """포털 검색 딥링크 1건을 만든다. 선언한 제공자가 없으면 None 이다.

    **링크 생성만 한다.** 서버는 이 주소를 조회하지 않는다 - 조사 docs/3
    4차 측정에서 (a)(전수 스냅샷 12,015건)를 기각한 1차 근거가 그 목록 경로가
    `robots.txt` 의 Disallow 에 있다는 실측이었고, (c) 를 고른 이유가 크롤링 0
    이다. 사용자가 브라우저에서 열고, 포털에서 활용신청을 하고, 승인된 뒤에
    키 패널 등록 섹션에서 등록한다.

    주소의 세 조각(`base_url`·`fixed_params`·`query_param`)은 전부 **동봉
    카탈로그 선언**에서 온다 - 코드가 파라미터 이름을 만들어 내지 않는다
    (발명 금지, 설계 docs/2 4-2). 선언이 `validate_base_url` 불변식을 깨면
    (https 아님·질의 문자열 포함·경로 템플릿) 링크를 만들지 않는다.

    Args:
        providers: 병합된 providers dict.
        query: 사용자가 찾는 데이터 이름. 비우면 고정 파라미터만 붙는다.

    Returns:
        dict or None: {provider, query, url, notice}. 선언이 없으면 None.
    """
    for pid in sorted(providers or {}):
        spec = (providers.get(pid) or {}).get("portal_search")
        if not isinstance(spec, dict):
            continue
        base = str(spec.get("base_url") or "")
        if validate_base_url(base):
            continue
        pairs = [(str(name), str(value))
                 for name, value in (spec.get("fixed_params") or {}).items()]
        param = str(spec.get("query_param") or "")
        clean = portal_query_clean(query)
        if param and clean:
            pairs.append((param, clean))
        return {"provider": pid,
                "query": clean if param else "",
                "url": base + "?" + urllib.parse.urlencode(pairs),
                "notice": str(spec.get("notice") or "")}
    return None


def validate_user_record(entry, providers):
    """사용자 등록 레코드의 구조 검사(설계 docs/8 4-3).

    `base_url` 검사에 더해 `provider` 열거형을 본다. 사용자가 임의 제공자
    이름을 만들면 **키를 넣을 자리가 없는 제공자**가 목록에 생긴다 - 제공자
    정의는 동봉 파일만 한다(설계 docs/8 4-1).

    Args:
        entry: 해석된 레코드 dict.
        providers: 병합된 providers dict.

    Returns:
        str: 거절 사유. 통과면 빈 문자열이다.
    """
    why = validate_base_url(entry.get("base_url"))
    if why:
        return why
    pid = str(entry.get("provider") or "")
    if not pid:
        return "provider is empty"
    if pid not in (providers or {}):
        return "unknown provider %r (not declared in a shipped catalog)" % pid
    resp = entry.get("response") or {}
    kind = str(resp.get("kind") or "")
    if kind not in RESPONSE_KINDS:
        return "unknown response.kind %r" % kind
    mode = paging_mode(entry)
    if mode not in PAGING_MODES:
        return "unknown paging mode %r" % mode
    return ""


def paging_spec(entry):
    """`paging` 선언을 dict 로 정규화한다.

    구 레지스트리 항목은 `paging` 이 문자열("none" / "tile_subdivide")이고
    S9e-3 의 등록 레코드는 dict 다. 두 모양을 한 자리에서 접는다 - 호출부가
    isinstance 를 되풀이하면 분기가 흩어진다.

    Returns:
        dict: 적어도 `mode` 키를 갖는 dict.
    """
    spec = entry.get("paging")
    if isinstance(spec, dict):
        out = dict(spec)
        out["mode"] = str(out.get("mode") or "none")
        return out
    return {"mode": str(spec or "none")}


def paging_mode(entry):
    """정규화된 페이징 방식 문자열."""
    return paging_spec(entry)["mode"]


def resolve_template(providers, entry):
    """항목이 참조한 제공자 템플릿을 물려준다(설계 docs/8 4-2).

    공통 호출 파라미터를 항목마다 반복하지 않는다. 항목의 값이 템플릿을
    **덮고**, dict 필드는 키 단위로 합친다 - 항목이 params 한 칸을 더하려고
    템플릿 전체를 다시 적게 하지 않기 위함이다.

    Args:
        providers: 병합된 providers dict.
        entry: 카탈로그 항목 dict.

    Returns:
        dict: 템플릿이 적용된 새 dict. 참조가 없으면 사본 그대로.
    """
    name = str(entry.get("template") or "")
    if not name:
        return dict(entry)
    meta = providers.get(str(entry.get("provider") or "")) or {}
    template = ((meta.get("templates") or {}).get(name)) or {}
    out = dict(template)
    for key, value in entry.items():
        if (key in TEMPLATE_DICT_FIELDS and isinstance(value, dict)
                and isinstance(out.get(key), dict)):
            merged = dict(out[key])
            merged.update(value)
            out[key] = merged
        else:
            out[key] = value
    return out


def flatten_snapshot_entry(entry, file_provider):
    """스냅샷 항목(`source`/`local` 2블록)을 평면 필드로 투영한다.

    왜 두 모양을 다 받는가: 스냅샷은 전사 필드(`source`)와 우리 필드(`local`)를
    **구조로** 갈라야 "발명 금지" 가 원문 축자 대조로 검사된다(설계 docs/8
    4-2). 반면 서버 내부는 `title`·`typename`·`verified` 같은 평면 필드를
    읽는다. 그래서 적재 시점에 한 번 투영하고 원 블록은 근거로 남긴다 -
    투영을 하지 않으면 158행이 제목도 typename 도 없는 항목으로 들어온다.

    항목에 평면 필드가 이미 있으면 그쪽이 이긴다(스냅샷 한 줄을 손으로
    덮어쓰는 길을 막지 않는다). `provider` 는 파일 전체 기본값을 쓸 수 있다 -
    158행마다 되풀이하지 않기 위함이다.

    Args:
        entry: 카탈로그 항목 dict.
        file_provider: 파일 최상위 `provider` 값(없으면 빈 값).

    Returns:
        dict: 평면 필드가 채워진 새 dict. 2블록 항목이 아니면 사본 그대로.
    """
    source = entry.get("source")
    local = entry.get("local")
    if not isinstance(source, dict) and not isinstance(local, dict):
        return dict(entry)
    source = source if isinstance(source, dict) else {}
    local = local if isinstance(local, dict) else {}
    out = dict(entry)
    if not out.get("provider") and file_provider:
        out["provider"] = str(file_provider)
    # 템플릿 이름은 호출 계열과 같은 축이다(`wfs` | `data`).
    if not out.get("template") and local.get("request_family"):
        out["template"] = str(local["request_family"])
    if not out.get("title") and source.get("title_ko"):
        out["title"] = source["title_ko"]
    if not out.get("geometry") and source.get("geometry"):
        out["geometry"] = source["geometry"]
    if not out.get("typename") and local.get("typename"):
        out["typename"] = local["typename"]
    for name in ("verified", "supported"):
        if name not in out and name in local:
            out[name] = local[name]
    if not out.get("notes") and local.get("notes"):
        out["notes"] = local["notes"]
    return out


def notes_head(text, cap=NOTES_HEAD_MAX):
    """카탈로그 `notes` 의 **머리 1문장**을 자른다.

    목록 행에 미지원 사유를 실으려면 전문이 너무 길다(2-5 의 압축 취지).
    마침표 뒤 공백을 문장 경계로 보고 첫 문장만 쓰고, 그래도 상한을 넘으면
    상한에서 끊는다. **문장을 다시 쓰지 않는다** - 카탈로그 원문을 자르는
    것이고, 전문은 `describe_dataset` 의 `notes` 가 그대로 돌려준다.

    Args:
        text: 원문 notes.
        cap: 길이 상한(문자 수).

    Returns:
        str: 머리 1문장. 원문이 비면 빈 문자열.
    """
    body = " ".join(str(text or "").split())
    if not body:
        return ""
    # 마침표 + 공백만 경계로 본다. 마지막 마침표는 문장 끝이라 경계가 아니다.
    cut = body.find(". ")
    if cut != -1:
        body = body[:cut + 1]
    if len(body) > cap:
        body = body[:cap]
    return body


def load_catalog(paths):
    """카탈로그 5파일을 병합한다(설계 docs/8 4-1).

    규칙 넷. (1) 적재 순서는 동봉 -> 사용자다. (2) **id 충돌은 거절**한다 -
    조용한 덮어쓰기는 목록과 실제 요청지가 갈리게 만든다. 먼저 적재된 파일이
    이기므로 레지스트리 8종이 스냅샷의 같은 id 보다 선순위다. (3) 사용자
    레코드는 `user.` 접두를 강제하고 동봉 레코드는 그 접두를 쓰지 못한다.
    (4) **같은 제공자에서 typename 이 겹치면 뒤에 온 쪽을 거절**한다 -
    스냅샷 158행과 레지스트리 8종은 같은 WFS 레이어를 겹쳐 가리킨다(목록 ID 가
    `_INFO` 접미라 id 는 다른데 측정 typename 은 같은 경계 항목이 있다).
    스냅샷 파일 자체는 158 전행을 보존해야 하므로(원문 축자 대조 불변식)
    중복 제거는 적재 시점에 한다. 거절 id 는 근거 문자열에 남는다.

    경로 템플릿(`{}`)이 든 `base_url` 은 **모든 레코드에서** 거절한다 -
    엔드포인트 집합을 넓히는 입구를 사용자 UI 하나로 묶는 불변식 I-2 의
    일부다(설계 docs/8 1). 사용자 레코드는 그 위에 `https://` 강제, 쿼리
    문자열 금지, `provider` 열거형, 봉투·페이징 선언 검사를 더 받는다
    (설계 docs/8 4-3, `validate_user_record`) - 파라미터는
    `fixed_params`/`params` 로만 들어온다.

    Args:
        paths: catalog_paths() 가 돌려준 경로들. 마지막 항목이 사용자 파일이다.

    Returns:
        tuple: (providers dict, id -> 해석된 항목 dict, 근거 문자열)
    """
    providers = {}
    datasets = {}
    notes = []
    rejected = []
    # (제공자, typename) -> 먼저 등재한 id. 중복 거절의 근거를 같이 남긴다.
    seen_typenames = {}
    user_path = paths[-1] if len(paths) > len(CATALOG_SIBLINGS) + 1 else ""
    for path in paths:
        body, why = read_catalog_file(path)
        is_user = bool(user_path) and path == user_path
        if body is None:
            notes.append("%s=%s" % (os.path.basename(path), why))
            continue
        file_provider = str(body.get("provider") or "") if not is_user else ""
        # providers 는 **동봉 파일만** 정의한다. 사용자 파일이 제공자를 만들면
        # 키를 넣을 자리 없는 제공자가 목록에 생긴다(설계 docs/8 4-3).
        if not is_user:
            for pid, meta in (body.get("providers") or {}).items():
                if isinstance(meta, dict):
                    providers.setdefault(str(pid), meta)
        rows = body.get("datasets") if not is_user else (
            body.get("records") or body.get("datasets"))
        n_before = len(datasets)
        for entry in rows or ():
            if not isinstance(entry, dict) or not entry.get("id"):
                rejected.append("%s:no id" % os.path.basename(path))
                continue
            entry = flatten_snapshot_entry(entry, file_provider)
            ds_id = str(entry["id"])
            has_prefix = ds_id.startswith(USER_ID_PREFIX)
            if is_user and not has_prefix:
                rejected.append("%s:needs %s prefix" % (ds_id, USER_ID_PREFIX))
                continue
            if not is_user and has_prefix:
                rejected.append("%s:%s prefix is reserved"
                                % (ds_id, USER_ID_PREFIX))
                continue
            if ds_id in datasets:
                rejected.append("%s:id collision" % ds_id)
                continue
            resolved = resolve_template(providers, entry)
            # 구조 검증(설계 docs/8 4-3). **범위는 사용자 레코드다** - 설계가
            # 요구한 `https://` 강제·쿼리 문자열 금지·`provider` 열거형은
            # 등록 레코드 검증이고, 동봉 레코드에는 경로 템플릿 금지만 건다
            # (불변식 I-2). 동봉에까지 `https://` 를 강제하면 하네스의 루프백
            # 픽스처(http://127.0.0.1)가 카탈로그에서 거절돼 검증 경로가
            # 닫힌다 - 2026-10-17 에 실제로 밟았다. 거절은 조용하지 않다 -
            # 사유가 근거 문자열에 남는다.
            why_struct = (validate_user_record(resolved, providers) if is_user
                          else ("path template"
                                if ("{" in str(resolved.get("base_url") or "")
                                    or "}" in str(resolved.get("base_url")
                                                  or "")) else ""))
            if why_struct:
                rejected.append("%s:%s" % (ds_id, why_struct))
                continue
            # 같은 레이어를 두 id 로 등재하면 목록에 같은 데이터가 두 줄로
            # 보이고 어느 쪽을 쓸지 모델이 고르게 된다. 먼저 온 쪽을 남긴다.
            tname = str(resolved.get("typename") or "")
            tkey = (str(resolved.get("provider") or ""), tname)
            if tname and tkey in seen_typenames:
                rejected.append("%s:typename dup of %s"
                                % (ds_id, seen_typenames[tkey]))
                continue
            if tname:
                seen_typenames[tkey] = ds_id
            resolved["source_file"] = os.path.basename(path)
            resolved["user_record"] = bool(is_user)
            datasets[ds_id] = resolved
        notes.append("%s=%d" % (os.path.basename(path),
                                len(datasets) - n_before))
    why = "catalog n=%d providers=%d (%s)" % (
        len(datasets), len(providers), " ".join(notes))
    if rejected:
        # 건수를 앞에 붙인다. 목록은 10건에서 끊기므로 건수 없이는 "몇 줄이
        # 빠졌는가" 를 근거 문자열에서 셀 수 없다.
        why += " rejected=%d:%s" % (len(rejected), ",".join(rejected[:10]))
    return providers, datasets, why


# -------------------------------------------------------------------- 유틸
def secret_variants(value):
    """비밀 하나에서 **치환해야 할 변형 전체**를 만든다(설계 docs/8 2-2).

    저장값과 URL 안의 문자열이 같은 것은 지금 `KEY_RE` 가 영숫자뿐이기 때문
    이지 마스킹 로직이 옳아서가 아니다. base64 계열 키(`+` `/` `=`)를 받는
    순간 URL 에는 `%2B...` 가 들어가고 저장값과의 완전 일치가 0건이 된다.
    그래서 변형을 미리 넓힌다.

    Args:
        value: 비밀 원문.

    Returns:
        tuple: 길이 내림차순 변형들. 12자 미만 변형은 제외한다(설계 docs/2 5-4
            안전장치 - 짧은 값을 치환하면 본문이 잠식된다).
    """
    raw = "" if value is None else str(value)
    if not raw:
        return ()
    cands = [raw, urllib.parse.quote(raw, safe=""), urllib.parse.quote_plus(raw)]
    plain = urllib.parse.unquote(raw)
    if plain != raw:
        cands.append(plain)
    kept = []
    for text in cands:
        if len(text) >= REDACT_MIN_LEN and text not in kept:
            kept.append(text)
    kept.sort(key=len, reverse=True)
    return tuple(kept)


def mask(text, secrets=()):
    """문자열에서 비밀 집합 전체를 마스킹한다(설계 docs/2 5-4, docs/8 2-2).

    정규식으로 "키처럼 보이는 것" 을 찾지 않는다 - 오탐이 본문을 깨뜨린다.
    비밀 집합과 **완전 일치하는 부분문자열**만 바꾸고, 긴 것부터 치환한다
    (한 값이 다른 값의 부분문자열일 때 짧은 쪽을 먼저 치환하면 긴 쪽이 토큰에
    섞여 남는다).

    Args:
        text: 임의 문자열.
        secrets: 비밀 문자열 하나 또는 iterable.

    Returns:
        str: 치환된 문자열.
    """
    body = str(text or "")
    for secret in _secret_list(secrets):
        body = body.replace(secret, REDACT_TOKEN)
    return body


def mask_bytes(body, secrets=()):
    """응답 **바이트**에서 비밀 집합을 치환한다(설계 docs/8 10 첫 항목).

    V-World WFS GetCapabilities 는 요청 URL 을 OnlineResource href 로 그대로
    되돌렸다(2026-10-16 실측, 응답 안에 키가 5회). 그래서 원본 페이지를 쓰기
    **전에** 이 함수를 지난다. 바이트에서 치환하므로 디코딩 가능 여부와 무관
    하고, 비밀이 없으면 응답은 바이트 단위로 그대로 남는다.

    Args:
        body: 응답 바이트.
        secrets: 비밀 문자열 하나 또는 iterable.

    Returns:
        tuple: (치환된 바이트, 치환 건수)
    """
    data = body if isinstance(body, bytes) else bytes(body or b"")
    hits = 0
    token = REDACT_TOKEN.encode("utf-8")
    for secret in _secret_list(secrets):
        needle = secret.encode("utf-8", "ignore")
        if needle and needle in data:
            hits += data.count(needle)
            data = data.replace(needle, token)
    return data, hits


def _secret_list(secrets):
    """비밀 인자를 길이 내림차순 리스트로 정규화한다.

    문자열 하나도 받는다 - 호출부가 집합을 들고 있지 않은 자리(유닛 측정)를
    위해 남긴 입구다.
    """
    if secrets is None:
        return []
    if isinstance(secrets, str):
        items = [secrets]
    else:
        items = [str(s) for s in secrets if s]
    kept = sorted({s for s in items if len(s) >= REDACT_MIN_LEN},
                  key=len, reverse=True)
    return kept


def parse_bbox(value):
    """bbox 인자를 (minx, miny, maxx, maxy) 로 정규화한다.

    Args:
        value: 길이 4 리스트, 또는 쉼표로 이은 문자열.

    Returns:
        tuple: 실수 4개.

    Raises:
        ValueError: 개수나 형식이 맞지 않거나 최소/최대가 뒤집혔을 때.
    """
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [p for p in str(value or "").replace(" ", "").split(",") if p]
    if len(items) != 4:
        raise ValueError("bbox needs 4 numbers (minx,miny,maxx,maxy)")
    nums = [float(x) for x in items]
    if nums[0] >= nums[2] or nums[1] >= nums[3]:
        raise ValueError("bbox min must be smaller than max")
    return tuple(nums)


def inside(root, path):
    """path 가 root 아래인가. 경로 탈출을 막는 접두 검사다.

    서버가 경로를 정하므로 모델이 깨뜨릴 입구는 없지만, 레지스트리 id 가
    경로 조각으로 쓰이므로 한 겹 더 본다.
    """
    root_abs = os.path.normcase(os.path.abspath(str(root)))
    path_abs = os.path.normcase(os.path.abspath(str(path)))
    return path_abs == root_abs or path_abs.startswith(root_abs + os.sep)


def safe_slug(text):
    """경로 조각으로 쓸 수 있게 영숫자와 하이픈만 남긴다."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(text or "x"))[:64] or "x"


def write_atomic(path, payload):
    """`.part` 로 쓰고 rename 한다(설계 docs/2 4-3 원자성).

    수집 중 트리 kill 이 들어오면 반쪽 파일이 남는데, 그것을 완성본으로
    오인하면 다음 단계가 조용히 틀린다. 그래서 완료 시점에만 최종 이름이 된다.

    Args:
        path: 최종 파일 경로.
        payload: 쓸 바이트.

    Returns:
        int: 쓴 바이트 수.
    """
    tmp = path + ".part"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    if os.path.exists(path):
        os.remove(path)
    os.replace(tmp, path)
    return len(payload)


# ------------------------------------------------------------- 응답 봉투 선언
def dig(payload, dotted):
    """점 경로로 JSON 안을 한 단계씩 들어간다(설계 docs/8 3-1).

    와일드카드도 슬라이스도 받지 않는다 - 경로 파서를 만들지 않기 위해
    `split(".")` 로 끝낸다. 선언에 그 밖의 표기가 있으면 경로 부재로 끝나고,
    부재는 **성공이 아니다**(2-4).

    Args:
        payload: 파싱된 JSON.
        dotted: `features` 또는 `body.items` 같은 점 경로. 빈 값이면 payload.

    Returns:
        tuple: (찾았는가, 값)
    """
    node = payload
    for part in [p for p in str(dotted or "").split(".") if p]:
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def top_key_names(node):
    """진단용 최상위 **키 이름** 목록. 값은 담지 않는다(설계 docs/8 2-4)."""
    if isinstance(node, dict):
        return [str(k) for k in list(node)[:TOP_KEYS_MAX]]
    if isinstance(node, list):
        return ["<list len=%d>" % len(node)]
    return ["<%s>" % type(node).__name__]


def xml_records(root, items_path):
    """XML 레코드 목록을 dict 리스트로 바꾼다.

    `xml.etree.ElementTree` 로 읽는다(stdlib). **제한을 명시한다** -
    ElementTree 는 entity 확장 계열(billion laughs 등)에 취약하고,
    `defusedxml` 은 표준 라이브러리가 아니라 `-I` 단일 파일 제약 아래 쓸 수
    없다. 완화는 **기존 바이트 상한과 페이지 상한뿐이며 가드가 아니다**
    (설계 docs/8 3-1, 10).

    Args:
        root: ElementTree 루트 엘리먼트.
        items_path: `.//item` 같은 ElementTree 경로.

    Returns:
        list[dict]: 자식 태그 이름 -> 텍스트.
    """
    out = []
    for node in root.findall(items_path):
        row = {}
        for child in node:
            row[str(child.tag)] = (child.text or "").strip()
        if not row:
            row = {str(node.tag): (node.text or "").strip()}
        out.append(row)
    return out


def read_total(entry, node, is_xml):
    """선언된 `paging.total_path` 로 전체 건수를 읽는다(설계 docs/8 3-1).

    `page_no` 페이징은 **총건수로 끝을 알고, 못 읽으면 빈 페이지로 끝낸다.**
    그래서 이 함수는 못 읽는 것을 오류로 올리지 않고 None 을 돌려준다 -
    두 종료 조건 중 하나가 빠진 것일 뿐이다(강의 러너도 두 조건을 다 쓴다).

    Args:
        entry: 해석된 카탈로그 항목.
        node: JSON 이면 파싱된 payload, XML 이면 ElementTree 루트.
        is_xml: XML 인가.

    Returns:
        int 또는 None. 선언이 없거나 숫자로 못 읽으면 None.
    """
    path = str(paging_spec(entry).get("total_path") or "")
    if not path:
        return None
    if is_xml:
        try:
            found = node.find(path)
        except SyntaxError:
            return None
        raw = (found.text or "").strip() if found is not None else ""
    else:
        seen, value = dig(node, path)
        raw = str(value or "") if seen else ""
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def parse_response(entry, body, page_name=""):
    """선언된 봉투로 응답을 읽는다(설계 docs/8 2-4, 3-1).

    "HTTP 200 은 성공이 아니다" 가 제공자 3사 중 2사에서 참이다 - 오류 채널은
    본문 안에 있다. 그래서 선언된 오류 코드를 먼저 보고, 그 다음 레코드 경로를
    본다. **경로가 없으면 0건 성공이 아니라 구조화 오류**다.

    Args:
        entry: 해석된 카탈로그 항목.
        body: 응답 바이트(이미 마스킹을 지난 것).
        page_name: 오류 문구에 적을 페이지 파일 이름.

    Returns:
        dict: {"kind", "items", "error", "top_keys"} 와, 성공 회차에만
            {"total"}. items 는 kind=geojson 이면 Feature 목록, 그 밖이면
            레코드 목록이다. error 가 비어 있지 않으면 그 회차는 실패다.
            total 은 `paging.total_path` 선언이 있고 숫자로 읽혔을 때만
            정수이고, 그 밖에는 None 이다(페이징이 빈 페이지로 끝낸다).
    """
    resp = entry.get("response") or {}
    kind = str(resp.get("kind") or "")
    if kind not in RESPONSE_KINDS:
        return {"kind": kind, "items": [], "top_keys": [],
                "error": "응답 봉투 선언(response.kind)이 없거나 모르는 값입니다: %r"
                         % (kind,)}
    where = " (%s)" % page_name if page_name else ""
    if kind == "xml_records":
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            return {"kind": kind, "items": [], "top_keys": [],
                    "error": "응답이 XML 이 아닙니다%s: %s" % (where, exc)}
        err = resp.get("error") or {}
        code_path = str(err.get("code_path") or "")
        if code_path:
            node = root.find(code_path)
            code = (node.text or "").strip() if node is not None else ""
            ok_values = [str(v) for v in (err.get("ok") or ())]
            if code and ok_values and code not in ok_values:
                msg_node = root.find(str(err.get("msg_path") or "")) \
                    if err.get("msg_path") else None
                msg = (msg_node.text or "").strip() if msg_node is not None else ""
                return {"kind": kind, "items": [], "top_keys": [],
                        "error": "제공자가 오류를 돌려줬습니다 (%s=%s) %s"
                                 % (code_path, code, msg)}
        items_path = str(resp.get("items_path") or "")
        found = root.findall(items_path) if items_path else []
        # XML 은 "경로 부재" 와 "레코드 0건" 이 같은 빈 findall 로 온다. 그래서
        # **오류 채널이 성공을 말했을 때만** 0건을 성공으로 받는다. 채널 선언이
        # 없으면 둘을 가를 근거가 없으므로 큰 소리로 실패한다(설계 docs/8 2-4).
        if not found and not (items_path and code_path):
            return {"kind": kind, "items": [], "top_keys":
                    [str(root.tag)] + [str(c.tag) for c in list(root)[:TOP_KEYS_MAX]],
                    "error": "선언된 레코드 경로 %r 를 응답에서 찾지 못했습니다%s"
                             % (items_path, where)}
        return {"kind": kind, "items": xml_records(root, items_path),
                "top_keys": [], "error": "",
                "total": read_total(entry, root, True)}

    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return {"kind": kind, "items": [], "top_keys": [],
                "error": "응답이 JSON 이 아닙니다%s" % where}
    err = resp.get("error") or {}
    if err.get("code_path"):
        seen, code = dig(payload, err["code_path"])
        ok_values = [str(v) for v in (err.get("ok") or ())]
        if seen and ok_values and str(code) not in ok_values:
            msg = ""
            if err.get("msg_path"):
                _seen, msg_value = dig(payload, err["msg_path"])
                msg = str(msg_value or "")
            return {"kind": kind, "items": [], "top_keys": [],
                    "error": "제공자가 오류를 돌려줬습니다 (%s=%s) %s"
                             % (err["code_path"], code, msg)}
    items_path = str(resp.get("items_path") or "")
    seen, value = dig(payload, items_path)
    if not seen:
        return {"kind": kind, "items": [], "top_keys": top_key_names(payload),
                "error": "선언된 레코드 경로 %r 가 응답에 없습니다%s"
                         % (items_path, where)}
    if not isinstance(value, list):
        # 한 단계 더 들어가야 하는 봉투(`body.items.item` 계열)를 추측하지 않고,
        # 사용자가 선언을 고칠 수 있게 그 자리의 키 이름만 돌려준다(U11).
        return {"kind": kind, "items": [], "top_keys": top_key_names(value),
                "error": "선언된 레코드 경로 %r 가 목록이 아닙니다%s"
                         % (items_path, where)}
    rows = [row for row in value if isinstance(row, dict)]
    return {"kind": kind, "items": rows, "top_keys": [], "error": "",
            "total": read_total(entry, payload, False)}


def validate_args(entry, args):
    """`args` 맵을 레지스트리 `params` 화이트리스트로 검증한다.

    설계 docs/8 3-2 안 A 의 안전성 논거가 이 함수에 모여 있다. (1) 키는 args
    에 못 들어간다(서버가 설정에서 읽어 자기가 붙인다), (2) 알 수 없는
    파라미터 이름은 **거절**한다(교집합이 아니라 부분집합 검사), (3) 값은
    타입·enum 으로 검증하고 전부 urlencode 를 거친다.

    Args:
        entry: 해석된 카탈로그 항목.
        args: 모델이 넘긴 맵. None 이면 빈 맵.

    Returns:
        dict: 질의 파라미터 이름 -> 문자열 값.

    Raises:
        ToolError: 미등재 이름, 타입·enum 위반, 금지 문자, 필수 누락.
    """
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise ToolError("args 는 이름-값 맵이어야 합니다")
    specs = entry.get("params") or {}
    out = {}
    for name, value in args.items():
        key = str(name)
        if key in ARGS_RESERVED:
            raise ToolError("%s 는 args 가 아니라 전용 인자로 넘기세요" % key)
        if key not in specs:
            raise ToolError("이 데이터셋이 받지 않는 인자입니다: %s (describe_dataset "
                            "의 params 에 있는 이름만 받습니다)" % key)
        spec = specs[key]
        # 구 레지스트리는 params 값이 설명 문자열이다. 그때는 타입 선언이 없는
        # 것으로 보고 문자열로 받는다(하위 호환).
        kind = str((spec or {}).get("type") if isinstance(spec, dict) else "str")
        text = "" if value is None else str(value)
        if any(ch in text for ch in ARGS_FORBIDDEN_CHARS):
            raise ToolError("%s 값에 개행이나 제어문자가 있습니다" % key)
        if kind == "int":
            try:
                text = str(int(text))
            except (TypeError, ValueError):
                raise ToolError("%s 는 정수여야 합니다" % key)
        elif kind == "enum":
            allowed = [str(v) for v in ((spec or {}).get("enum") or ())]
            if text not in allowed:
                raise ToolError("%s 가 받는 값은 %s 입니다"
                                % (key, ", ".join(allowed) or "(선언 없음)"))
        elif kind == "bbox":
            try:
                text = "%.8f,%.8f,%.8f,%.8f" % parse_bbox(text)
            except ValueError as exc:
                raise ToolError("%s 형식 오류: %s" % (key, exc))
        out[key] = text
    for name in entry.get("required") or ():
        key = str(name)
        if key in ARGS_RESERVED or key not in specs:
            continue
        if key not in out:
            raise ToolError("이 데이터셋은 args 에 %s 가 필수입니다" % key)
    return out


# --------------------------------------------------------------------- HTTP
def http_get(url, timeout=HTTP_TIMEOUT_S):
    """GET 1회. 응답 바이트를 그대로 돌려준다.

    `urllib` 기본 핸들러가 `HTTP_PROXY`/`HTTPS_PROXY` 를 존중한다(기관망
    대응, 설계 docs/2 4-5). 실패는 원문을 그대로 올린다 - 추정 진단을 쓰지
    않는다.

    Args:
        url: 전체 URL(키 포함. 호출자가 로그에 넣을 때 마스킹한다).
        timeout: 초.

    Returns:
        tuple: (상태 코드, 응답 바이트, content-type)

    Raises:
        urllib.error.URLError: 연결 자체가 실패했을 때.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "upwise-chat-collect/0.2.0"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.getcode(), resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "") if exc.headers else ""


def http_get_retry(url, log, masker):
    """재시도를 포함한 GET(설계 docs/2 4-5).

    429/5xx 는 지수 백오프 3회. 401/403 은 재시도하지 않고 분류해 올린다.

    Args:
        url: 전체 URL(비밀 포함).
        log: ServerLog.
        masker: 문자열 하나를 받아 비밀을 지운 문자열을 돌려주는 콜러블
            (`Collector.mask`). 호출부가 비밀 **값**을 넘기지 않는다
            (설계 docs/8 2-3).

    Returns:
        tuple: (상태 코드 또는 0, 바이트, 사유 문자열)
    """
    last = ""
    for attempt in range(RETRY_MAX):
        try:
            code, body, _ctype = http_get(url)
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as exc:
            last = "transport: %r" % (exc,)
            log.write("http_error", "%s %s" % (masker(url), masker(last)))
            if attempt + 1 >= RETRY_MAX:
                return 0, b"", last
            time.sleep(RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)])
            continue
        log.write("http", "code=%s bytes=%d url=%s"
                  % (code, len(body), masker(url)))
        if code in (401, 403):
            return code, body, "키가 거부됐습니다(HTTP %d)" % code
        if code in RETRY_STATUS and attempt + 1 < RETRY_MAX:
            last = "HTTP %d" % code
            time.sleep(RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)])
            continue
        if code != 200:
            return code, body, "HTTP %d" % code
        return code, body, ""
    return 0, b"", last or "retries exhausted"


# ------------------------------------------------------------------ 수집 본체
class Collector:
    """수집 1회를 수행하고 요약을 계산한다.

    요약 수치를 서버가 계산하는 것이 요점이다(설계 docs/2 4-6). 모델이 세면
    전사의 숫자에 재현 경로가 없다.
    """

    def __init__(self, env, log):
        """환경 계약을 읽고 레지스트리를 적재한다.

        Args:
            env: os.environ 과 같은 매핑.
            log: ServerLog.
        """
        self.log = log
        self.ini_path = env.get(ENV_SETTINGS_INI, "")
        self.key_prefix = env.get(ENV_KEY_PREFIX, "upwise_chat/keys/")
        self.workspace = env.get(ENV_WORKSPACE, "") or os.getcwd()
        self.root = os.path.join(self.workspace, COLLECTED_SUBDIR)
        # 런타임 비밀 레지스터(설계 docs/8 2-3 I-1). 저장 키와 그 인코딩 변형,
        # 그리고 앞으로 발급될 토큰이 **같은 집합**에 들어간다. 마스킹은 호출부가
        # 넘긴 값 하나가 아니라 이 집합 전체를 대상으로 한다.
        self._secrets = set()
        # 제공자별 accessToken. **메모리에만 산다**(설계 docs/8 2-3) - 디스크,
        # 도구 결과, collect_meta.json 어디에도 쓰지 않는다. 서버가 죽으면
        # 같이 사라지고 다음 기동이 다시 발급받는다.
        self._tokens = {}
        self.catalog_files = catalog_paths(env.get(ENV_REGISTRY, ""),
                                           self.ini_path)
        self._catalog_sig = ()
        self.providers = {}
        self.registry = {}
        self.registry_why = ""
        self.reload_catalog()
        self.csv_log = CollectCsvLog(self.root)
        self.calls = 0
        # 엔드포인트 오버라이드는 **설정에서만** 온다. 모델 인자로 받지 않는다.
        # 하네스가 로컬 http 서버로 전 경로를 재게 하는 유일한 입구다.
        self.endpoint_override, self.override_why = read_setting(
            self.ini_path, SETTING_ENDPOINT_OVERRIDE)
        self.log.write("init", "registry=%s workspace=%s override=%s(%s)"
                       % (self.registry_why, self.workspace,
                          bool(self.endpoint_override), self.override_why))

    # ------------------------------------------------------------------
    # 비밀 레지스터
    # ------------------------------------------------------------------

    def note_secret(self, value):
        """비밀 하나와 그 변형을 레지스터에 등록한다(설계 docs/8 2-3 I-1).

        **등록 진입점은 이 함수 하나다.** 지금 부르는 쪽은 `read_key()` 지만,
        SGIS `accessToken` 같은 파생 비밀도 발급 직후 같은 자리를 지나야 한다
        (토큰 발급 자체는 S9e-2 범위다 - 여기서는 구조만 세운다). 토큰은
        메모리에만 두고 디스크·도구 결과·사이드카에 넣지 않는다.

        Args:
            value: 비밀 원문.

        Returns:
            int: 레지스터에 든 변형의 수(이 호출로 더해진 것 포함).
        """
        for text in secret_variants(value):
            self._secrets.add(text)
        return len(self._secrets)

    def secrets(self):
        """마스킹 대상 비밀 집합. 길이 내림차순이다. **로그에 적지 않는다.**"""
        return tuple(_secret_list(self._secrets))

    def mask(self, text):
        """레지스터 전체로 문자열을 마스킹한다. 호출부는 비밀을 넘기지 않는다."""
        return mask(text, self._secrets)

    def mask_response(self, body):
        """응답 바이트를 레지스터 전체로 마스킹한다(설계 docs/8 10 첫 항목).

        Returns:
            tuple: (치환된 바이트, 치환 건수)
        """
        return mask_bytes(body, self._secrets)

    # ------------------------------------------------------------------
    # 카탈로그
    # ------------------------------------------------------------------

    def reload_catalog(self):
        """카탈로그 4파일을 다시 병합한다. 지문도 갱신한다."""
        self._catalog_sig = catalog_signature(self.catalog_files)
        self.providers, self.registry, self.registry_why = load_catalog(
            self.catalog_files)
        return self.registry_why

    def ensure_catalog(self):
        """호출마다 지문을 보고 바뀌었으면 재적재한다(설계 docs/8 4-1).

        사용자가 등록 UI 로 파일을 고친 직후 수집하려면 핫리로드가 유일한
        경로다 - 서버는 CLI 가 띄우므로 플러그인이 단독으로 재시작할 수 없다.
        """
        if catalog_signature(self.catalog_files) != self._catalog_sig:
            why = self.reload_catalog()
            self.log.write("catalog_reload", why)
        return self.registry

    # ------------------------------------------------------------------
    # 조회 도구
    # ------------------------------------------------------------------

    def list_datasets(self, provider=None, query=None, limit=None, offset=None):
        """노출 데이터셋 목록. 압축형이고 질의로 좁힌다(설계 docs/8 2-5).

        158 종이 되면 전량 반환이 호출마다 수십 KB 를 모델 컨텍스트로 밀어
        넣는다. 그래서 행마다 6필드로 줄이고 `total`·`truncated` 를 같이 준다.
        상세는 `describe_dataset` 이 맡는다.

        행에 `supported` 가 있는 이유(2026-10-17 실기 결함)
            미지원 항목은 **목록에서 빼지 않는다**(설계 docs/8 3-3 D4 - 숨기면
            "못 받는다" 를 사용자가 모른다). 그런데 압축형이 5필드였을 때는
            모델이 목록 단계에서 지원 여부를 구별할 수단이 없었고, 실제로
            `vworld.lt_c_bldginfo`(supported=false)를 "자주 쓰는 후보" 로
            사용자에게 권했다. 후보는 목록 단계에서 정해지므로 구별 수단은
            여기 있어야 한다 - `describe_dataset` 에 있는 것으로는 늦다.
            미지원 행에만 `unsupported_why`(사유 머리 1문장)를 덧붙인다.
            지원 행에는 그 칸을 만들지 않는다 - 30행 전부에 빈 칸을 실으면
            압축형의 바이트 예산을 사유 없이 먹는다.

        `providers` 가 **제공자 선언 기준**인 이유(2026-10-17 실기 결함)
            전에는 조회 결과에서 유도해서(`{r["provider"] for r in hits}`)
            데이터셋이 0건인 제공자가 사라졌다. data.go.kr 은 공식 카탈로그
            API 가 없어 동봉 데이터셋이 0건이고 사용자 등록으로만 생기는데
            (설계 docs/8 3-5), 그래서 **사용자가 키를 저장해 두고도** 모델이
            "두 제공처(sgis, vworld) 모두 키가 설정되어 있습니다" 라고 보고했다.
            지금은 동봉 선언에 있는 제공자를 전부 싣고 제공자마다
            `key_configured` 와 데이터셋 수를 같이 준다 - 모델이 "키는 있는데
            등록된 데이터셋이 0건" 을 말할 수 있다. 이 집계는 **질의·제공자
            인자와 무관**하다(카탈로그 전량 기준) - 제공자 재고는 조회 결과에
            따라 달라지는 값이 아니다.

        `portal_search` 가 0건일 때만 붙는 이유 (조사 docs/3 4차 측정 (c))
            data.go.kr 은 공식 카탈로그 API 가 없고 목록 페이지는 robots.txt
            Disallow 경로다. 그래서 전수 스냅샷((a))을 기각하고 **포털 검색
            링크 생성**((c))으로 탐색을 세운다. 0건이 "플러그인 카탈로그에
            없다" 이므로 그 자리에서만 링크를 돌려준다 - 후보가 있는 호출에
            안내를 실으면 압축형의 바이트 상한을 문구로 먹는다. 서버는 이
            주소를 **조회하지 않는다**.

        Args:
            provider: 제공자 id 로 좁힌다. 비우면 전체.
            query: id 또는 제목 부분일치(대소문자 무시). 0건이면 같은 값이
                포털 검색 링크의 검색어가 된다.
            limit: 반환 상한. 기본 30, 최대 100.
            offset: 건너뛸 개수.

        Returns:
            dict: 도구 결과 본문.
        """
        self.ensure_catalog()
        want_provider = str(provider or "").strip().lower()
        needle = str(query or "").strip().lower()
        try:
            take = int(limit) if limit else LIST_LIMIT_DEFAULT
        except (TypeError, ValueError):
            raise ToolError("limit 은 정수여야 합니다")
        take = max(1, min(take, LIST_LIMIT_MAX))
        try:
            skip = max(0, int(offset) if offset else 0)
        except (TypeError, ValueError):
            raise ToolError("offset 은 정수여야 합니다")
        # 키 조회는 제공자당 1회만 한다 - 행마다 INI 를 다시 읽으면 158 행에서
        # 파일 파싱이 158 회가 된다.
        key_cache = {}
        # 제공자별 데이터셋 수. **필터 전** 전량으로 센다(아래 집계가 조회
        # 결과와 무관해야 한다).
        per_provider = {}
        for entry in self.registry.values():
            pid_all = str(entry.get("provider", ""))
            per_provider[pid_all] = per_provider.get(pid_all, 0) + 1
        hits = []
        for ds_id in sorted(self.registry):
            entry = self.registry[ds_id]
            pid = str(entry.get("provider", ""))
            if want_provider and pid.lower() != want_provider:
                continue
            if needle and needle not in ds_id.lower() \
                    and needle not in str(entry.get("title", "")).lower():
                continue
            if pid not in key_cache:
                if entry.get("auth") == "none":
                    key_cache[pid] = True
                else:
                    # 다필드 제공자는 required 가 전부 찼을 때만 configured 다
                    # (설계 docs/8 5-1). 반쪽 입력을 true 로 세면 모델이
                    # 거부당할 데이터셋을 사용자에게 권한다.
                    fields, _why = self.read_keys(pid)
                    key_cache[pid] = bool(fields)
            supported = bool(entry.get("supported", True))
            row = {
                "id": ds_id,
                "provider": pid,
                "title": entry.get("title", ""),
                "key_configured": bool(key_cache[pid]),
                "verified": bool(entry.get("verified", False)),
                "supported": supported,
            }
            if not supported:
                # 사유는 카탈로그 원문(`local.notes`)의 머리 1문장이다. 전문은
                # describe_dataset 의 `notes` 가 돌려준다.
                row["unsupported_why"] = notes_head(entry.get("notes", ""))
            hits.append(row)
        rows = hits[skip:skip + take]
        # 제공자 재고(동봉 선언 기준). 키 상태는 **행 캐시를 재사용하지 않고**
        # 제공자 단위로 다시 읽는다 - 행 캐시에는 `auth: none` 데이터셋 때문에
        # 키 없이 true 가 된 칸이 있을 수 있고, 그것을 제공자 재고에 그대로
        # 옮기면 "키가 설정됐다" 를 거짓으로 말한다. 읽기는 제공자 수(지금 3)
        # 만큼이다.
        provider_rows = []
        for pid in sorted(self.providers):
            fields, _why = self.read_keys(pid)
            provider_rows.append({
                "id": pid,
                "key_configured": bool(fields),
                "datasets": int(per_provider.get(pid, 0)),
            })
        body = {"datasets": rows, "n": len(rows), "total": len(hits),
                "offset": skip, "limit": take,
                "truncated": (skip + len(rows)) < len(hits),
                "providers": provider_rows,
                "output_root": self.root,
                "limits": {"pages": LIMIT_PAGES, "bytes": LIMIT_BYTES,
                           "seconds": LIMIT_SECONDS,
                           "calls_per_session": LIMIT_CALLS_PER_SESSION}}
        # 조회가 0건일 때만 포털 검색 딥링크를 싣는다. 기본 호출(158건)에
        # 싣지 않는 이유 둘: 후보가 있을 때 할 안내가 아니고, 압축형의 바이트
        # 상한(하네스 23 NC1·NS2 의 8 KB)을 안내 문구로 먹는다. 0건은
        # "카탈로그에 없다" 이고, data.go.kr 은 동봉 데이터셋이 0건이라
        # `provider` 로 좁힌 호출도 여기로 떨어진다.
        if not hits:
            link = portal_search_link(self.providers, query)
            if link:
                body["portal_search"] = link
        return body

    def describe_dataset(self, dataset_id):
        """데이터셋 하나의 인자 화이트리스트와 제약.

        Returns:
            dict: 도구 결과 본문.

        Raises:
            ToolError: 모르는 id 일 때.
        """
        self.ensure_catalog()
        entry = self.registry.get(str(dataset_id or ""))
        if entry is None:
            raise ToolError("unknown dataset id: %r (use list_datasets)"
                            % (dataset_id,))
        key_fields, why = self.read_keys(entry.get("provider", ""))
        resp = entry.get("response") or {}
        kind = str(resp.get("kind") or "")
        return {
            "id": entry.get("id"),
            "provider": entry.get("provider"),
            "title": entry.get("title", ""),
            "params": entry.get("params") or {},
            "required": entry.get("required") or [],
            "paging": entry.get("paging", "none"),
            "page_limit": entry.get("page_limit"),
            "format": entry.get("format", ""),
            "default_crs": entry.get("default_crs", ""),
            "notes": entry.get("notes", ""),
            # 공간 결과인가. 비공간이면 collect 가 layer_path 를 비우고
            # table_path 를 채운다 - 모델이 적재 단계를 미리 알아야 한다.
            "response_kind": kind,
            "returns": ("layer_path" if kind == "geojson"
                        or (resp.get("lon_field") and resp.get("lat_field"))
                        else "table_path"),
            "verified": bool(entry.get("verified", False)),
            "supported": bool(entry.get("supported", True)),
            # 키 **값** 은 돌려주지 않는다. 설정됐는지와 사유만 준다.
            # 다필드 제공자의 사유에는 빠진 필드 **이름**만 들어 있다.
            "key_configured": bool(key_fields),
            "key_why": "" if key_fields else why,
        }

    # ------------------------------------------------------------------
    # 키
    # ------------------------------------------------------------------

    def read_key(self, provider):
        """제공자 키를 설정 INI 에서 읽는다. 값은 호출자 안에서만 쓴다.

        Args:
            provider: `vworld` 같은 제공자 이름.

        Returns:
            tuple: (키 또는 "", 사유 문자열)
        """
        if not provider:
            return "", "no provider"
        value, why = read_setting(self.ini_path,
                                  self.key_prefix + str(provider))
        if not value:
            return "", why
        # 형식 검사는 **제공자별**이다(설계 docs/8 3-5). 전역 식을 넓히지
        # 않으므로 V-World 는 지금 집합을 그대로 쓰고, base64 계열을 받는
        # 제공자만 자기 선언으로 넓힌다.
        pattern, form, _src = provider_key_pattern(self.providers, provider)
        okay, bad = validate_key_value(value, pattern, form)
        if not okay:
            # 추측하지 않는다. 형식을 못 읽었으면 거기서 끝낸다.
            return "", bad
        # 읽은 즉시 비밀 레지스터에 넣는다. 이 자리가 유일한 키 입구이므로
        # 등록을 여기 두면 "마스킹 대상에 안 들어간 비밀" 이 생기지 않는다.
        self.note_secret(value)
        return value, "ini"

    def read_keys(self, provider):
        """제공자 키를 **필드 맵**으로 읽는다(설계 docs/8 5-1).

        제공자마다 키가 한 칸이라는 전제가 SGIS 에서 깨진다 - 인증이
        `SGIS_SERVICE_ID` + `SGIS_SECURITY_KEY` 두 값으로 성립한다. 그래서
        제공자 선언에 `fields` 가 있으면 그 목록대로 읽고, 없으면 지금처럼
        `<접두><제공자>` 한 칸으로 읽어 V-World 경로를 그대로 둔다.

        **required 가 하나라도 비면 configured 가 아니다.** 반쪽 입력으로
        호출하면 제공자가 거부하고 사용자는 어느 칸이 비었는지 모른다. 그래서
        사유에 **빠진 필드 이름**을 적는다 - 값은 어느 경로로도 적지 않는다.

        Args:
            provider: `sgis` 같은 제공자 이름.

        Returns:
            tuple: ({필드명: 값}, 사유 문자열). 하나라도 모자라면 빈 맵이다.
                단일 필드 제공자는 필드명이 `key` 다.
        """
        pid = str(provider or "")
        if not pid:
            return {}, "no provider"
        fields = (self.providers.get(pid) or {}).get("fields")
        if not isinstance(fields, (list, tuple)) or not fields:
            value, why = self.read_key(pid)
            return ({"key": value} if value else {}), why
        out = {}
        missing = []
        unreadable = []
        # 다필드 제공자도 형식 식은 제공자 단위다 - 칸마다 다른 식을 두면
        # 선언이 늘고 얻는 것이 없다.
        pattern, form, _src = provider_key_pattern(self.providers, pid)
        for spec in fields:
            if not isinstance(spec, dict) or not spec.get("name"):
                continue
            name = str(spec["name"])
            setting = str(spec.get("setting")
                          or (self.key_prefix + pid + "__" + name))
            required = bool(spec.get("required", True))
            value, _why = read_setting(self.ini_path, setting)
            if not value:
                if required:
                    missing.append(name)
                continue
            okay, bad = validate_key_value(value, pattern, form)
            if not okay:
                # 형식을 못 읽었으면 추측하지 않는다. 어느 칸인지와 **사유
                # 문구**만 말한다 - 값은 어느 경로로도 적지 않는다.
                unreadable.append("%s(%s)" % (name, bad))
                continue
            self.note_secret(value)
            out[name] = value
        if missing or unreadable:
            parts = []
            if missing:
                parts.append("비어 있는 필드: %s" % ", ".join(missing))
            if unreadable:
                parts.append("형식을 읽지 못한 필드: %s" % ", ".join(unreadable))
            return {}, "; ".join(parts)
        return out, "ini"

    def ensure_token(self, entry, force=False):
        """제공자 토큰을 확보한다. **메모리에만 둔다**(설계 docs/8 2-3).

        토큰은 디스크에 쓰지 않고, 도구 결과에도 `collect_meta.json` 에도
        넣지 않는다. 발급 즉시 비밀 레지스터를 지나므로 그 뒤의 모든 마스킹
        대상에 자동으로 들어간다 - 호출부가 토큰을 따로 넘기지 않는다.

        Args:
            entry: 해석된 카탈로그 항목.
            force: True 면 캐시를 무시하고 다시 발급받는다(재인증 1회 경로).

        Returns:
            str: accessToken.

        Raises:
            ToolError: 키 필드가 모자라거나, 인증 응답이 실패이거나, 토큰이
                마스킹 최소 길이에 못 미칠 때.
        """
        pid = str(entry.get("provider") or "")
        if not force and self._tokens.get(pid):
            return self._tokens[pid]
        meta = self.providers.get(pid) or {}
        spec = meta.get("auth_endpoint") or {}
        if not spec.get("url"):
            raise ToolError("제공자 %s 의 인증 엔드포인트 선언이 없습니다" % pid)
        fields, why = self.read_keys(pid)
        if not fields:
            raise ToolError(
                "제공자 %s 의 API 키가 설정되지 않았습니다 (%s). QGIS 설정 "
                "%s 에 값을 저장하세요."
                % (pid, why,
                   ", ".join(str(f.get("setting") or "")
                             for f in (meta.get("fields") or ())
                             if isinstance(f, dict))))
        params = {}
        for field_name, param_name in (spec.get("params") or {}).items():
            if str(field_name) not in fields:
                raise ToolError("제공자 %s 의 인증에 필요한 키 필드 %s 가 "
                                "없습니다" % (pid, field_name))
            params[str(param_name)] = fields[str(field_name)]
        base = self.endpoint_override or str(spec["url"])
        url = base + ("&" if "?" in base else "?") + urllib.parse.urlencode(params)
        code, body, fail = http_get_retry(url, self.log, self.mask)
        if fail or code != 200:
            raise ToolError("제공자 %s 인증 요청이 실패했습니다: %s"
                            % (pid, self.mask(fail or ("HTTP %s" % code))))
        try:
            payload = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            raise ToolError("제공자 %s 인증 응답이 JSON 이 아닙니다" % pid)
        err = spec.get("error") or {}
        if err.get("code_path"):
            seen, value = dig(payload, err["code_path"])
            ok_values = [str(v) for v in (err.get("ok") or ())]
            if not seen or (ok_values and str(value) not in ok_values):
                raise ToolError("제공자 %s 인증을 거부했습니다 (%s=%s)"
                                % (pid, err["code_path"], value))
        seen, token = dig(payload, str(spec.get("token_path") or ""))
        token = str(token or "") if seen else ""
        if not token:
            raise ToolError("제공자 %s 인증 응답에서 토큰 경로 %r 를 찾지 "
                            "못했습니다. 본 최상위 키: %s"
                            % (pid, spec.get("token_path"),
                               ", ".join(top_key_names(payload))))
        if len(token) < REDACT_MIN_LEN:
            # 마스킹은 `REDACT_MIN_LEN` 미만 문자열을 레지스터에 넣지 않는다
            # (짧은 값을 치환하면 본문이 잠식된다). 그 길이 아래의 토큰은
            # 등록해도 지워지지 않으므로 **쓰지 않고 멈춘다** - 로그와
            # 사이드카에 평문으로 남는 길을 막는다.
            raise ToolError("제공자 %s 가 돌려준 토큰이 마스킹 최소 길이(%d자)"
                            "보다 짧아 사용하지 않았습니다"
                            % (pid, REDACT_MIN_LEN))
        self.note_secret(token)
        self._tokens[pid] = token
        self.log.write("auth", "provider=%s token_len=%d reauth=%s"
                       % (pid, len(token), bool(force)))
        return token

    # ------------------------------------------------------------------
    # 수집
    # ------------------------------------------------------------------

    def build_url(self, entry, secret, bbox, max_features, crs, args=None):
        """레지스트리 템플릿과 허용 인자로 URL 을 만든다.

        모델은 이 함수에 **URL 을 넘기지 못한다.** base 와 고정 파라미터는
        카탈로그가, 가변 파라미터는 화이트리스트가 정한다. 문자열 연결로
        경로를 조립하지 않는다 - 값은 전부 `urlencode` 를 거친다.

        파라미터 **이름**이 빈 문자열이면 그 축을 아예 싣지 않는다. 제공자마다
        받는 축이 달라서다 - SGIS 는 bbox·srsName·maxFeatures 를 받지 않으므로
        카탈로그가 그 세 이름을 빈 값으로 선언한다. 이름을 비우는 것이
        "이 제공자에는 그 축이 없다" 를 코드가 아니라 선언으로 적는 방식이다
        (설계 docs/8 3-1 의 제공자별 코드가 아니라 제공자별 데이터).

        Args:
            entry: 해석된 카탈로그 항목.
            secret: `auth=key_query` 면 제공자 키, `auth=token` 이면 발급받은
                accessToken. 둘 다 모델이 아니라 서버가 구한 값이다.
            bbox: 정규화된 bbox 또는 None.
            max_features: 페이지당 상한 또는 None.
            crs: 요청 좌표계 또는 빈 값.
            args: `validate_args()` 를 통과한 질의 파라미터 맵.

        Returns:
            str: 전체 URL(비밀 포함).
        """
        base = self.endpoint_override or entry.get("base_url", "")
        params = dict(entry.get("fixed_params") or {})
        for name, value in (args or {}).items():
            params[name] = value
        if entry.get("typename"):
            params[entry.get("typename_param", "typename")] = entry["typename"]
        auth = str(entry.get("auth") or "none")
        if auth == "key_query":
            params[entry.get("key_param", "key")] = secret
        elif auth == "token" and secret:
            params[entry.get("token_param", "accessToken")] = secret
        bbox_param = entry.get("bbox_param", "bbox")
        if bbox is not None and bbox_param:
            params[bbox_param] = "%.8f,%.8f,%.8f,%.8f" % bbox
        crs_param = entry.get("crs_param", "srsName")
        if crs and crs_param:
            params[crs_param] = crs
        mf_param = entry.get("max_features_param", "maxFeatures")
        if max_features and mf_param:
            params[mf_param] = max_features
        return base + ("&" if "?" in base else "?") + urllib.parse.urlencode(params)

    def collect(self, dataset_id, bbox=None, max_features=None, crs=None,
                args=None):
        """수집 1회. 받고 저장하고 합치고 요약한다.

        Args:
            dataset_id: 카탈로그 id.
            bbox: minx,miny,maxx,maxy (데이터셋이 요구하면 필수).
            max_features: 페이지당 상한. 카탈로그 상한을 넘기지 못한다.
            crs: 요청 좌표계. 비우면 카탈로그 default_crs.
            args: 데이터셋 `params` 화이트리스트의 부분집합(설계 docs/8 3-2).

        Returns:
            dict: 저장 경로와 요약 수치.

        Raises:
            ToolError: 인자나 전제조건이 어긋났을 때, 그리고 응답 봉투 선언이
                빗나가 **한 건도 읽지 못했을 때**(설계 docs/8 2-4 - 조용한
                0건 성공을 만들지 않는다).
        """
        started = time.time()
        if self.calls >= LIMIT_CALLS_PER_SESSION:
            raise ToolError("세션당 수집 호출 상한 %d 회를 넘었습니다"
                            % LIMIT_CALLS_PER_SESSION)
        self.ensure_catalog()
        entry = self.registry.get(str(dataset_id or ""))
        if entry is None:
            raise ToolError("unknown dataset id: %r (use list_datasets)"
                            % (dataset_id,))
        if not entry.get("supported", True):
            raise ToolError("이 데이터셋은 아직 지원하지 않습니다: %s"
                            % (entry.get("notes") or "사유 미기재"))
        auth = str(entry.get("auth") or "none")
        if auth not in ("none", "key_query", "token"):
            raise ToolError("이 데이터셋의 인증 방식(%s)은 아직 구현되지 "
                            "않았습니다" % auth)
        secret = ""
        if auth == "key_query":
            secret, why = self.read_key(entry.get("provider", ""))
            if not secret:
                raise ToolError(
                    "제공자 %s 의 API 키가 설정되지 않았습니다 (%s). QGIS 설정 "
                    "%s%s 에 키를 저장하세요."
                    % (entry.get("provider"), why, self.key_prefix,
                       entry.get("provider")))
        elif auth == "token":
            # 여기서 쓰는 비밀은 저장 키가 아니라 **발급받은 토큰**이다.
            # ensure_token 이 키 부재를 네트워크 요청 전에 걸러 내므로
            # "키도 없는데 인증 요청부터 나간다" 가 성립하지 않는다.
            secret = self.ensure_token(entry)
        call_args = validate_args(entry, args)
        for name in entry.get("required") or ():
            if name == "bbox" and bbox is None:
                raise ToolError("이 데이터셋은 bbox 인자가 필수입니다")
        try:
            box = parse_bbox(bbox) if bbox is not None else None
        except ValueError as exc:
            raise ToolError("bbox 형식 오류: %s" % exc)
        cap = int(entry.get("page_limit") or 1000)
        try:
            per_page = int(max_features) if max_features else cap
        except (TypeError, ValueError):
            raise ToolError("max_features 는 정수여야 합니다")
        per_page = max(1, min(per_page, cap))
        want_crs = str(crs or entry.get("default_crs") or "")
        allowed_crs = entry.get("allowed_crs") or ()
        if allowed_crs and want_crs not in allowed_crs:
            raise ToolError("이 데이터셋이 받는 좌표계는 %s 입니다"
                            % ", ".join(allowed_crs))

        self.calls += 1
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(self.root, safe_slug(entry.get("provider")),
                               safe_slug(entry.get("id")), stamp)
        if not inside(self.root, out_dir):
            raise ToolError("출력 경로가 작업 폴더를 벗어났습니다")
        os.makedirs(out_dir, exist_ok=True)

        state = {"pages": 0, "bytes": 0, "features": {}, "records": [],
                 "incomplete": False, "stop_reason": "", "errors": [],
                 "urls": [], "redactions": 0, "envelope_fatal": False,
                 "top_keys": [], "args": call_args,
                 # 현재 회차가 쓰는 비밀과 남은 재인증 예산. 토큰은 재발급으로
                 # 바뀌므로 호출 인자가 아니라 여기에 둔다(_one 참조).
                 "secret": secret, "token_retry": 0,
                 # 서버가 만드는 페이징 파라미터. `_one` 이 args 위에 덮는다.
                 "paging_params": {}, "last_total": None}
        mode = paging_mode(entry)
        if mode not in PAGING_MODES:
            raise ToolError("이 데이터셋의 페이징 선언(%s)은 아직 구현되지 "
                            "않았습니다" % mode)
        if mode == "tile_subdivide" and box is not None:
            self._tile(entry, secret, box, per_page, want_crs, out_dir, state,
                       started, depth=0)
        elif mode == "page_no":
            self._pages(entry, secret, box, per_page, want_crs, out_dir, state,
                        started)
        else:
            self._one(entry, secret, box, per_page, want_crs, out_dir, state,
                      started)

        features = list(state["features"].values())
        merged_path, merged_bytes = self._derive(entry, out_dir, features,
                                                 state, want_crs)
        # 레코드 봉투 + 좌표 선언이면 피처를 만든 쪽이 `_derive` 다. 요약과
        # CSV 로그가 **같은 목록**을 세야 한다 - `state["features"]` 는
        # geojson 봉투 전용이고, 거기만 보면 사이드카와 로그가 어긋난다.
        shown = features or list(state.get("derived") or ())
        summary = self._summarize(entry, shown, want_crs, box, per_page,
                                  state, out_dir, merged_path, merged_bytes,
                                  started)
        write_atomic(os.path.join(out_dir, "collect_meta.json"),
                     json.dumps(summary["meta"], ensure_ascii=False,
                                indent=2).encode("utf-8"))
        self.csv_log.row(
            ts=time.strftime("%Y-%m-%d %H:%M:%S"), dataset=entry.get("id"),
            params="bbox=%s max_features=%s crs=%s args=%s"
                   % (box, per_page, want_crs,
                      json.dumps(call_args, ensure_ascii=False,
                                 sort_keys=True)),
            pages=state["pages"], bytes=state["bytes"],
            features=len(shown), crs=want_crs,
            status="INCOMPLETE" if state["incomplete"] else "OK",
            elapsed_s="%.3f" % (time.time() - started),
            url_masked=(state["urls"] or [""])[0],
            error=" | ".join(state["errors"])[:400])
        self.log.write("collect_done", json.dumps(summary["result"],
                                                  ensure_ascii=False)[:1500])
        # 선언 경로가 빗나가 **한 건도 읽지 못했으면 성공이 아니다**(설계 docs/8
        # 2-4). 원본 페이지와 사이드카·CSV 는 이미 남겼고, 그 자리를 알려주면서
        # 구조화 오류로 끝낸다 - 빈 레이어가 "데이터 없는 지역" 으로 읽히는
        # 경로를 닫는다.
        if state["envelope_fatal"] and not shown and not state["records"]:
            raise ToolError(
                "응답을 읽지 못했습니다. 선언된 봉투와 실제 응답이 다릅니다. "
                "원본은 %s 에 남겼습니다. 본 최상위 키: %s. 사유: %s"
                % (out_dir, ", ".join(state["top_keys"][:TOP_KEYS_MAX]) or "(없음)",
                   " | ".join(state["errors"])[:300]))
        return summary["result"]

    def _one(self, entry, secret, box, per_page, crs, out_dir, state, started):
        """페이지 1장을 받아 원본 그대로 저장하고 선언된 봉투로 읽는다.

        `auth=token` 이면 선언된 오류 채널이 실패를 말했을 때 **딱 1회**
        재인증하고 같은 페이지를 다시 받는다(설계 docs/8 2-3). 재인증 횟수는
        수집 1회 전체에 걸린 예산이라 `state` 가 들고 있다 - 타일 분할로
        `_one` 이 여러 번 불려도 토큰 재발급은 통틀어 한 번이다. 실패한 첫
        응답도 **지우지 않고 페이지 파일로 남긴다**(원본성 규칙).

        Returns:
            int: 이 응답에서 새로 얻은 피처 또는 레코드 수.
        """
        auth = str(entry.get("auth") or "none")
        while True:
            if self._over_limit(state, started):
                return 0
            # 토큰은 재인증 때 바뀐다. 호출 인자가 아니라 state 를 본다.
            use_secret = state.get("secret") or secret
            # 페이징 파라미터는 **서버가 만든 값**이라 args 화이트리스트를
            # 지나지 않는다(모델이 페이지 번호를 고르지 않는다). 사용자 args
            # 위에 덮으므로 같은 이름을 args 로 넣어도 질의가 두 번 조립되지
            # 않는다 - 덮었다는 사실은 `paging_params` 로 로그에 남는다.
            call_args = dict(state.get("args") or {})
            call_args.update(state.get("paging_params") or {})
            url = self.build_url(entry, use_secret, box, per_page, crs,
                                 args=call_args)
            masked = self.mask(url)
            state["urls"].append(masked)
            code, body, why = http_get_retry(url, self.log, self.mask)
            if why or code != 200:
                state["incomplete"] = True
                # 전송 예외 문구도 마스킹을 지난다 - 어떤 라이브러리가 요청
                # URL 을 예외 메시지에 넣는지 전부 알지 못한다.
                state["errors"].append(
                    "%s (%s)" % (self.mask(why or "HTTP %s" % code), masked))
                return 0
            state["pages"] += 1
            # 응답 본문도 비밀 집합을 지난 뒤에 디스크로 간다(설계 docs/8 10
            # 첫 항목 - GetCapabilities 가 요청 URL 을 응답에 되돌린 실측).
            # 비밀이 없으면 바이트가 그대로 남고, 치환이 있었으면 건수를
            # 사이드카에 적는다.
            body, hits = self.mask_response(body)
            state["redactions"] += hits
            kind = str((entry.get("response") or {}).get("kind") or "")
            ext = "xml" if kind == "xml_records" else (
                "json" if kind in ("geojson", "json_records") else "txt")
            page_name = "page_%04d.%s" % (state["pages"], ext)
            state["bytes"] += write_atomic(os.path.join(out_dir, page_name),
                                           body)
            parsed = parse_response(entry, body, page_name)
            if not parsed["error"]:
                break
            if auth == "token" \
                    and state.get("token_retry", 0) < TOKEN_REAUTH_MAX:
                # 토큰 만료와 인자 오류를 응답만으로 가를 수 없다(둘 다
                # errMsg 로 온다). 그래서 **한 번만** 다시 받아 보고, 그래도
                # 같은 오류면 그 오류를 그대로 올린다. 무한 재인증은 쿼터를
                # 태운다(설계 docs/8 2-3).
                state["token_retry"] = state.get("token_retry", 0) + 1
                try:
                    state["secret"] = self.ensure_token(entry, force=True)
                except ToolError as exc:
                    state["incomplete"] = True
                    state["envelope_fatal"] = True
                    state["errors"].append(self.mask(str(exc)))
                    return 0
                state["errors"].append(
                    "제공자 오류 뒤 토큰을 1회 재발급했습니다 (%s)"
                    % self.mask(parsed["error"])[:200])
                continue
            state["incomplete"] = True
            state["envelope_fatal"] = True
            state["errors"].append(self.mask(parsed["error"]))
            for name in parsed["top_keys"]:
                if name not in state["top_keys"]:
                    state["top_keys"].append(name)
            return 0
        # 총건수는 페이징 종료 조건이다. 못 읽으면 None 이고 그때는 빈 페이지가
        # 유일한 종료 조건이 된다(설계 docs/8 3-1).
        state["last_total"] = parsed.get("total")
        got = 0
        if parsed["kind"] == "geojson":
            for feat in parsed["items"]:
                fid = feat.get("id") or json.dumps(
                    feat.get("properties"), sort_keys=True, ensure_ascii=False)
                state["features"][fid] = feat
                got += 1
        else:
            # 레코드는 중복 제거를 하지 않는다. 키가 될 필드를 제공자마다 모르고,
            # 추측한 키로 합치면 원본보다 적은 행이 파생물에 남는다.
            state["records"].extend(parsed["items"])
            got = len(parsed["items"])
        return got

    def _pages(self, entry, secret, box, per_page, crs, out_dir, state,
               started):
        """`page_no` 페이징. 총건수로 끝을 알고, 못 읽으면 빈 페이지로 끝낸다.

        두 종료 조건이 다 필요한 이유(설계 docs/8 3-1): 강의 러너가 상가
        API 에서는 `totalCount` 로 끝내고 빈 `items` 도 같이 보고 있다
        [실측 - collect_store.main()]. 총건수를 안 주거나 숫자로 못 읽는
        기관 API 가 있을 수 있으므로(U11) 한 조건만 두면 무한 루프가 된다.

        페이지 상한은 **기존 한도와 같은 자리**다 - `_over_limit` 이
        페이지·바이트·경과 세 축을 보고 넘으면 `incomplete` 를 세운다.
        데이터셋 선언의 `paging.max_pages` 는 그보다 작은 상한을 둘 수 있다
        (쿼터가 기관마다 다르고 비공개가 다수라서다 - 설계 docs/8 3-5).

        Args:
            entry: 해석된 카탈로그 항목.
            secret: 키 또는 토큰.
            box: 정규화된 bbox 또는 None.
            per_page: 페이지 크기.
            crs: 요청 좌표계.
            out_dir: 이번 회차 저장 폴더.
            state: 수집 상태.
            started: 시작 시각.
        """
        spec = paging_spec(entry)
        page_param = str(spec.get("page_param") or "pageNo")
        size_param = str(spec.get("size_param") or "")
        first = 1
        try:
            declared_max = int(spec.get("max_pages") or 0)
        except (TypeError, ValueError):
            declared_max = 0
        max_pages = min(declared_max or LIMIT_PAGES, LIMIT_PAGES)
        page_no = first
        while True:
            if self._over_limit(state, started):
                return
            params = {page_param: str(page_no)}
            if size_param:
                params[size_param] = str(per_page)
            state["paging_params"] = params
            got = self._one(entry, secret, box, per_page, crs, out_dir, state,
                            started)
            if state.get("envelope_fatal"):
                return
            if got <= 0:
                # 빈 페이지가 정상 종료다. 전송 실패도 여기로 오는데 그때는
                # `_one` 이 이미 incomplete 와 사유를 세워 둔다.
                return
            total = state.get("last_total")
            # 끝 판정식은 강의 러너와 같다 - `page * size >= total` 이다
            # [실측 - collect_store/collect_realprice]. 받은 레코드 수로
            # 세지 않는 이유는 중복 제거가 끼면 끝을 못 만나기 때문이다.
            if total is not None and page_no * per_page >= int(total):
                return
            if page_no - first + 1 >= max_pages:
                state["incomplete"] = True
                reason = "페이지 상한 %d 에서 멈췄습니다 (page_no=%d, total=%s)" \
                    % (max_pages, page_no, total)
                if not state["stop_reason"]:
                    state["stop_reason"] = "pages>=%d" % max_pages
                state["errors"].append(reason)
                return
            page_no += 1

    def _tile(self, entry, secret, box, per_page, crs, out_dir, state, started,
              depth):
        """상한에 걸린 타일을 2x2 로 재귀 분할한다.

        V-World WFS 는 페이지 파라미터 없이 maxFeatures 상한만 있다. 한 요청이
        상한을 꽉 채우면 잘린 것이므로 영역을 쪼개 다시 받는다(강의 러너가 쓴
        방식과 같은 보정이다).
        """
        got = self._one(entry, secret, box, per_page, crs, out_dir, state,
                        started)
        if got < per_page or depth >= TILE_MAX_DEPTH:
            if got >= per_page and depth >= TILE_MAX_DEPTH:
                state["incomplete"] = True
                state["errors"].append("타일 분할 상한(depth=%d)에서 멈췄습니다"
                                       % TILE_MAX_DEPTH)
            return
        minx, miny, maxx, maxy = box
        midx = (minx + maxx) / 2.0
        midy = (miny + maxy) / 2.0
        for sub in ((minx, miny, midx, midy), (midx, miny, maxx, midy),
                    (minx, midy, midx, maxy), (midx, midy, maxx, maxy)):
            if self._over_limit(state, started):
                return
            self._tile(entry, secret, sub, per_page, crs, out_dir, state,
                       started, depth + 1)

    def _over_limit(self, state, started):
        """한도를 넘었는가. 넘으면 부분 저장 상태로 멈춘다.

        부분 수집도 버리지 않고 저장하고 `incomplete=true` 를 적는다
        (저장소 데이터 원본성 규칙).
        """
        if state["pages"] >= LIMIT_PAGES:
            state["stop_reason"] = "pages>=%d" % LIMIT_PAGES
        elif state["bytes"] >= LIMIT_BYTES:
            state["stop_reason"] = "bytes>=%d" % LIMIT_BYTES
        elif time.time() - started >= LIMIT_SECONDS:
            state["stop_reason"] = "elapsed>=%.0fs" % LIMIT_SECONDS
        else:
            return False
        state["incomplete"] = True
        if state["stop_reason"] not in state["errors"]:
            state["errors"].append(state["stop_reason"])
        return True

    def _derive(self, entry, out_dir, features, state, crs):
        """파생 산출물을 만든다. 원본 페이지는 건드리지 않는다.

        봉투별로 갈리는 지점이다(설계 docs/8 3-1).
            geojson       합본 GeoJSON
            레코드 + 좌표 선언  파생 GeoJSON 포인트(원본 JSON·XML 은 그대로)
            레코드 (좌표 없음)   파생 CSV. `layer_path` 를 비우고 `table_path` 로 준다

        Args:
            entry: 해석된 카탈로그 항목.
            out_dir: 이번 회차 저장 폴더.
            features: 모은 GeoJSON Feature 목록.
            state: 수집 상태. `table_path` 를 여기에 적는다.
            crs: 요청 좌표계.

        Returns:
            tuple: (layer_path, 쓴 바이트 수). 공간 결과가 없으면 layer_path 는
                빈 문자열이다.
        """
        state["table_path"] = ""
        # 파생 포인트 목록. 레코드 봉투에서는 `state["features"]` 가 비어
        # 있으므로(그 dict 는 geojson 봉투의 중복 제거용이다) 요약이 세어야 할
        # 피처가 여기 있다. 비우지 않으면 "레이어는 20건인데 도구 결과는
        # features=0" 이 되고, 모델은 결과 수치를 그대로 쓰도록 지시받아 있어
        # 사용자에게 "0건" 을 말한다(2026-10-17 실키 측정에서 적발).
        state["derived"] = []
        resp = entry.get("response") or {}
        kind = str(resp.get("kind") or "")
        records = state.get("records") or []
        # 봉투 선언이 산출물을 정한다. 레코드가 0건이어도 레코드 봉투는 레코드
        # 경로로 간다 - 빈 GeoJSON 을 돌려주면 모델이 비공간 결과를 레이어로
        # 적재하려 든다.
        if kind == "geojson" or not kind:
            return self._merge(out_dir, features, crs)
        lon_field = str(resp.get("lon_field") or "")
        lat_field = str(resp.get("lat_field") or "")
        if lon_field and lat_field:
            points = []
            dropped = 0
            for row in records:
                try:
                    lon = float(row.get(lon_field))
                    lat = float(row.get(lat_field))
                except (TypeError, ValueError):
                    dropped += 1
                    continue
                points.append({"type": "Feature",
                               "geometry": {"type": "Point",
                                            "coordinates": [lon, lat]},
                               "properties": dict(row)})
            if dropped:
                # 파생물에서 빠진 행은 원본에 그대로 있다. 숨기지 않고 센다.
                state["incomplete"] = True
                state["errors"].append(
                    "좌표가 없는 레코드 %d 건은 파생 레이어에서 빠졌습니다"
                    "(원본 페이지에는 그대로 있습니다)" % dropped)
            state["derived"] = points
            return self._merge(out_dir, points,
                               str(resp.get("crs") or crs))
        state["table_path"] = self._write_table(out_dir, records)
        try:
            return "", os.path.getsize(state["table_path"])
        except OSError:
            return "", 0

    def _write_table(self, out_dir, records):
        """비공간 레코드를 파생 CSV 로 쓴다.

        열 순서는 **처음 본 순서**다. 정렬하면 제공자 응답의 열 순서가 사라져
        원본과 대조하기 어려워진다. 어느 행에 없는 열은 빈 칸으로 둔다.

        Returns:
            str: CSV 경로.
        """
        columns = []
        for row in records:
            for name in row:
                if name not in columns:
                    columns.append(name)
        buf = io.StringIO(newline="")
        writer = csv.writer(buf)
        writer.writerow(columns)
        for row in records:
            writer.writerow([row.get(name, "") for name in columns])
        path = os.path.join(out_dir, "records.csv")
        # BOM 을 붙인다. 엑셀이 BOM 없는 UTF-8 CSV 를 cp949 로 읽어 한글 열
        # 이름이 깨지고, 사용자가 받는 첫 화면이 그 창이다.
        write_atomic(path, buf.getvalue().encode("utf-8-sig"))
        return path

    def _merge(self, out_dir, features, crs):
        """합본 GeoJSON 을 쓴다. 원본 페이지는 덮지 않는다.

        좌표계는 **받은 그대로**다. 서버가 재투영하지 않는다(설계 docs/2 4-4).
        EPSG 를 레거시 `crs` 멤버로 명시해 QGIS 가 원본 좌표계로 적재하게 한다.

        Returns:
            tuple: (합본 경로, 바이트 수)
        """
        urn = ""
        if crs.upper().startswith("EPSG:"):
            urn = "urn:ogc:def:crs:EPSG::" + crs.split(":", 1)[1]
        doc = {"type": "FeatureCollection", "features": features}
        if urn:
            doc["crs"] = {"type": "name", "properties": {"name": urn}}
        path = os.path.join(out_dir, "merged.geojson")
        n = write_atomic(path, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        return path, n

    def _summarize(self, entry, features, crs, box, per_page, state, out_dir,
                   merged_path, merged_bytes, started):
        """요약 수치를 서버가 계산한다(설계 docs/2 4-6).

        Returns:
            dict: result(도구 결과)와 meta(사이드카) 두 묶음.
        """
        # 좌표계는 **레이어를 만든 쪽**이 아는 값이다. 레코드 봉투 + 좌표
        # 선언 경로에서는 `default_crs` 가 비어 있고(비공간일 수도 있는
        # 데이터셋이라 비워 둔다) 실제 좌표계는 `response.crs` 선언에 있다.
        # 그것을 여기서 집지 않으면 `_merge` 는 EPSG 를 박는데 요약과
        # `load_hint` 는 "좌표계는  입니다." 로 나간다(2026-10-17 실키 측정).
        crs = str(crs or (entry.get("response") or {}).get("crs") or "")
        fields = []
        for feat in features[:200]:
            for name in (feat.get("properties") or {}):
                if name not in fields:
                    fields.append(name)
        bbox_out = None
        for feat in features:
            for x, y in iter_coords((feat.get("geometry") or {}).get("coordinates")):
                if bbox_out is None:
                    bbox_out = [x, y, x, y]
                else:
                    bbox_out[0] = min(bbox_out[0], x)
                    bbox_out[1] = min(bbox_out[1], y)
                    bbox_out[2] = max(bbox_out[2], x)
                    bbox_out[3] = max(bbox_out[3], y)
        records = state.get("records") or []
        table_path = str(state.get("table_path") or "")
        result = {
            "dataset": entry.get("id"),
            "title": entry.get("title", ""),
            "saved_dir": out_dir,
            "layer_path": merged_path,
            # 비공간 결과의 자리(설계 docs/8 3-2). 공간 결과면 빈 문자열이고,
            # 공간 결과가 없으면 layer_path 가 빈 문자열이 된다. 둘 중 하나는
            # 항상 비어 있다 - 스킬 4단계가 그것으로 분기한다.
            "table_path": table_path,
            "pages": state["pages"],
            "features": len(features),
            "record_count": len(records) if records else len(features),
            "fields": fields,
            "bbox": bbox_out,
            "crs": crs,
            "bytes_raw": state["bytes"],
            "bytes_merged": merged_bytes,
            # 응답 본문에서 비밀을 치환한 건수(설계 docs/8 10 첫 항목). 0 이
            # 아니면 디스크의 원본 페이지가 그만큼 변조된 것이므로 적어 둔다.
            "redactions": int(state.get("redactions", 0)),
            "incomplete": bool(state["incomplete"]),
            "stop_reason": state["stop_reason"],
            "errors": state["errors"][:5],
            "elapsed_s": round(time.time() - started, 3),
            # 비공간 결과도 적재한다(사용자 결정 D5 개정, 2026-10-17). 적재
            # 가능성은 U13 이 실측으로 닫았다(58, records.csv -> QgsProject
            # 레이어 1개, 전 필드 String). 스킬 4단계 문구와 같은 말을 해야
            # 한다 - 서버와 스킬이 어긋나면 모델이 둘 중 하나를 고른다.
            "load_hint": (
                "add_vector_layer 에 layer_path 를 그대로 넘기세요. 좌표계는 "
                "%s 입니다." % crs if merged_path else
                "공간 결과가 아닙니다. add_vector_layer 에 table_path 를 "
                "넘겨 표로 적재하고, 도형이 없어 지도에 그려지지 않으며 "
                "속성 테이블과 조인에 쓴다는 것을 사용자에게 알리세요. 전 "
                "필드가 문자열로 읽힙니다 - 숫자 열은 변환 후에 통계나 "
                "단계구분 스타일에 쓰세요."),
        }
        if state.get("top_keys"):
            # 선언이 빗나갔을 때의 진단. **키 이름만** 싣는다(값은 유출면이다).
            result["response_top_keys"] = list(state["top_keys"])[:TOP_KEYS_MAX]
        meta = dict(result)
        meta.update({
            "requested_bbox": list(box) if box else None,
            "max_features": per_page,
            "args": dict(state.get("args") or {}),
            "provider": entry.get("provider"),
            "source_file": entry.get("source_file", ""),
            "url_masked": (state["urls"] or [""])[0],
            # 페이징 계보. `page_no` 회차가 총건수로 끝났는지 빈 페이지로
            # 끝났는지 사이드카만 보고 되짚을 수 있어야 한다.
            "paging_mode": paging_mode(entry),
            "total_reported": state.get("last_total"),
            "paging_params_last": dict(state.get("paging_params") or {}),
            "requested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "plugin_version": SERVER_VERSION,
            "endpoint_override": bool(self.endpoint_override),
        })
        return {"result": result, "meta": meta}


def iter_coords(node):
    """GeoJSON 좌표 트리에서 (x, y) 쌍을 모두 꺼낸다.

    BBOX 를 서버가 계산해야 하므로(설계 docs/2 4-6) 중첩 깊이를 가정하지 않고
    훑는다.
    """
    if not isinstance(node, (list, tuple)) or not node:
        return
    if isinstance(node[0], (int, float)) and len(node) >= 2:
        yield float(node[0]), float(node[1])
        return
    for child in node:
        for pair in iter_coords(child):
            yield pair


class ToolError(Exception):
    """도구 결과로 돌려줄 구조화 오류. 스택을 모델에 보내지 않는다."""


# ---------------------------------------------------------------- MCP 프로토콜
TOOLS = [
    # description 은 모델이 읽는 데이터다. 절차의 대부분이 여기 들어 있어
    # 스킬이 없어도 기능이 동작한다(설계 docs/2 6-1 P-C 안전망).
    {
        "name": "list_datasets",
        "description": ("List the public datasets this plugin can collect, with "
                        "whether the provider API key is configured. Call this "
                        "first. The list is paged: it returns at most 'limit' "
                        "rows (default 30) plus 'total' and 'truncated'. If "
                        "'truncated' is true, narrow the list with 'query' "
                        "instead of paging through everything. A row with "
                        "'supported': false cannot be collected: never offer it "
                        "as a candidate, and if the user names it, report its "
                        "'unsupported_why' instead of collecting. 'providers' "
                        "lists every provider this plugin declares with its "
                        "'key_configured' and its dataset count, so a provider "
                        "with 0 datasets still appears. When the call finds "
                        "nothing at all, the result carries 'portal_search': "
                        "a data.go.kr portal search link built from your "
                        "'query', plus the notice to show with it. Show that "
                        "link to the user and stop; you cannot fetch it and "
                        "nothing here opens it. Returns no secrets."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string",
                             "description": "keep only this provider id"},
                "query": {"type": "string",
                          "description": ("case-insensitive substring of the "
                                          "dataset id or title")},
                "limit": {"type": "integer",
                          "description": "max rows, default 30, capped at 100"},
                "offset": {"type": "integer", "description": "rows to skip"},
            },
            "required": [],
        },
    },
    {
        "name": "describe_dataset",
        "description": ("Describe one dataset: which arguments you may pass, "
                        "which are required, the paging mode and the coordinate "
                        "reference system. 'returns' tells you whether collect "
                        "will give back a layer_path or a table_path. If "
                        "'supported' is false, collect will refuse this dataset: "
                        "report 'notes' as the reason instead of calling it. Ask "
                        "for any missing argument instead of guessing a "
                        "default."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string",
                               "description": "id from list_datasets"},
            },
            "required": ["dataset_id"],
        },
    },
    {
        "name": "collect",
        "description": ("Download one dataset into the plugin workspace and "
                        "return the saved file path plus a summary (pages, "
                        "feature count, field names, bbox, CRS, bytes, whether "
                        "the result is incomplete). The server picks the output "
                        "path; you cannot pass one. Pass the returned "
                        "layer_path to add_vector_layer; if layer_path is empty "
                        "the result is not spatial and table_path holds a CSV. "
                        "Use the returned numbers verbatim; do not recount."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string",
                               "description": "id from list_datasets"},
                "bbox": {"type": "string",
                         "description": ("minx,miny,maxx,maxy in the dataset "
                                         "CRS (lon/lat for EPSG:4326)")},
                "max_features": {"type": "integer",
                                 "description": "per-request cap, clamped by the server"},
                "crs": {"type": "string",
                        "description": "request CRS, defaults to the dataset default"},
                "args": {"type": "object",
                         "description": ("dataset specific query arguments. "
                                         "Only names listed in the params map "
                                         "of describe_dataset are accepted; "
                                         "anything else is refused. API keys "
                                         "are not accepted here - the server "
                                         "reads them from the QGIS settings.")},
            },
            "required": ["dataset_id"],
        },
    },
]


def send(obj, log):
    """JSON-RPC 한 줄 송신. 개행은 \\n 고정이다."""
    body = json.dumps(obj, ensure_ascii=False)
    log.write("SEND", body[:1200])
    sys.stdout.write(body + "\n")
    sys.stdout.flush()


def tool_result(rid, payload, is_error=False):
    """MCP tools/call 응답 한 건. 본문은 JSON 텍스트 블록 하나다."""
    text = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, indent=2)
    return {"jsonrpc": "2.0", "id": rid,
            "result": {"content": [{"type": "text", "text": text}],
                       "isError": bool(is_error)}}


def call_tool(collector, name, args):
    """도구 1건 실행. 결과 본문을 돌려준다.

    Returns:
        tuple: (본문, 오류인가)
    """
    args = args or {}
    try:
        if name == "list_datasets":
            return collector.list_datasets(
                provider=args.get("provider"), query=args.get("query"),
                limit=args.get("limit"), offset=args.get("offset")), False
        if name == "describe_dataset":
            return collector.describe_dataset(args.get("dataset_id")), False
        if name == "collect":
            return collector.collect(
                args.get("dataset_id"), bbox=args.get("bbox"),
                max_features=args.get("max_features"),
                crs=args.get("crs"), args=args.get("args")), False
        return {"error": "unknown tool: %s" % name}, True
    except ToolError as exc:
        return {"error": str(exc)}, True
    except Exception as exc:  # noqa: BLE001 - 서버가 죽으면 세션이 degraded 된다
        collector.log.write("tool_exception", "%s %r" % (name, exc))
        return {"error": "수집 중 오류: %r" % (exc,)}, True


def handle(req, collector, log):
    """요청 1건 처리. 알림이면 None 을 돌려준다."""
    method = req.get("method", "")
    rid = req.get("id")

    if method == "initialize":
        params = req.get("params") or {}
        ver = params.get("protocolVersion") or PROTOCOL_FALLBACK
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": ver,
                           "capabilities": {"tools": {"listChanged": False}},
                           "serverInfo": {"name": SERVER_NAME,
                                          "version": SERVER_VERSION}}}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params") or {}
        payload, is_err = call_tool(collector, params.get("name"),
                                    params.get("arguments"))
        return tool_result(rid, payload, is_err)
    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return {"jsonrpc": "2.0", "id": rid, "result": {key: []}}
    if rid is None:
        return None
    log.write("unknown_method", method)
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": "method not found: %s" % method}}


def main():
    """stdin 의 JSON-RPC 줄을 끝까지 처리한다."""
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdin.reconfigure(encoding="utf-8")
    log = ServerLog(os.environ.get(ENV_LOG, ""))
    log.write("START", "pid=%d python=%s" % (os.getpid(), sys.executable))
    collector = Collector(os.environ, log)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        log.write("RECV", line[:1200])
        try:
            req = json.loads(line)
        except ValueError:
            continue
        try:
            resp = handle(req, collector, log)
        except Exception as exc:  # noqa: BLE001 - 핸들러 예외로 서버가 죽지 않는다
            log.write("HANDLER_ERR", repr(exc))
            continue
        if resp is not None:
            send(resp, log)
    log.write("STOP", "stdin closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
