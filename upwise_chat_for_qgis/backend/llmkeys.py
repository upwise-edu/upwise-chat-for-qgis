"""LLM API 키/모델/base URL 설정 선언 (docs/13 2-1, 3-1, 3-2).

이 모듈이 하는 것과 하지 않는 것
    하는 것은 **선언**이다 - 설정 경로 7개, 칸 정의, 검증 규칙, 기본값.
    하지 않는 것은 **값 보유**다. 읽기와 쓰기는 `keystore.read_value`/
    `save_field`/`delete_value` 를 그대로 지나가고, 이 모듈은 어떤 값도
    속성이나 모듈 전역에 담아 두지 않는다(docs/13 3-3 H-1).

    키 **값**을 만지는 모듈이 하나라는 규약(`keystore` 모듈 docstring)이
    그래서 유지된다. `keystore.py` 는 이번 회차에 고치지 않았다 - 필요한
    것이 이미 다 있다(`save_field` 가 칸별 `key_re` 로 검증한다).

접두사를 `upwise_chat/keys/` 와 다르게 둔 이유와 한계
    수집 키 접두사(`posture.COLLECT_KEY_PREFIX`)를 순회하는 코드가 LLM 키를
    절대 집지 않게 `upwise_chat/llm/` 아래로 뺀다. **격리가 아니다** -
    수집 서버는 QGIS3.ini 전체 경로를 받아 섹션을 순회하므로 INI 안의 어떤
    값도 읽을 수 있는 자리에 있다(`collect_server.read_setting`). 접두사
    분리는 우리 코드의 실수 경로를 줄이는 것이고 자식의 권한을 줄이지
    않는다. 이 성질은 README 5(함정)에 등재돼 있다.

검증 규칙이 접두사 패턴을 쓰지 않는 이유 (docs/13 3-2)
    `sk-ant-` 류 접두사 검사를 넣지 않는다. 키 모양은 발급 주체가 바꿀 수
    있고 우리는 그것을 검증할 수 없다. 접두사로 거르면 **유효한 미래 키를
    저장 거부**하는 쪽으로 틀린다 - 틀릴 때 안전한 방향은 통과시키고
    제공자가 401 로 거절하게 두는 쪽이다. 막는 것은 붙여넣기 사고(공백,
    개행, 따옴표, 빈 값, 너무 짧은 값)뿐이다.

설계 정본: docs/13.api_key_backend_design_v1.md 2-1, 3-1, 3-2, 3-3
"""

import re

from . import keystore

# ----------------------------------------------------------------------
# 설정 경로 (docs/13 3-1 표. 문자열을 바꾸지 않는다)
# ----------------------------------------------------------------------
#
# **이 일곱 문자열은 사용자 설정에 저장되는 자리다.** 바꾸면 이미 넣어 둔
# 키와 모델 선택이 조용히 무효가 된다(`adapter_registry.DEFAULT_BACKEND_NAME`
# 과 `posture.MODEL_CHOICE_*` 의 같은 규약). 하네스 110 F3 이 이 표와 설계
# 3-1 표의 글자 일치를 판정한다.

#: 어느 백엔드로 뜰 것인가. "claude" / "api_anthropic" / "api_openai".
SETTING_BACKEND = "upwise_chat/backend"

#: Anthropic API 키 **값**.
SETTING_KEY_ANTHROPIC = "upwise_chat/llm/keys/anthropic"

#: OpenAI 호환 API 키 **값**. 비어 있어도 된다(로컬 서버).
SETTING_KEY_OPENAI = "upwise_chat/llm/keys/openai"

#: Anthropic 모델명.
SETTING_MODEL_ANTHROPIC = "upwise_chat/llm/model/anthropic"

#: OpenAI 호환 모델명. 기본값이 없다 - 서버마다 다르므로 필수 입력이다.
SETTING_MODEL_OPENAI = "upwise_chat/llm/model/openai"

#: OpenAI 호환 base URL.
SETTING_BASE_URL_OPENAI = "upwise_chat/llm/base_url/openai"

#: Anthropic 토큰 상한. 상한이지 지출 약정이 아니다.
SETTING_MAX_TOKENS = "upwise_chat/llm/max_tokens"

#: 설정 경로 전체. 선언 순서가 설계 3-1 표의 행 순서다. 하네스와
#: `scripts/25_keyleak_grep.py` 가 이 목록을 읽는다 - 경로를 리터럴로
#: 다시 적는 자리를 만들지 않는다.
LLM_SETTINGS = (
    SETTING_BACKEND,
    SETTING_KEY_ANTHROPIC,
    SETTING_KEY_OPENAI,
    SETTING_MODEL_ANTHROPIC,
    SETTING_MODEL_OPENAI,
    SETTING_BASE_URL_OPENAI,
    SETTING_MAX_TOKENS,
)

#: 그 가운데 **값이 비밀인 것**. 레다크션 집합과 키 유출 검사의 needle 이
#: 이 둘이다. 나머지 다섯은 비밀이 아니다 - 모델명을 needle 로 넣으면
#: 모델명을 적은 모든 줄이 "유출" 로 잡힌다(검사망이 거짓 적발로 죽는다).
LLM_SECRET_SETTINGS = (SETTING_KEY_ANTHROPIC, SETTING_KEY_OPENAI)

# ----------------------------------------------------------------------
# 제공자 이름 (어댑터 `name` 과 같은 문자열이어야 한다)
# ----------------------------------------------------------------------

PROVIDER_ANTHROPIC = "api_anthropic"
PROVIDER_OPENAI = "api_openai"

#: 등록 순서. 패널 행 순서가 이것이다.
PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI)

#: Claude CLI 백엔드 이름. `adapter_claude.ClaudeAdapter.name` 과 같은 값을
#: 여기서 다시 적지 않으려고 import 로 받는다.
BACKEND_CLAUDE = "claude"

# ----------------------------------------------------------------------
# 검증식과 기본값
# ----------------------------------------------------------------------

# 공백도 제어문자도 없는 출력 가능 ASCII 8-512자(docs/13 3-2).
#
# 전역 `keystore.KEY_RE`(영숫자/밑줄/하이픈 8-128자)를 **우회한다**. 우회가
# 필요한 이유는 둘이다. (1) OpenAI 프로젝트 키가 128자를 넘길 수 있다
# `[추측]`. (2) base64 계열 문자(`+` `/` `=`)와 점이 들어갈 수 있다.
# 넓히는 쪽이지만 **공백/개행/따옴표/제어문자는 그대로 막는다** - 막으려는
# 것이 붙여넣기 사고뿐이기 때문이다.
LLM_KEY_RE = r"^[\x21-\x7e]{8,512}$"

# 모델명. 공백 없는 출력 가능 ASCII 1-200자. 모델명은 비밀이 아니고 길이
# 하한을 둘 근거도 없다(`gpt-5` 처럼 짧은 이름이 있다). 콜론과 점을 허용
# 하는 이유는 로컬 서버 이름(`llama3.1:8b`)이 그렇게 생겼기 때문이다.
MODEL_RE = r"^[\x21-\x7e]{1,200}$"

#: Anthropic 모델 기본값. 사용자가 비워 두면 이 값으로 요청한다.
MODEL_DEFAULT_ANTHROPIC = "claude-opus-5-5"

#: OpenAI 호환 base URL 기본값.
BASE_URL_DEFAULT_OPENAI = "https://api.openai.com/v1"

#: Anthropic 토큰 상한 기본값. 스트리밍 권고값이다. **상한이고 약정이
#: 아니다** - 모델이 이만큼 쓰는 것이 아니라 이보다 길면 잘린다.
MAX_TOKENS_DEFAULT = 64000

#: 토큰 상한의 허용 범위. 하한 1 은 "0 을 보내면 400" 이기 때문이고,
#: 상한은 모델 상한을 우리가 모르므로 넉넉히 둔다 - 제공자가 400 으로
#: 거절하는 것이 우리가 추측해 거절하는 것보다 낫다.
MAX_TOKENS_MIN = 1
MAX_TOKENS_MAX = 1000000

# 거절 사유 문구. 값을 넣지 않는다(docs/13 3-3 H-3).
KEY_HINT = "공백과 따옴표 없이 8-512자로 넣으세요."
MODEL_REASON = "모델명을 공백 없이 넣으세요."
BASE_URL_REASON = "http:// 또는 https:// 로 시작하는 주소만 저장합니다."
MAX_TOKENS_REASON = "토큰 상한은 %d-%d 사이 정수로 넣으세요." % (MAX_TOKENS_MIN,
                                                        MAX_TOKENS_MAX)

_MODEL_RE = re.compile(MODEL_RE)


# ----------------------------------------------------------------------
# 칸 정의 (keystore.save_field 에 넘기는 모양)
# ----------------------------------------------------------------------


def key_field(provider):
    """제공자 하나의 **키 칸** 정의. `keystore.save_field` 가 읽는 모양이다.

    `key_form` 을 넣지 않는다. 그 규칙(`"decoding"`, 퍼센트 인코딩 거부)은
    공공 API 포털의 Encoding/Decoding 키 구분 때문이고 LLM 키에는 그 구분이
    없다(docs/13 3-2).

    Args:
        provider: `PROVIDER_ANTHROPIC` 또는 `PROVIDER_OPENAI`.

    Returns:
        dict: name/label/setting/required/key_re/form/hint.
    """
    if provider == PROVIDER_OPENAI:
        # 로컬 서버(Ollama, LM Studio)는 키를 요구하지 않는다. 값이 비면
        # Authorization 헤더를 아예 넣지 않는다(docs/13 3-2).
        return {"name": "openai_key", "label": "API 키(선택)",
                "setting": SETTING_KEY_OPENAI, "required": False,
                "key_re": LLM_KEY_RE, "form": "", "hint": KEY_HINT}
    return {"name": "anthropic_key", "label": "API 키",
            "setting": SETTING_KEY_ANTHROPIC, "required": True,
            "key_re": LLM_KEY_RE, "form": "", "hint": KEY_HINT}


def model_field(provider):
    """제공자 하나의 **모델명 칸** 정의.

    Args:
        provider: 제공자 이름.

    Returns:
        dict: `keystore.save_field` 가 읽는 모양.
    """
    if provider == PROVIDER_OPENAI:
        return {"name": "openai_model", "label": "모델명",
                "setting": SETTING_MODEL_OPENAI, "required": True,
                "key_re": MODEL_RE, "form": "", "hint": MODEL_REASON}
    return {"name": "anthropic_model", "label": "모델명",
            "setting": SETTING_MODEL_ANTHROPIC, "required": False,
            "key_re": MODEL_RE, "form": "", "hint": MODEL_REASON}


def base_url_field():
    """OpenAI 호환 base URL 칸 정의. 제공자가 하나뿐이라 인자가 없다."""
    return {"name": "openai_base_url", "label": "base URL",
            "setting": SETTING_BASE_URL_OPENAI, "required": False,
            # URL 은 아래 `validate_base_url` 이 먼저 보고 통과한 것만
            # 내려오므로 칸 식은 넓게 둔다(이중 검사가 되지 않게).
            "key_re": r"^[\x21-\x7e]{8,512}$", "form": "",
            "hint": BASE_URL_REASON}


def max_tokens_field():
    """Anthropic 토큰 상한 칸 정의."""
    return {"name": "max_tokens", "label": "토큰 상한",
            "setting": SETTING_MAX_TOKENS, "required": False,
            "key_re": r"^[0-9]{1,7}$", "form": "", "hint": MAX_TOKENS_REASON}


def backend_field():
    """백엔드 선택 칸 정의. 라디오 3개가 이 칸 하나에 쓴다."""
    return {"name": "backend", "label": "백엔드",
            "setting": SETTING_BACKEND, "required": False,
            "key_re": r"^[a-z_]{4,32}$", "form": "", "hint": ""}


# ----------------------------------------------------------------------
# 읽기 (전부 keystore 경유. 값을 보관하지 않는다)
# ----------------------------------------------------------------------


def read_backend_name(settings=None):
    """저장된 백엔드 이름. 없으면 빈 문자열이다.

    `normalize` 하지 않는다 - 모르는 값을 기본 백엔드로 접는 것은
    `adapter_registry.get()` 의 규약이고, 그 판정을 두 군데 두지 않는다.

    Args:
        settings: QSettings 호환 객체. None 이면 QgsSettings.

    Returns:
        str
    """
    return keystore.read_value(SETTING_BACKEND, settings=settings)


def read_key(provider, settings=None):
    """제공자 하나의 키 **값**.

    **반환값은 HTTP 요청 헤더와 레다크터에만 들어간다**(docs/13 3-3 H-4).
    로그, 진단, 요약, 예외 문구, UI 문구에 넣지 않는다.

    Args:
        provider: 제공자 이름.
        settings: QSettings 호환 객체.

    Returns:
        str: 없으면 빈 문자열.
    """
    return keystore.read_value(key_field(provider)["setting"],
                               settings=settings)


def read_model(provider, settings=None):
    """제공자 하나의 모델명. Anthropic 은 기본값으로 떨어진다.

    OpenAI 호환은 기본값이 **없다** - 서버마다 이름이 다르므로 추측하면
    404 가 나고 사용자는 사유를 모른다(docs/13 3-1).

    Args:
        provider: 제공자 이름.
        settings: QSettings 호환 객체.

    Returns:
        str: 설정값, 없으면 Anthropic 은 기본값, OpenAI 호환은 "".
    """
    value = keystore.read_value(model_field(provider)["setting"],
                                settings=settings).strip()
    if value:
        return value
    return "" if provider == PROVIDER_OPENAI else MODEL_DEFAULT_ANTHROPIC


def read_base_url(settings=None):
    """OpenAI 호환 base URL. 없으면 기본값이다."""
    value = keystore.read_value(SETTING_BASE_URL_OPENAI,
                                settings=settings).strip()
    return value or BASE_URL_DEFAULT_OPENAI


def read_max_tokens(settings=None):
    """Anthropic 토큰 상한. 깨진 값은 기본값으로 떨어진다.

    깨진 값에서 예외를 던지지 않는 이유는 이 값이 사용자 설정에서 오기
    때문이다 - 설정 오타로 전송이 막히는 것이 아니라 기본값으로 떠야 한다
    (`adapter_registry.get()` 과 같은 관용구).

    Returns:
        int
    """
    raw = keystore.read_value(SETTING_MAX_TOKENS, settings=settings).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return MAX_TOKENS_DEFAULT
    if value < MAX_TOKENS_MIN or value > MAX_TOKENS_MAX:
        return MAX_TOKENS_DEFAULT
    return value


# ----------------------------------------------------------------------
# 검증과 저장
# ----------------------------------------------------------------------


def validate_key(provider, value):
    """키 하나의 저장 전 검증. 사유에 값을 넣지 않는다.

    Args:
        provider: 제공자 이름.
        value: 사용자가 넣은 값.

    Returns:
        tuple: (통과 여부, 사유 문자열, 다듬은 값)
    """
    return keystore.validate_field_value(key_field(provider), value)


def save_key(provider, value, settings=None):
    """키 하나를 저장한다. 검증은 `keystore.save_field` 가 한다.

    Returns:
        tuple: (성공 여부, 사유 문자열). 사유에 **키 값을 넣지 않는다.**
    """
    return keystore.save_field(key_field(provider), value, settings=settings)


def delete_key(provider, settings=None):
    """키 하나를 지운다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    return keystore.delete_value(key_field(provider)["setting"],
                                 settings=settings)


def validate_model(value):
    """모델명 검증. 빈 값과 공백 섞인 값을 막는다.

    Returns:
        tuple: (통과 여부, 사유 문자열, 다듬은 값)
    """
    text = ("" if value is None else str(value)).strip()
    if not text or not _MODEL_RE.match(text):
        return False, MODEL_REASON, text
    return True, "", text


def save_model(provider, value, settings=None):
    """모델명을 저장한다.

    자체 검증을 먼저 하는 이유는 사유 문면이다 - `keystore.save_field` 의
    거절 사유는 "키 형식이..." 로 시작하고, 모델명 칸에서 그 문면은 틀렸다.
    저장 자체는 그대로 `keystore` 를 지난다(H-1).

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    ok, why, text = validate_model(value)
    if not ok:
        return False, why
    return keystore.save_field(model_field(provider), text,
                               settings=settings)


def delete_model(provider, settings=None):
    """모델명을 지운다. Anthropic 은 기본값으로 돌아간다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    return keystore.delete_value(model_field(provider)["setting"],
                                 settings=settings)


def validate_base_url(url):
    """base URL 검증. `keystore.save_endpoint_override` 와 같은 규칙이다.

    http(s) 가 아닌 주소를 막는 이유는 **키가 그 주소로 전송된다**는
    사실이다(docs/13 3-2 의 고지 1줄). 상대 경로나 file:// 로는 TLS 도
    프록시 규칙도 적용되지 않는다.

    Returns:
        tuple: (통과 여부, 사유 문자열, 다듬은 값)
    """
    text = ("" if url is None else str(url)).strip()
    if not text:
        return False, BASE_URL_REASON, text
    if not (text.startswith("http://") or text.startswith("https://")):
        return False, BASE_URL_REASON, text
    if len(text) < 8 or len(text) > 512 or re.search(r"\s", text):
        return False, BASE_URL_REASON, text
    return True, "", text


def save_base_url(url, settings=None):
    """base URL 을 저장한다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    ok, why, text = validate_base_url(url)
    if not ok:
        return False, why
    return keystore.save_field(base_url_field(), text, settings=settings)


def delete_base_url(settings=None):
    """base URL 을 지운다. 기본값으로 돌아간다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    return keystore.delete_value(SETTING_BASE_URL_OPENAI, settings=settings)


def validate_max_tokens(value):
    """토큰 상한 검증.

    Returns:
        tuple: (통과 여부, 사유 문자열, 다듬은 값 문자열)
    """
    text = ("" if value is None else str(value)).strip()
    try:
        number = int(text)
    except (TypeError, ValueError):
        return False, MAX_TOKENS_REASON, text
    if number < MAX_TOKENS_MIN or number > MAX_TOKENS_MAX:
        return False, MAX_TOKENS_REASON, text
    return True, "", str(number)


def save_max_tokens(value, settings=None):
    """토큰 상한을 저장한다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    ok, why, text = validate_max_tokens(value)
    if not ok:
        return False, why
    return keystore.save_field(max_tokens_field(), text, settings=settings)


def save_backend_name(name, settings=None):
    """백엔드 선택을 저장한다.

    적용 시점은 **다음 새 대화부터**다. 모델 선택이 이미 그 규약이고
    (`plugin._make_spec` 의 "다음 스폰부터 적용") 턴이 도는 중에 백엔드를
    바꿔 끼우면 이력과 전사가 섞인다(docs/13 I-5).

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    return keystore.save_field(backend_field(), name, settings=settings)


# ----------------------------------------------------------------------
# 상태 조회 (값을 돌려주지 않는 것들)
# ----------------------------------------------------------------------


def key_present(provider, settings=None):
    """키가 설정돼 있는가. **값을 보지 않고 길이만 본다**(docs/13 2-3).

    Returns:
        bool
    """
    return bool(read_key(provider, settings=settings))


def is_configured(provider, settings=None):
    """그 제공자로 전송할 준비가 됐는가(키와 모델).

    OpenAI 호환은 키가 **선택**이다(로컬 서버). 모델명은 둘 다 필수다 -
    없으면 요청 본문의 `model` 이 빈 문자열이 되고 그것은 400 이다.

    Args:
        provider: 제공자 이름.
        settings: QSettings 호환 객체.

    Returns:
        tuple: (준비됐는가, 사유 문자열). 사유에 값을 넣지 않는다.
    """
    model = read_model(provider, settings=settings)
    if not model:
        return False, "model_missing"
    if provider == PROVIDER_OPENAI:
        if not read_base_url(settings=settings):
            return False, "base_url_missing"
        return True, "ok"
    if not key_present(provider, settings=settings):
        return False, "llm_key_missing"
    return True, "ok"


def secrets(settings=None):
    """레다크션에 넘길 LLM 키 값들.

    **이 함수의 반환값은 레다크터에만 들어간다**(`keystore.secrets` 와 같은
    계약). 호출자는 `keystore.secrets()` 와 **합집합**으로 묶어야 한다 -
    한쪽만 넣으면 나머지 키가 레다크션 집합에서 빠지고, 전사/내보내기/
    클립보드/녹화/진단에서 안 지워진다(docs/13 3-3 H-2).

    Returns:
        tuple: 저장된 키 값들(중복 제거).
    """
    out = []
    for provider in PROVIDERS:
        value = read_key(provider, settings=settings)
        if value and value not in out:
            out.append(value)
    return tuple(out)


def summary(settings=None):
    """진단 로그와 하네스가 읽는 요약. **값도 길이도 들어가지 않는다.**

    `keystore.mask()` 를 쓰지 않는 이유: 그 함수는 자릿수를 보여 준다.
    자릿수는 화면에서는 쓸모가 있지만 로그에 남을 이유가 없다
    (docs/13 3-3 H-3).

    Returns:
        dict: 불리언과 칸 이름만.
    """
    out = {"backend": read_backend_name(settings=settings), "keys": {},
           "models": {}, "ready": {}}
    for provider in PROVIDERS:
        out["keys"][provider] = key_present(provider, settings=settings)
        out["models"][provider] = bool(read_model(provider,
                                                  settings=settings))
        ok, why = is_configured(provider, settings=settings)
        out["ready"][provider] = {"ok": ok, "why": why}
    out["base_url_set"] = bool(
        keystore.read_value(SETTING_BASE_URL_OPENAI, settings=settings))
    out["max_tokens_set"] = bool(
        keystore.read_value(SETTING_MAX_TOKENS, settings=settings))
    return out
