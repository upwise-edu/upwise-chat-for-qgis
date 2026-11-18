"""LLM API 직결 전송과 SSE 번역 (docs/13 2-2, 4, 6).

이 모듈이 왜 Qt 와 qgis 를 import 하지 않는가
    `protocol.py` 와 같은 조건이고 같은 이유다 - QGIS 밖 하네스에서 합성
    SSE 재생으로 번역 전체를 검증할 수 있어야 한다. 소켓을 실제로 여는
    함수가 여기 있지만, 그 함수들은 **워커 스레드에서만** 불린다
    (docs/13 I-4). 스레드는 `apibackend.py` 가 쥔다.

왜 stdlib `urllib` 인가 (docs/13 4-3)
    이 플러그인의 서드파티 HTTP 의존은 0건이다. `requests` 가 QGIS 번들에
    있다는 측정은 받아들이지만, 쓰는 순간 **플러그인의 첫 site-packages
    의존**이 되고 Linux/macOS/flatpak/OSGeo4W 커스텀은 미측이다. 선례도
    이미 `collect_server.http_get`(`urllib.request`)으로 서 있다.
    `iter_lines` 편의보다 의존 0 의 값이 크다.

    대가 하나를 명시한다. gzip 자동 해제가 없으므로 `Accept-Encoding:
    identity` 를 **우리가 명시**한다 - 압축 스트림은 델타가 뭉칠 위험이
    있다 `[추측]`.

번역의 기준선 둘 (docs/13 4-0. 깨지면 전사가 어긋난다)
    1. **턴을 닫는 것은 synthetic `result` 1줄뿐이다.** SSE `message_stop`
       은 턴을 닫지 않는다 - 상태머신이 그것을 세기만 하는 거동이 그대로다.
    2. **권위 블록(`assistant` 줄)은 각 블록의 `content_block_stop`
       직전에 넣는다.** Claude CLI 의 실관측 순서가 그렇고(protocol.py
       모듈 docstring), 그 순서여야 `machine._match_block` 이 "닫히지 않은
       같은 종류의 마지막 블록" 경로로 짝을 찾는다. `stop` 뒤에 넣으면
       `match_closed_block` 진단이 매 블록 발화한다.

키는 어디까지 가는가 (docs/13 3-3 H-4)
    `build_request`/`build_key_probe` 의 인자로 들어와 **headers dict 에만**
    담긴다. body 에도 URL 에도 들어가지 않고(두 제공자 모두 키를 쿼리
    파라미터로 받지 않는다), 예외 문구에도 들어가지 않는다 - `ApiHttpError`
    는 status, reason, 응답 본문 발췌만 든다(H-5).

설계 정본: docs/13.api_key_backend_design_v1.md 2-2, 4-1, 4-2, 4-3, 6
"""

import json
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import machine, protocol

# ----------------------------------------------------------------------
# 상수
# ----------------------------------------------------------------------

#: User-Agent. **제품명과 버전만 적는다** - 개인정보도 기관명도 넣지 않는다.
USER_AGENT = "upwise-chat-for-qgis/0.7.0"

# 제공자 이름. `adapter_api` 의 `name` 과 같은 문자열이어야 한다. 이 모듈이
# 어댑터를 import 하지 않으므로(의존 방향이 반대다) 문자열로 둔다.
PROVIDER_ANTHROPIC_NAME = "api_anthropic"
PROVIDER_OPENAI_NAME = "api_openai"

# `max_tokens=None` 으로 Anthropic 요청을 만들 때의 폴백. 설정 읽기는
# `llmkeys.read_max_tokens` 가 하고 이 값은 그 경로를 타지 않는 호출
# (하네스, 2차 재사용)에서만 쓰인다. Anthropic 은 이 필드가 **필수**다.
MAX_TOKENS_FALLBACK = 64000

#: Anthropic Messages API 엔드포인트.
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# `anthropic-version` 헤더(사용자 결정 D-1, 2026-11-19).
#
# 이 값을 고른 이유: 이 설계가 쓰는 `thinking.display:"summarized"` 가 그
# 버전의 문서화된 기능이고, 구 버전과의 조합은 미측이다. 알려진 파괴 변경
# (sampling 파라미터가 400)은 우리가 그 파라미터를 보내지 않으므로 해당
# 없다. 값을 내리면 "빈 생각 블록 + 긴 침묵" 이 되거나 400 이 날 수 있다.
ANTHROPIC_VERSION = "2026-10-21"

#: 0토큰 키 점검용 모델 목록 엔드포인트. GET 이고 토큰을 쓰지 않는다.
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"

#: OpenAI 호환 base URL 기본값(패널이 비워 두었을 때).
OPENAI_BASE_DEFAULT = "https://api.openai.com/v1"

#: OpenAI 호환 경로 2개. base URL 뒤에 붙인다.
OPENAI_CHAT_PATH = "/chat/completions"
OPENAI_MODELS_PATH = "/models"

#: 연결 상한(초). 임의값이고 프록시 지연을 감안한 넉넉한 값이다 `[추측]`.
CONNECT_TIMEOUT_S = 15.0

# 소켓 깨우기 주기(초). **취소 반응 지연의 상한이 이 값이다.**
# 값 자체는 거동이 아니라 반응성이다 - 짧게 두면 취소가 빠르고 깨어나는
# 횟수가 는다.
READ_WAKE_S = 1.0

# 연속 무음 상한(초). **`machine.SILENCE_WARN_S` 보다 커야 한다** -
# 같거나 작으면 침묵 경고 바가 뜰 기회가 없다. `ping` 수신이 이 타이머를
# 갱신한다(연결이 살아 있다는 증거다). 하네스 110 D5 가 이 부등식을 판정한다.
IDLE_ABORT_S = 300.0

# 턴 전체 상한(초). **`machine.TURN_TOTAL_MAX_S` 를 그대로 읽어 쓴다.**
# 사본을 만들지 않는 이유: 머신 워치독과 백엔드가 다른 시점에 포기하면
# 사용자가 모순된 상태를 본다.
TURN_MAX_S = machine.TURN_TOTAL_MAX_S

#: 침묵 경고 상한. 위 부등식의 비교 대상이고 사본이 아니다.
SILENCE_WARN_S = machine.SILENCE_WARN_S

#: SSE 본문의 접두. `event:` 줄은 버린다 - 페이로드 안에 `type` 이 있다.
SSE_DATA_PREFIX = "data:"

#: OpenAI 호환 스트림의 종료 표식.
OPENAI_DONE = "[DONE]"

#: 응답 content-type 이 이것이 아니면 턴을 오류로 닫는다. 기관망 프록시가
#: HTML 로그인 페이지를 돌려주는 경로를 "아무 글자도 안 나오는" 증상이
#: 아니라 사유로 바꾸는 것이 이 검사의 목적이다(docs/13 4-3 규칙 4).
SSE_CONTENT_TYPE = "text/event-stream"

#: 오류 사유에 붙일 응답 본문 발췌 상한. 제공자 사유가 길어도 UI 한 줄에
#: 들어가야 한다.
BODY_EXCERPT_MAX = 400

#: content-type 이 어긋났을 때 사유에 붙일 본문 앞부분 길이.
HTML_EXCERPT_MAX = 200

# ----------------------------------------------------------------------
# 사용자 대면 문구 (docs/13 5-6 표. 키 값이 들어가지 않는다)
# ----------------------------------------------------------------------

NOTICE_KEY_MISSING = ("API 키를 설정해야 보낼 수 있습니다. "
                      "[LLM 키] 패널에서 넣으세요.")
NOTICE_401 = "키가 거부됐습니다(HTTP 401). 키를 다시 확인하세요."
NOTICE_403 = ("접근이 거부됐습니다(HTTP 403). 조직 설정이나 키 권한을 "
              "확인하세요.")
NOTICE_429 = "사용 한도에 걸렸습니다(HTTP 429). 잠시 뒤 다시 보내세요."
NOTICE_429_RETRY = ("사용 한도에 걸렸습니다(HTTP 429). %s초 뒤 다시 "
                    "보내세요.")
NOTICE_400 = "요청이 거부됐습니다: %s"
NOTICE_404 = ("모델이나 주소를 찾지 못했습니다(HTTP 404). 모델명과 base URL "
              "을 확인하세요.")
NOTICE_5XX = "제공자 쪽에서 처리하지 못했습니다(%s). 잠시 뒤 다시 보내세요."
NOTICE_HTTP_OTHER = "요청이 실패했습니다(HTTP %s): %s"
NOTICE_TRANSPORT = "연결하지 못했습니다: %s"
NOTICE_NOT_SSE = ("응답이 스트리밍 형식이 아닙니다(content-type %s). "
                  "프록시나 주소를 확인하세요.")
NOTICE_REFUSAL = "모델이 이 요청에 답하지 않았습니다(%s)."
NOTICE_MAX_TOKENS = ("길이 제한으로 답이 끊겼습니다. 토큰 상한을 늘리거나 "
                     "질문을 쪼개 보세요.")
NOTICE_IDLE = "응답이 끊겼습니다(%d초 동안 수신 없음)."

# 스트림이 종료 신호 없이 끊긴 경우. 설계 5-6 표에 없는 문구를 하나 더
# 두는 이유: EOF 자체는 오류가 아니라 정상 반환이고, 그때 "아무 일도 없이
# 빈 답" 을 보여 주면 사용자는 무엇이 잘못됐는지 모른다.
NOTICE_TRUNCATED = "응답이 끝나기 전에 연결이 끊겼습니다."

# 스트림 중 `error` 이벤트. 과부하(`overloaded_error`)가 여기로 온다.
NOTICE_STREAM_ERROR = "제공자가 오류를 보냈습니다: %s"

#: 거절 stop_reason. HTTP 200 인데 내용이 거절인 경우다.
STOP_REFUSAL = "refusal"
#: 길이 제한 stop_reason.
STOP_MAX_TOKENS = "max_tokens"

#: 중단된 턴의 result subtype. 상태머신의 중단 판정 네 조건 중 하나다
#: (`protocol.RESULT_SUBTYPE_ABORTED` 와 같은 값이어야 한다).
RESULT_SUBTYPE_SUCCESS = "success"

# `finish(reason=...)` 의 어휘. 문자열을 호출자가 들지 않게 상수로 둔다.
FINISH_NORMAL = ""
FINISH_INTERRUPT = "interrupt"

#: OpenAI `finish_reason` -> 내부 `stop_reason` 사상(docs/13 4-2 표).
#: 표에 없는 값은 **원문 그대로** 둔다 - 모르는 값에 뜻을 지어내지 않는다.
OPENAI_FINISH_MAP = {
    "stop": "end_turn",
    "length": STOP_MAX_TOKENS,
    "tool_calls": "tool_use",
    "content_filter": "content_filter",
}


# ----------------------------------------------------------------------
# 예외
# ----------------------------------------------------------------------


class ApiHttpError(Exception):
    """상태 코드가 2xx 가 아니었다.

    **키를 담지 않는다**(docs/13 3-3 H-5). `urllib` 예외 원문을 그대로
    올리지 않고 status, reason, 응답 본문 발췌만 든다 - 원문에는 요청
    헤더가 섞여 나올 수 있다.
    """

    def __init__(self, status, reason="", body_text="", retry_after=""):
        """
        Args:
            status: HTTP 상태 코드(int 또는 문자열).
            reason: 상태 문구.
            body_text: 응답 본문 발췌. 제공자가 쓴 글이다.
            retry_after: `Retry-After` 헤더 원값. 없으면 빈 문자열.
        """
        self.status = status
        self.reason = str(reason or "")
        self.body_text = str(body_text or "")[:BODY_EXCERPT_MAX]
        self.retry_after = str(retry_after or "")
        super().__init__("HTTP %s %s" % (status, self.reason))


class ApiTransportError(Exception):
    """연결 자체가 실패했다(URLError, ssl, socket.timeout, OSError).

    사유 문자열만 든다. 키도 헤더도 담지 않는다.
    """


# ----------------------------------------------------------------------
# 요청 조립
# ----------------------------------------------------------------------


def _base_headers():
    """두 제공자가 공유하는 헤더. 키는 여기 없다."""
    return {
        "Content-Type": "application/json",
        "Accept": SSE_CONTENT_TYPE,
        # gzip 을 요청하지 않는다(모듈 docstring 의 대가 1).
        "Accept-Encoding": "identity",
        "User-Agent": USER_AGENT,
    }


def normalize_base_url(base_url):
    """base URL 의 꼬리 슬래시를 떼어 경로 결합을 한 가지로 만든다.

    Args:
        base_url: 사용자가 넣은 주소. 빈 값이면 기본값.

    Returns:
        str
    """
    text = str(base_url or "").strip() or OPENAI_BASE_DEFAULT
    return text.rstrip("/")


def build_request(provider, key=None, model="", system="", messages=(),
                  max_tokens=None, base_url=None, tools=None):
    """제공자 하나의 POST 요청 재료를 만든다.

    Anthropic 본문에 넣지 않는 것과 그 이유(전부 공개 문서 근거)
        `temperature`/`top_p`/`top_k`  이 API 버전에서 전 모델 400 이다.
        `thinking:{"type":"disabled"}`·`budget_tokens`  현행 모델에서 400 이다.
        `output_config.effort`  1차 미노출(사용자 결정 D-3). 기본값으로 둔다.
        `fallbacks`  서버측 모델 대체. 끄는 것이 사용자 결정 D-2 다 -
            켜면 사용자가 고른 모델이 아닌 모델이 답하고 그 모델 단가로
            청구된다. 이 제품은 조용한 대체를 규약으로 금지해 왔다.
        `cache_control`  무엇을 안정 접두사로 둘지 정해야 하고 지금 근거가
            없다.

    `thinking.display` 를 `"summarized"` 로 켜는 이유
        기본값이 `"omitted"` 이고, 그러면 `thinking` 블록이 **빈 텍스트로**
        스트리밍된다. 이 독은 생각 영역을 렌더하므로 사용자는 빈 생각 블록
        과 긴 침묵을 본다.

    OpenAI 호환에 `max_tokens` 를 보내지 않는 이유(docs/13 2-2-1)
        본가는 최신 모델에서 `max_completion_tokens` 로 바꿨고 로컬 서버는
        `max_tokens` 를 받는다 `[추측]`. 둘 중 하나를 고르면 반대쪽에서
        400 이다. 필수 필드가 아니므로 **아예 보내지 않는다** - 서버
        기본값이 적용되고 호환 축이 하나 줄어든다. 같은 이유로
        `stream_options`(usage 포함 요청)도 보내지 않는다.

    Args:
        provider: `"api_anthropic"` 또는 `"api_openai"`.
        key: API 키 원문. **이 함수 밖으로 나가지 않는다** - 반환하는
            headers dict 에만 담긴다.
        model: 모델명.
        system: 시스템 프롬프트. 빈 문자열이면 키를 넣지 않는다.
        messages: [{"role":"user"|"assistant","content":str}, ...] 평면 이력.
        max_tokens: Anthropic 필수. OpenAI 호환은 None 으로 두어 안 보낸다.
        base_url: OpenAI 호환 전용.
        tools: **1차에서 무시한다.** 2차(도구 루프)가 쓸 자리를 지금 받아
            두는 것이고(docs/13 8-2 자리 2), 값이 와도 본문에 싣지 않는다.

    Returns:
        tuple: (url, headers dict, body bytes)
    """
    del tools  # 1차는 도구를 싣지 않는다. 자리만 받는다.
    headers = _base_headers()
    flat = [dict(m) for m in (messages or ())]
    if provider == PROVIDER_OPENAI_NAME:
        url = normalize_base_url(base_url) + OPENAI_CHAT_PATH
        if key:
            # 값이 비면 헤더를 **아예 넣지 않는다**. 빈 Bearer 를 보내면
            # 키를 요구하지 않는 서버가 그것을 잘못된 키로 읽을 수 있다.
            headers["Authorization"] = "Bearer " + str(key)
        payload = [{"role": "system", "content": system}] if system else []
        payload.extend(flat)
        body = {"model": str(model or ""), "stream": True,
                "messages": payload}
        return url, headers, json.dumps(body, ensure_ascii=False).encode(
            "utf-8")

    headers["x-api-key"] = str(key or "")
    headers["anthropic-version"] = ANTHROPIC_VERSION
    body = {
        "model": str(model or ""),
        "max_tokens": int(MAX_TOKENS_FALLBACK if max_tokens is None
                          else max_tokens),
        "stream": True,
        "thinking": {"type": "adaptive", "display": "summarized"},
        "messages": flat,
    }
    if system:
        body["system"] = system
    return (ANTHROPIC_URL, headers,
            json.dumps(body, ensure_ascii=False).encode("utf-8"))


def build_key_probe(provider, key=None, base_url=None):
    """0토큰 키 점검용 GET 요청 재료.

    `/v1/models` 는 토큰을 쓰지 않고 401/200 을 준다. 그래서 사용자가
    **과금 없이** 키와 주소와 연결을 확인할 수 있다 - Claude 모드의
    "연결 점검이 모델 턴을 쓰지 않는다" 와 같은 설계 축이다.

    Args:
        provider: 제공자 이름.
        key: API 키 원문. headers 에만 담긴다.
        base_url: OpenAI 호환 전용.

    Returns:
        tuple: (url, headers dict, None)
    """
    headers = _base_headers()
    # GET 이므로 SSE 를 기대하지 않는다. 두 헤더를 JSON 으로 되돌린다.
    headers["Accept"] = "application/json"
    headers.pop("Content-Type", None)
    if provider == PROVIDER_OPENAI_NAME:
        if key:
            headers["Authorization"] = "Bearer " + str(key)
        return normalize_base_url(base_url) + OPENAI_MODELS_PATH, headers, None
    headers["x-api-key"] = str(key or "")
    headers["anthropic-version"] = ANTHROPIC_VERSION
    return ANTHROPIC_MODELS_URL, headers, None


# ----------------------------------------------------------------------
# 전송 (워커 스레드에서만 부른다. docs/13 I-4)
# ----------------------------------------------------------------------


def _header_value(resp, name):
    """응답 헤더 하나를 읽는다. 가짜 응답 객체도 받는다.

    Args:
        resp: 응답 객체. `.headers` 또는 `.getheader` 를 가진다.
        name: 헤더 이름(대소문자 무관).

    Returns:
        str: 없으면 빈 문자열.
    """
    getter = getattr(resp, "getheader", None)
    if callable(getter):
        try:
            return str(getter(name) or "")
        except Exception:  # noqa: BLE001 - 헤더 조회 실패를 "없음" 으로 본다
            return ""
    headers = getattr(resp, "headers", None)
    if headers is None:
        return ""
    try:
        value = headers.get(name)
    except Exception:  # noqa: BLE001
        return ""
    if value is None:
        # dict 로 들어온 가짜 응답. 대소문자를 접어 한 번 더 본다.
        try:
            lower = {str(k).lower(): v for k, v in dict(headers).items()}
        except Exception:  # noqa: BLE001
            return ""
        value = lower.get(str(name).lower())
    return "" if value is None else str(value)


def content_type_of(resp):
    """응답의 content-type 본체(파라미터 제외, 소문자).

    Returns:
        str: 없으면 빈 문자열.
    """
    raw = _header_value(resp, "Content-Type")
    return raw.split(";")[0].strip().lower()


def check_sse_content_type(resp, body_peek=""):
    """응답이 SSE 인가. 아니면 사유 1줄을 돌려준다(docs/13 4-3 규칙 4).

    Args:
        resp: 응답 객체.
        body_peek: 본문 앞부분. 사유에 붙여 사용자가 프록시 페이지를
            알아볼 수 있게 한다.

    Returns:
        tuple: (SSE 인가, 사유 문자열). SSE 면 사유는 빈 문자열이다.
    """
    ctype = content_type_of(resp)
    if ctype == SSE_CONTENT_TYPE:
        return True, ""
    shown = ctype or "(없음)"
    why = NOTICE_NOT_SSE % shown
    peek = str(body_peek or "").strip()[:HTML_EXCERPT_MAX]
    if peek:
        why += " 본문 앞부분: " + peek
    return False, why


def peek_body(resp, limit=HTML_EXCERPT_MAX):
    """응답 본문 앞부분을 읽는다. SSE 가 아닐 때만 쓴다.

    SSE 응답에 이것을 쓰면 **스트림의 머리를 먹는다.** 호출자는
    content-type 이 어긋난 것을 먼저 확인하고 부른다(그때는 어차피 턴을
    오류로 닫으므로 먹어도 된다).

    Args:
        resp: 응답 객체.
        limit: 읽을 바이트 수.

    Returns:
        str: 못 읽으면 빈 문자열.
    """
    return _read_peek_n(resp, int(limit))


def _read_peek_n(resp, limit):
    """`resp.read(limit)` 을 문자열로. 실패는 빈 문자열이다."""
    try:
        raw = resp.read(limit)
    except Exception:  # noqa: BLE001 - 본문이 없는 응답도 있다
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return "" if raw is None else str(raw)


def open_stream(url, headers, body, opener=None, connect_timeout_s=None,
                method=None):
    """요청을 열고 응답 객체를 돌려준다. 2xx 가 아니면 ApiHttpError.

    `urlopen` 의 `timeout` 은 **소켓 타임아웃**이라 연결뿐 아니라 이후의
    모든 읽기에도 걸린다. 그래서 스트림 읽기는 `READ_WAKE_S` 로 다시 짧게
    세워 깨어나며 취소를 확인한다(`iter_sse`).

    Args:
        url: 요청 주소.
        headers: 헤더 dict. 키가 들어 있는 유일한 자리다.
        body: POST 본문 bytes. None 이면 GET 이다.
        opener: 주입점. None 이면 `urllib.request.urlopen`. 하네스가 가짜를
            꽂아 **네트워크 없이** 전 경로를 재는 자리다.
        connect_timeout_s: 연결 상한. None 이면 `CONNECT_TIMEOUT_S`.
        method: HTTP 메서드. None 이면 본문 유무로 정한다.

    Returns:
        응답 객체. `readline()`/`read()`/`close()` 와 헤더 조회를 갖는다.

    Raises:
        ApiHttpError: 2xx 가 아니다.
        ApiTransportError: 연결 자체가 실패했다.
    """
    timeout = CONNECT_TIMEOUT_S if connect_timeout_s is None \
        else float(connect_timeout_s)
    verb = method or ("GET" if body is None else "POST")
    if opener is not None:
        # 주입 경로. 가짜는 (url, headers, body, timeout) 네 인자를 받는다.
        return _open_injected(opener, url, headers, body, timeout, verb)
    request = urllib.request.Request(url, data=body, headers=dict(headers),
                                     method=verb)
    try:
        resp = urllib.request.urlopen(request, timeout=timeout,
                                      context=ssl.create_default_context())
    except urllib.error.HTTPError as exc:
        # 본문을 **읽는다**. 제공자의 `error.message` 가 거기 있고 그것이
        # 사용자에게 유일하게 쓸모 있는 사유다(docs/13 4-3 규칙 2).
        raise _http_error_from(exc) from None
    except (urllib.error.URLError, ssl.SSLError, socket.timeout, OSError) as exc:
        raise ApiTransportError(_transport_reason(exc)) from None
    status = getattr(resp, "status", None)
    if status is None:
        status = getattr(resp, "code", 200)
    if int(status) < 200 or int(status) >= 300:
        raise ApiHttpError(status, _header_value(resp, "Reason"),
                           _read_peek(resp),
                           _header_value(resp, "Retry-After"))
    return resp


def _open_injected(opener, url, headers, body, timeout, verb):
    """주입된 opener 를 부른다. 2xx 검사는 실제 경로와 같게 한다.

    Args:
        opener: callable(url, headers, body, timeout) 또는 그 부분집합.
        url: 요청 주소.
        headers: 헤더 dict.
        body: 본문 bytes 또는 None.
        timeout: 소켓 상한.
        verb: HTTP 메서드.

    Returns:
        응답 객체.

    Raises:
        ApiHttpError, ApiTransportError
    """
    try:
        resp = opener(url, dict(headers), body, timeout)
    except (ApiHttpError, ApiTransportError):
        # 가짜가 이미 우리 예외를 던졌다. 두 번 감싸지 않는다.
        raise
    except urllib.error.HTTPError as exc:
        raise _http_error_from(exc) from None
    except (urllib.error.URLError, ssl.SSLError, socket.timeout, OSError) as exc:
        raise ApiTransportError(_transport_reason(exc)) from None
    del verb
    status = getattr(resp, "status", None)
    if status is None:
        status = getattr(resp, "code", 200)
    if int(status) < 200 or int(status) >= 300:
        raise ApiHttpError(status, getattr(resp, "reason", ""),
                           _read_peek(resp),
                           _header_value(resp, "Retry-After"))
    return resp


def _http_error_from(exc):
    """`urllib` HTTPError 를 우리 예외로 바꾼다. 헤더를 담지 않는다."""
    body = ""
    try:
        raw = exc.read()
        body = raw.decode("utf-8", "replace") if isinstance(raw, bytes) \
            else str(raw)
    except Exception:  # noqa: BLE001 - 본문을 못 읽어도 상태는 전한다
        body = ""
    retry = ""
    try:
        retry = str(exc.headers.get("Retry-After") or "")
    except Exception:  # noqa: BLE001
        retry = ""
    return ApiHttpError(getattr(exc, "code", 0), getattr(exc, "reason", ""),
                        body, retry)


def _transport_reason(exc):
    """전송 예외에서 사유 한 줄만 꺼낸다. 요청 정보를 담지 않는다."""
    reason = getattr(exc, "reason", None)
    if reason is not None:
        return "%s: %s" % (type(exc).__name__, reason)
    return "%s: %s" % (type(exc).__name__, exc)


def _read_peek(resp):
    """오류 응답의 본문 앞부분을 읽는다. 못 읽으면 빈 문자열이다."""
    try:
        raw = resp.read(BODY_EXCERPT_MAX)
    except Exception:  # noqa: BLE001 - 본문 없는 응답도 있다
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return "" if raw is None else str(raw)


def iter_sse(resp, cancel=None, idle_abort_s=None, clock=None,
             resume_reads=True, on_activity=None):
    """SSE 본문을 `data:` 페이로드 문자열로 흘린다.

    규칙 넷(docs/13 2-2)
        (1) `data:` 접두만 본다. `event:` 줄은 버린다 - 페이로드 안에
            `type` 이 있다.
        (2) 빈 줄은 이벤트 경계다. 버린다.
        (3) `cancel` 이 켜지면 즉시 멈춘다. **응답은 호출자가 닫는다.**
        (4) 연속 무음이 `idle_abort_s` 를 넘으면 ApiTransportError.

    이어 읽기와 폴백 (docs/13 4-3 의 `[미측]` 단서)
        깨우기 타임아웃이 **줄 중간**에 터진 뒤 같은 응답에서 읽기를
        이어갈 수 있는가는 측정되지 않았다. `http.client` 의 버퍼드 리더가
        부분 바이트를 유지하므로 이어진다고 보지만 추측이다. 그래서
        `resume_reads=False` 폴백을 명세해 둔다 - 그때는 타임아웃을 오류로
        올리고, 호출자가 단일 긴 타임아웃으로 다시 연다. 하네스 110 H 군이
        둘을 가짜 응답으로 가른다.

    Args:
        resp: 응답 객체. `readline()` 을 갖는다.
        cancel: `is_set()` 을 가진 객체(threading.Event). None 이면 취소가
            없는 재생이다.
        idle_abort_s: 연속 무음 상한. None 이면 `IDLE_ABORT_S`.
        clock: 단조 시각 함수. 하네스가 바꿔 끼운다.
        resume_reads: 깨우기 타임아웃 뒤 이어 읽을 것인가.
        on_activity: 줄을 받을 때마다 부르는 콜백. 무음 시계를 바깥에서도
            보고 싶을 때 쓴다(없으면 안 부른다).

    Yields:
        str: `data:` 뒤의 페이로드 문자열.

    Raises:
        ApiTransportError: 무음 초과 또는 읽기 실패.
    """
    limit = IDLE_ABORT_S if idle_abort_s is None else float(idle_abort_s)
    now = clock or time.monotonic
    last = now()
    while True:
        if cancel is not None and cancel.is_set():
            return
        try:
            raw = resp.readline()
        except socket.timeout:
            # 깨우기 타임아웃. 취소 확인과 무음 누적이 이 자리의 일이다.
            if not resume_reads:
                raise ApiTransportError(NOTICE_IDLE % int(limit)) from None
            if cancel is not None and cancel.is_set():
                return
            if now() - last >= limit:
                raise ApiTransportError(NOTICE_IDLE % int(limit)) from None
            continue
        except (urllib.error.URLError, ssl.SSLError, OSError) as exc:
            raise ApiTransportError(_transport_reason(exc)) from None
        if raw is None or raw == b"" or raw == "":
            # EOF. 종료 신호를 봤는지는 번역기가 안다.
            return
        last = now()
        if on_activity is not None:
            on_activity()
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) \
            else str(raw)
        text = text.rstrip("\r\n")
        if not text:
            continue
        if not text.startswith(SSE_DATA_PREFIX):
            continue
        yield text[len(SSE_DATA_PREFIX):].lstrip()


# ----------------------------------------------------------------------
# 오류 문구
# ----------------------------------------------------------------------


def http_notice(exc):
    """`ApiHttpError` 하나를 사용자 대면 한 줄로(docs/13 5-6 표).

    Args:
        exc: ApiHttpError.

    Returns:
        str: 키 값이 들어가지 않는다.
    """
    try:
        status = int(exc.status)
    except (TypeError, ValueError):
        status = 0
    detail = provider_message(exc.body_text) or exc.reason
    if status == 401:
        return NOTICE_401
    if status == 403:
        return NOTICE_403
    if status == 429:
        return (NOTICE_429_RETRY % exc.retry_after) if exc.retry_after \
            else NOTICE_429
    if status == 400:
        return NOTICE_400 % (detail or "사유 없음")
    if status == 404:
        return NOTICE_404
    if 500 <= status < 600:
        return NOTICE_5XX % ("HTTP %d" % status)
    return NOTICE_HTTP_OTHER % (status or "?", detail or "사유 없음")


def transport_notice(exc):
    """`ApiTransportError` 하나를 사용자 대면 한 줄로.

    무음 초과는 자기 문구를 이미 들고 있으므로 그대로 쓴다 - 두 번 감싸면
    "연결하지 못했습니다: 응답이 끊겼습니다(...)" 가 된다.

    Args:
        exc: ApiTransportError.

    Returns:
        str
    """
    text = str(exc)
    if text.startswith(NOTICE_IDLE.split("(")[0]):
        return text
    return NOTICE_TRANSPORT % text


def provider_message(body_text):
    """제공자 오류 본문에서 사람이 읽을 한 줄만 꺼낸다.

    두 제공자가 모두 `{"error":{"message":...}}` 또는
    `{"error":{"type":...}}` 꼴을 쓴다. JSON 이 아니면 앞부분을 그대로
    발췌한다 - 프록시가 HTML 을 돌려주는 경로가 있다.

    Args:
        body_text: 응답 본문 발췌.

    Returns:
        str: 없으면 빈 문자열.
    """
    text = str(body_text or "").strip()
    if not text:
        return ""
    try:
        body = json.loads(text)
    except (ValueError, TypeError):
        return text[:BODY_EXCERPT_MAX]
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("type") or "")[
                :BODY_EXCERPT_MAX]
        if isinstance(err, str):
            return err[:BODY_EXCERPT_MAX]
        if body.get("message"):
            return str(body["message"])[:BODY_EXCERPT_MAX]
    return text[:BODY_EXCERPT_MAX]


# ----------------------------------------------------------------------
# 번역기 공통부
# ----------------------------------------------------------------------


class _TranslatorBase(object):
    """SSE 페이로드를 내부 공통 이벤트 줄로 접는 공통부(docs/13 4-0).

    상태를 든다 - 메시지 id 고정, 열린 블록 추적, usage 누적, 텍스트 조립.
    그래서 번역기는 **턴 1개에 1개**다. 재사용하면 앞 턴의 버퍼가 섞인다.
    """

    def __init__(self, session_id, user_uuid):
        """
        Args:
            session_id: 우리가 발급한 세션 식별자. 내부 줄에 그대로 실린다.
            user_uuid: 이 턴의 사용자 메시지 uuid. `result` 의
                `user_message_uuids` 에 1건으로 실린다.
        """
        self._sid = str(session_id or "")
        self._uuid = str(user_uuid or "")
        self._mid = ""
        # index -> {"type": str, "parts": list[str]}. 삽입 순서를 쓴다.
        self._blocks = {}
        self._order = []
        self._usage = {}
        self._stop_reason = ""
        self._finished = False
        self._clean = False
        self._error_notice = ""
        # `finish()` 의 멱등성을 **두 스레드 사이에서도** 지키는 락이다.
        # 워커 스레드의 `finally` 와 UI 스레드의 취소 경로가 같은 번역기에
        # 이 함수를 부르고, 검사와 세우기가 원자적이지 않으면 `result` 가
        # 2줄 날 수 있다(docs/13 I-2 가 깨지는 유일한 경로다).
        self._lock = threading.Lock()
        # 세기만 하는 것들. 판정과 진단의 근거다.
        self.counts = {}
        self.notes = []

    # ---- 내부 유틸 -------------------------------------------------

    def _bump(self, key):
        """카운터 하나를 올린다."""
        self.counts[key] = self.counts.get(key, 0) + 1

    def _note(self, tag, detail=""):
        """진단 한 줄. 키 값이 들어가지 않는다."""
        self.notes.append((str(tag), str(detail)[:200]))

    def _wrap(self, inner):
        """SSE 데이터 객체 1개를 내부 `stream_event` 줄로 감싼다.

        `api_message_id` 를 래퍼에 넣는 이유: `protocol.stream_info()` 가
        그 키를 먼저 보고 없으면 `event.message.id` 로 떨어지므로, 래퍼에
        넣는 쪽이 블록 키 `(mid, index)` 를 모든 이벤트에서 같게 만든다.

        Args:
            inner: SSE `data:` 페이로드 객체.

        Returns:
            dict: 내부 줄 1개.
        """
        return {"type": "stream_event", "api_message_id": self._mid,
                "session_id": self._sid, "event": inner}

    def _open_block(self, index, btype):
        """블록 버퍼 하나를 연다. 같은 index 가 두 번 오면 그대로 쓴다."""
        if index not in self._blocks:
            self._blocks[index] = {"type": str(btype or "text"), "parts": []}
            self._order.append(index)
        return self._blocks[index]

    def _append(self, index, text):
        """블록 버퍼에 델타를 누적한다. 없으면 열어 둔다."""
        block = self._blocks.get(index)
        if block is None:
            # start 를 못 본 delta. 상태머신도 같은 상황을 기록하고 넘어간다.
            self._note("delta_without_start", "index=%s" % index)
            block = self._open_block(index, "text")
        if text:
            block["parts"].append(text)

    def _block_payload(self, index):
        """블록 하나를 Anthropic 블록 스키마 1개로.

        Returns:
            dict or None: 모르는 종류면 None(권위 줄을 만들지 않는다).
        """
        block = self._blocks.get(index)
        if block is None:
            return None
        body = "".join(block["parts"])
        if block["type"] == "text":
            return {"type": "text", "text": body}
        if block["type"] == "thinking":
            return {"type": "thinking", "thinking": body}
        return None

    def _authoritative(self, index):
        """블록 하나의 권위 `assistant` 줄. 못 만들면 빈 목록이다.

        **`content_block_stop` 직전에** 넣는다(docs/13 4-0 기준선 2).

        Returns:
            list: 내부 줄 0개 또는 1개.
        """
        payload = self._block_payload(index)
        if payload is None:
            return []
        return [{"type": "assistant",
                 "message": {"id": self._mid, "content": [payload]}}]

    # ---- 공개면 ----------------------------------------------------

    def assistant_text(self):
        """이 턴에 조립된 assistant 텍스트. 이력 보관과 `result` 재료다.

        `thinking` 블록을 건너뛰고 텍스트 블록만 줄바꿈으로 잇는다 -
        `machine.Turn.assistant_text()` 와 같은 규칙이고, 같아야 전사와
        `result.result` 가 어긋나지 않는다.

        Returns:
            str
        """
        parts = []
        for index in self._order:
            block = self._blocks.get(index) or {}
            if block.get("type") != "text":
                continue
            body = "".join(block.get("parts") or ())
            if body:
                parts.append(body)
        return "\n".join(parts)

    def usage(self):
        """토큰 수. **모르는 키는 넣지 않는다.**

        0 을 넣지 않는 이유: 0 은 "안 썼다" 로 읽히고 그것은 거짓이다.
        OpenAI 호환은 `stream_options` 를 안 보내므로 대개 빈 dict 다.

        Returns:
            dict
        """
        return dict(self._usage)

    def stop_reason(self):
        """마지막으로 관측한 stop_reason. 없으면 빈 문자열."""
        return self._stop_reason

    def finished(self):
        """`result` 줄을 이미 만들었는가."""
        return self._finished

    def finish(self, reason=FINISH_NORMAL, error=None):
        """턴을 닫는 `result` 줄 1개. **여러 번 불러도 1번만 만든다.**

        이 멱등성이 docs/13 I-2 의 집행 지점이다. 워커의 `finally` 가 이
        함수를 부르고, 오류 경로도 같은 함수를 부른다 - 둘이 겹쳐도 줄은
        1개여야 한다. 깨지면 `is_busy()` 가 영구 True 가 되고 입력이 영구
        잠긴다(이 제품에 이미 있었던 사고의 모양이다).

        Args:
            reason: `FINISH_NORMAL` 또는 `FINISH_INTERRUPT`. 그 외 문자열은
                진단에만 쓴다.
            error: 사용자 대면 오류 문구 1줄. 주면 오류 종료다.

        Returns:
            list: 내부 줄 0개(이미 닫혔다) 또는 1개.
        """
        with self._lock:
            if self._finished:
                self._bump("finish_again")
                return []
            self._finished = True
        notice = str(error or self._error_notice or "")
        if reason == FINISH_INTERRUPT:
            # 중단 판정 네 조건을 맞춘다(machine._is_interrupted_result).
            # `result` 키를 **넣지 않는다** - 조건 4 가 그것이다.
            event = {"type": "result",
                     "subtype": protocol.RESULT_SUBTYPE_ABORTED,
                     "is_error": True, "session_id": self._sid,
                     "usage": self.usage(),
                     "stop_reason": self._stop_reason,
                     "user_message_uuids": [self._uuid] if self._uuid else []}
            return [event]
        if not notice and not self._clean:
            # 종료 신호 없이 끊긴 스트림. 정상 종료로 적으면 사용자는 빈
            # 답을 보고 아무 사유도 못 읽는다.
            notice = NOTICE_TRUNCATED
        if notice:
            event = {"type": "result",
                     "subtype": protocol.RESULT_SUBTYPE_ABORTED,
                     "is_error": True,
                     # 오류에도 `result` 를 싣는다. 중단과 구별되는 자리가
                     # 이 키의 유무이고(조건 4), 본문이 있어야 사유가 어디로
                     # 가지 않는다.
                     "result": notice,
                     "session_id": self._sid, "usage": self.usage(),
                     "stop_reason": self._stop_reason,
                     "upwise_notice": notice,
                     "user_message_uuids": [self._uuid] if self._uuid else []}
            return [event]
        event = {"type": "result", "subtype": RESULT_SUBTYPE_SUCCESS,
                 "is_error": False, "result": self.assistant_text(),
                 "session_id": self._sid, "usage": self.usage(),
                 "stop_reason": self._stop_reason,
                 "user_message_uuids": [self._uuid] if self._uuid else []}
        # 200 인데 내용이 거절이거나 길이로 잘린 경우. 사유를 한 줄 붙인다.
        # **`total_cost_usd` 는 넣지 않는다** - API 응답에 금액이 없고,
        # 없는 키라서 비용 누계 코드가 아예 돌지 않는다(docs/13 5-4).
        if self._stop_reason == STOP_REFUSAL:
            event["upwise_notice"] = NOTICE_REFUSAL % (
                self._refusal_detail() or STOP_REFUSAL)
        elif self._stop_reason == STOP_MAX_TOKENS:
            event["upwise_notice"] = NOTICE_MAX_TOKENS
        return [event]

    def _refusal_detail(self):
        """거절 분류값. 기본 구현은 없다(제공자별로 다르다)."""
        return ""


# ----------------------------------------------------------------------
# Anthropic 번역기
# ----------------------------------------------------------------------


class AnthropicTranslator(_TranslatorBase):
    """Anthropic SSE 페이로드를 내부 공통 이벤트 줄로 접는다(docs/13 4-1).

    왜 래퍼 한 겹으로 끝나는가
        내부 공통 이벤트 모델이 **이미 Anthropic 와이어 포맷**이다.
        `protocol.stream_info()` 가 분기하는 delta 종류와 `machine._on_stream`
        이 소비하는 이벤트 이름이 Messages API SSE 와 같은 집합이다. Claude
        Code 의 `stream_event` 가 그 SSE 를 한 겹 감싼 것이고 이 플러그인의
        파서는 그 감싼 것을 풀도록 쓰여 있다.
    """

    def __init__(self, session_id, user_uuid):
        """거절 분류값 칸을 하나 더 든다."""
        super().__init__(session_id, user_uuid)
        self._refusal = ""

    def feed(self, payload_text):
        """SSE 데이터 1건을 먹고 내부 줄 0개 이상을 돌려준다.

        예외를 던지지 않는다. 모르는 종류와 깨진 JSON 은 카운터와 진단
        한 줄로 처리한다 - `protocol` 의 규칙 1(미지 이벤트로 예외를 던지지
        않는다)과 같은 축이다.

        Args:
            payload_text: `data:` 뒤의 문자열.

        Returns:
            list[dict]: 내부 줄들.
        """
        try:
            inner = json.loads(payload_text)
        except (ValueError, TypeError):
            self._bump("nonjson")
            self._note("nonjson", str(payload_text)[:120])
            return []
        if not isinstance(inner, dict):
            self._bump("nonobject")
            return []
        etype = str(inner.get("type") or "")
        self._bump("sse/" + (etype or "(none)"))

        if etype == "ping":
            # 내부 줄을 만들지 않는다. 무음 타이머는 `iter_sse` 가 줄을
            # 받은 사실로 이미 갱신했다(연결이 살아 있다는 증거다).
            return []

        if etype == "error":
            err = inner.get("error")
            err = err if isinstance(err, dict) else {}
            detail = str(err.get("message") or err.get("type") or "오류")
            self._error_notice = NOTICE_STREAM_ERROR % detail
            # 스트림 중 오류는 턴을 닫는다. 같은 `finish` 를 지나므로
            # `result` 는 1줄이다.
            return self.finish(error=self._error_notice)

        if etype == "message_start":
            msg = inner.get("message")
            msg = msg if isinstance(msg, dict) else {}
            # **메시지 id 를 여기서 고정한다.** 블록 키의 앞자리이므로
            # 중간에 바뀌면 블록이 쪼개진다.
            self._mid = str(msg.get("id") or self._mid or "")
            self._absorb_usage(msg.get("usage"))
            return [self._wrap(inner)]

        if etype == "content_block_start":
            cb = inner.get("content_block")
            cb = cb if isinstance(cb, dict) else {}
            self._open_block(inner.get("index"), cb.get("type") or "text")
            return [self._wrap(inner)]

        if etype == "content_block_delta":
            delta = inner.get("delta")
            delta = delta if isinstance(delta, dict) else {}
            dtype = str(delta.get("type") or "")
            self._bump("delta/" + (dtype or "(none)"))
            if dtype == "text_delta":
                self._append(inner.get("index"), delta.get("text") or "")
            elif dtype == "thinking_delta":
                self._append(inner.get("index"), delta.get("thinking") or "")
            # `signature_delta` 는 화면에 쓸 것이 없고 `input_json_delta` 는
            # 1차에 오지 않는다(tools 미전송). 와도 조립하지 않는다 -
            # 권위 인자는 assistant 의 tool_use 블록에서 받는 규칙이다.
            return [self._wrap(inner)]

        if etype == "content_block_stop":
            # 권위 줄이 **먼저** 간다(기준선 2).
            out = self._authoritative(inner.get("index"))
            out.append(self._wrap(inner))
            return out

        if etype == "message_delta":
            delta = inner.get("delta")
            delta = delta if isinstance(delta, dict) else {}
            reason = delta.get("stop_reason")
            if isinstance(reason, str) and reason:
                self._stop_reason = reason
            refusal = delta.get("refusal") or delta.get("stop_sequence")
            if isinstance(refusal, str) and refusal:
                self._refusal = refusal
            self._absorb_usage(inner.get("usage"))
            return [self._wrap(inner)]

        if etype == "message_stop":
            # **턴을 닫지 않는다.** 상태머신도 세기만 한다.
            self._clean = True
            return [self._wrap(inner)]

        self._bump("unknown")
        self._note("unknown_sse_type", etype or "(none)")
        return []

    def _absorb_usage(self, usage):
        """usage dict 하나를 누적한다. 모르는 키는 그대로 보관한다.

        키를 추리지 않는 이유: `cache_creation_input_tokens` 처럼 나중에
        쓸 값이 늘어날 수 있고, 모르는 키를 버리면 그때 다시 측정해야 한다.
        """
        if not isinstance(usage, dict):
            return
        for key, value in usage.items():
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            self._usage[str(key)] = value

    def _refusal_detail(self):
        """거절 분류값. 없으면 빈 문자열."""
        return self._refusal


# ----------------------------------------------------------------------
# OpenAI 호환 번역기
# ----------------------------------------------------------------------


class OpenAiTranslator(_TranslatorBase):
    """OpenAI 호환 chunk 를 같은 내부 줄로 접는다(docs/13 4-2).

    Anthropic 과 달리 **블록 경계 이벤트가 없다.** 그래서 번역기가 경계를
    합성한다 - 첫 chunk 에서 `message_start`, 첫 `delta.content` 에서
    `content_block_start`, `finish_reason` 에서 권위 줄 ->
    `content_block_stop` -> `message_delta` -> `message_stop` 이다.
    합성 순서는 Anthropic 쪽과 같게 둔다(기준선 2를 양쪽이 지켜야 한다).
    """

    #: 본문 블록 index. OpenAI 호환은 index 를 주지 않으므로 우리가 정한다.
    TEXT_INDEX = 0
    #: 생각 블록 index(벤더 확장 `reasoning_content`).
    THINKING_INDEX = 1

    def __init__(self, session_id, user_uuid):
        """합성 경계가 몇 번 났는지 함께 든다."""
        super().__init__(session_id, user_uuid)
        self._started = False
        self._open = set()
        self._done = False

    def feed(self, payload_text):
        """chunk 1건(또는 `[DONE]`)을 먹고 내부 줄들을 돌려준다.

        Args:
            payload_text: `data:` 뒤의 문자열.

        Returns:
            list[dict]: 내부 줄들.
        """
        text = str(payload_text or "").strip()
        if text == OPENAI_DONE:
            self._bump("chunk/done")
            self._done = True
            self._clean = True
            out = self._close_blocks()
            out.extend(self.finish())
            return out
        try:
            chunk = json.loads(text)
        except (ValueError, TypeError):
            self._bump("nonjson")
            self._note("nonjson", text[:120])
            return []
        if not isinstance(chunk, dict):
            self._bump("nonobject")
            return []
        self._bump("chunk")
        out = []
        if not self._started:
            # 첫 chunk 의 `id` 를 고정한다. 뒤 chunk 의 id 가 달라도
            # **무시**한다 - 블록 키가 `(mid, index)` 라서 중간에 바뀌면
            # 블록이 쪼개진다 `[추측]`.
            self._mid = str(chunk.get("id") or "") or self._synth_mid()
            self._started = True
            out.append(self._wrap({"type": "message_start",
                                   "message": {"id": self._mid,
                                               "role": "assistant",
                                               "content": []}}))
        self._absorb_usage(chunk.get("usage"))
        choices = chunk.get("choices")
        choices = choices if isinstance(choices, list) else []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            out.extend(self._feed_choice(choice))
        return out

    def _feed_choice(self, choice):
        """choice 1개를 내부 줄들로 바꾼다."""
        out = []
        delta = choice.get("delta")
        delta = delta if isinstance(delta, dict) else {}
        body = delta.get("content")
        if isinstance(body, str) and body:
            out.extend(self._delta_line(self.TEXT_INDEX, "text",
                                        "text_delta", body))
        reason_body = delta.get("reasoning_content")
        if isinstance(reason_body, str) and reason_body:
            # 벤더 확장이다 `[미측]`. 오면 생각 영역으로 가고 없으면 아무
            # 일도 없다.
            out.extend(self._delta_line(self.THINKING_INDEX, "thinking",
                                        "thinking_delta", reason_body))
        # `delta:{"role":"assistant"}` 만 온 chunk 로는 블록을 열지 않는다.
        # 열면 본문 없는 블록이 전사에 생긴다.
        finish = choice.get("finish_reason")
        if isinstance(finish, str) and finish:
            self._bump("finish/" + finish)
            self._stop_reason = OPENAI_FINISH_MAP.get(finish, finish)
            out.extend(self._close_blocks())
            out.append(self._wrap({"type": "message_delta",
                                   "delta": {"stop_reason": self._stop_reason},
                                   "usage": self.usage()}))
            out.append(self._wrap({"type": "message_stop"}))
        return out

    def _delta_line(self, index, btype, delta_type, body):
        """델타 1건. 블록이 아직 없으면 `content_block_start` 를 합성한다."""
        out = []
        if index not in self._open:
            self._open_block(index, btype)
            self._open.add(index)
            out.append(self._wrap({"type": "content_block_start",
                                   "index": index,
                                   "content_block": {"type": btype,
                                                     btype: ""}}))
        self._append(index, body)
        key = "text" if delta_type == "text_delta" else "thinking"
        out.append(self._wrap({"type": "content_block_delta", "index": index,
                               "delta": {"type": delta_type, key: body}}))
        return out

    def _close_blocks(self):
        """열린 블록을 권위 줄 + stop 으로 닫는다. 이미 닫혔으면 빈 목록."""
        out = []
        for index in sorted(self._open):
            out.extend(self._authoritative(index))
            out.append(self._wrap({"type": "content_block_stop",
                                   "index": index}))
        self._open = set()
        return out

    def _synth_mid(self):
        """chunk 에 `id` 가 없을 때 우리가 미는 메시지 id.

        uuid 를 쓰지 않는 이유는 import 를 늘리지 않으려는 것뿐이고, 값의
        유일성은 세션 id 와 턴의 사용자 uuid 로 이미 충분하다.
        """
        return "upwise-%s-%s" % (self._sid[:8] or "nosid",
                                 self._uuid[:8] or "nouuid")

    def _absorb_usage(self, usage):
        """usage dict 하나를 누적한다. 1차에서는 대개 오지 않는다."""
        if not isinstance(usage, dict):
            return
        # 본가 이름(prompt/completion)을 Anthropic 이름으로 사상한다. 두
        # 이름이 섞이면 UI 가 둘 다 읽어야 한다.
        mapping = {"prompt_tokens": "input_tokens",
                   "completion_tokens": "output_tokens"}
        for key, value in usage.items():
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            self._usage[mapping.get(str(key), str(key))] = value
