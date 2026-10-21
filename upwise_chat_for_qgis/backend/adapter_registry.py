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

왜 등록을 import 시점에 하는가
    QGIS 플러그인은 플러그인 적재 때 모듈을 한 번 올리고 그 뒤로는
    같은 모듈 객체를 쓴다. 등록을 함수 호출로 미루면 "누가 먼저 부르는가"
    에 따라 레지스트리가 비는 순간이 생긴다.

설계 정본: docs/7.gpt_mode_backend_design_v1.md 2-10, 4, 4-1
"""

from . import adapter_claude

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
    """기본 백엔드 이름.

    GPT 모드가 들어오면 여기서 사용자 설정(QgsSettings 키 1개)을 읽어
    `normalize` 한 값을 돌려주게 된다. 지금은 상수다 - 고를 것이 하나뿐인
    설정 UI 를 먼저 만들면 사용자가 "되는데 안 되는" 선택지를 본다.
    """
    return DEFAULT_BACKEND_NAME


def _register_builtin():
    """패키지에 들어 있는 어댑터를 등록한다.

    GPT 모드의 등록 한 줄이 들어올 자리다(모듈 docstring 절차 2).
    """
    register(adapter_claude.ClaudeAdapter(), replace=True)


_register_builtin()
