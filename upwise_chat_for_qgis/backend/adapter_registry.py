"""백엔드 어댑터 레지스트리 - 제2 백엔드가 들어오는 자리.

이 모듈이 있는 이유
    호출자(`process.py`·`machine.py`·`plugin.py`)가 `ClaudeAdapter` 를
    직접 import 하면, 제2 백엔드를 넣을 때 그 셋을 다시 고쳐야 한다.
    레지스트리를 거치면 고칠 곳이 **이 파일의 등록 한 줄**뿐이다.

GPT 모드를 넣는 절차 (docs/7 4-1 "백엔드 추상화 리팩터" 다음 단계)
    1. `adapter_codex.py` 에 `CodexAdapter(adapter.BackendAdapter)` 를 쓴다.
       능력 플래그는 docs/7 3-1 실측대로 - `long_lived=False`(턴마다
       `codex exec` 재spawn + `exec resume`), `partial_deltas=False`
       (item 단위 갱신뿐), `system_prompt_flag=False`(AGENTS.md 우회),
       `plugin_dirs=False`, `skill_bundle=False`.
    2. 이 파일 아래 `_register_builtin()` 에 한 줄 더한다.
    3. 사용자 선택 창구(설정 키 1개)를 `default_name()` 에 물린다.

    **이번 회차에서 2·3 은 하지 않는다.** Codex 실행·스파이크가 별도
    회차이고(docs/7 3-2 미확인 8항목), 구현 없는 등록은 사용자가 고를 수
    있는 빈 백엔드를 만든다.

LLM API 직결 백엔드를 넣는 절차 (0.7.0. docs/13 2-5)
    위 절차 2·3 이 **이 회차에 실행됐다.** 등록되는 것은 Codex 가 아니라
    **다른 종류의 백엔드 2개**(`adapter_api.AnthropicApiAdapter`·
    `OpenAiCompatApiAdapter`)이고, `default_name()` 이 사용자 설정
    (`llmkeys.SETTING_BACKEND`)을 읽는다. 위 금지("구현 없는 등록")는
    지켜진다 - 구현이 같은 회차에 들어왔다.

    Codex 어댑터가 뒤에 들어와도 충돌하지 않는다. 이 레지스트리는
    이름 -> 인스턴스 사전이고 중복 이름이 없다. 위 Codex 절차 문면을
    **지우지 않는다** - 그 회차의 할 일이 그대로 남아 있다.

왜 등록을 import 시점에 하는가
    QGIS 플러그인은 플러그인 적재 때 모듈을 한 번 올리고 그 뒤로는
    같은 모듈 객체를 쓴다. 등록을 함수 호출로 미루면 "누가 먼저 부르는가"
    에 따라 레지스트리가 비는 순간이 생긴다.

설계 정본: docs/7.gpt_mode_backend_design_v1.md 2-10, 4, 4-1
"""

from . import adapter_api, adapter_claude, llmkeys

# 기본 백엔드 이름. 설정이 없거나 모르는 값일 때 접히는 자리다.
#
# **문자열을 바꾸지 않는다** - 사용자 설정에 저장될 값이고, 바꾸면 이미
# 저장해 둔 선택이 조용히 무효가 된다(posture.MODEL_CHOICE_* 와 같은 규약).
DEFAULT_BACKEND_NAME = adapter_claude.ClaudeAdapter.name

# 이름 -> 어댑터 인스턴스. 어댑터는 상태를 들지 않으므로 하나를 공유한다.
_REGISTRY = {}


def register(instance, replace=False):
    """어댑터 하나를 등록한다.

    Args:
        instance: `adapter.BackendAdapter` 구현 인스턴스.
        replace: 같은 이름이 이미 있을 때 덮어쓸지. 기본은 거부다 -
            조용한 덮어쓰기는 "어느 쪽이 도는지 모르는" 상태를 만든다.

    Returns:
        str: 등록한 이름.

    Raises:
        ValueError: 이름이 비었거나, 중복인데 replace 가 False 일 때.
    """
    name = str(getattr(instance, "name", "") or "")
    if not name:
        raise ValueError("adapter has no name: %r" % (instance,))
    if name in _REGISTRY and not replace:
        raise ValueError("adapter already registered: %s" % name)
    _REGISTRY[name] = instance
    return name


def names():
    """등록된 백엔드 이름들. 등록 순서가 아니라 사전 순이다(표시 안정)."""
    return tuple(sorted(_REGISTRY))


def get(name=None):
    """이름으로 어댑터를 꺼낸다.

    모르는 이름은 **기본 백엔드로 접는다.** 예외를 던지지 않는 이유는
    이 값이 사용자 설정에서 오기 때문이다 - 설정 파일에 오타가 있으면
    플러그인이 안 뜨는 것이 아니라 기본 백엔드로 떠야 한다
    (posture.normalize_model_choice 와 같은 관용구).

    Args:
        name: 백엔드 이름. None 이거나 모르는 값이면 기본 백엔드.

    Returns:
        adapter.BackendAdapter
    """
    key = str(name or "") or DEFAULT_BACKEND_NAME
    return _REGISTRY.get(key) or _REGISTRY[DEFAULT_BACKEND_NAME]


def default():
    """기본 백엔드 어댑터. 호출자의 `backend=None` 기본값이 이것이다."""
    return _REGISTRY[DEFAULT_BACKEND_NAME]


def default_name():
    """사용자가 고른 백엔드 이름. 모르는 값은 기본 백엔드로 접힌다.

    0.7.0: 설정(`llmkeys.SETTING_BACKEND`)을 읽는다. 등록된 이름이 아니면
    **기본 백엔드 이름**을 돌려준다 - 사용자가 설정을 손으로 깨뜨려도
    Claude 모드로 떠야 하고, 그 접기 규약이 `get()` 과 같아야 두 창구가
    갈라지지 않는다. 설정을 못 읽는 환경(QGIS 밖)에서는 빈 문자열이
    오므로 그 경로도 같은 분기로 접힌다.

    Returns:
        str: 등록된 백엔드 이름 하나.
    """
    try:
        name = llmkeys.read_backend_name()
    except Exception:  # noqa: BLE001 - 설정 읽기 실패는 기본 백엔드로 접는다
        return DEFAULT_BACKEND_NAME
    key = str(name or "")
    return key if key in _REGISTRY else DEFAULT_BACKEND_NAME


def _register_builtin():
    """패키지에 들어 있는 어댑터를 등록한다.

    등록 순서가 `names()` 의 순서를 정하지 않는다(그 함수는 사전 순이다).
    """
    register(adapter_claude.ClaudeAdapter(), replace=True)
    # 0.7.0 LLM API 직결 2개(docs/13 2-5). Codex 등록 한 줄은 여전히
    # 들어올 자리가 비어 있다.
    register(adapter_api.AnthropicApiAdapter(), replace=True)
    register(adapter_api.OpenAiCompatApiAdapter(), replace=True)


_register_builtin()
