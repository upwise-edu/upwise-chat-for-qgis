"""LLM API 직결 어댑터 2개 (docs/13 2-3).

무엇을 하는가
    `adapter.BackendAdapter` 계약을 **HTTP 직결**에 묶는다. 어댑터 2개가
    들어온다 - Anthropic Messages API 와 OpenAI 호환 범용(base URL + 키 +
    모델명 입력식)이다. 공통부는 전송과 번역 골격이고 제공자별로 다른 것은
    요청 조립과 SSE 번역 두 군데뿐이다.

계약의 세 묶음을 어떻게 메우는가 (docs/13 1-1 실측)
    프로토콜 묶음(13개)  `protocol.*` **그대로 위임**한다. `adapter_claude`
        와 같은 코드다 - 내부 공통 이벤트 모델이 이미 Anthropic 와이어
        포맷이라 새 어휘를 발명할 이유가 없다.
    탐지 묶음(6개)  무해한 기본값. "실행 파일 없음" 이 **정상**이므로
        `find_executable` 은 `MISSING` 을 돌려주지 않는다 - 돌려주면
        전제조건 바가 "실행 파일 없음" 으로 입력을 막는다.
    argv 묶음(3개)  빈 리스트와 빈 문자열. `write_mcp_config` 는 **파일을
        쓰지 않는다**.

`turn_ends_on_result=True` 가 거짓말이 아닌 이유
    그 플래그의 문서상 뜻은 "턴이 종료 이벤트 하나로 닫히는가. False 면
    **프로세스 종료**가 턴 종료다" 다(`adapter.py` 의 그 속성 주석).
    API 모드에는 프로세스가 없고 번역기가 synthetic `result` 줄을 만들어
    닫는다. 따라서 참이다. **나중에 누가 반드시 의심하므로** 이 단락을
    여기에 둔다.

왜 `apiclient` 를 모듈 수준에서 import 하지 않는가
    `apiclient` 가 `machine` 의 상수 두 개를 읽어 쓰고(사본 금지),
    `machine` 은 `adapter_registry` 를 import 하며 레지스트리가 이 모듈을
    import 한다. 모듈 수준에서 받으면 그 사슬이 닫힌다. `adapter_claude`
    가 `detect` 를 함수 안에서 받는 것과 같은 처방이다.

1차 범위 (사용자 결정 U-2)
    **채팅 전용이다.** 요청에 `tools` 를 싣지 않으므로 포스처, 게이트, MCP,
    스킬 번들, 승인 바가 전부 비적용이 된다. 2차(도구 루프)를 막지 않는
    인터페이스 여지만 남긴다.

설계 정본: docs/13.api_key_backend_design_v1.md 2-3, 4-1-1, 5-1, 8-2
"""

import uuid as uuid_mod

from . import adapter, llmkeys, posture, protocol

# ----------------------------------------------------------------------
# 능력 플래그 (docs/13 2-3)
# ----------------------------------------------------------------------
#
# **플래그를 추가하지 않았다.** 12개로 이 백엔드를 다 서술할 수 있다는 것이
# "계약을 확장하지 않는다" 는 결정의 근거 가운데 하나다.
API_CAPABILITIES = adapter.BackendCapabilities(
    # 프로세스가 없다. 턴 1개 = HTTP 교환 1회다.
    long_lived=False,
    # SSE 가 토큰 단위 델타를 준다. Codex 와 반대다.
    partial_deltas=True,
    # 우리가 uuid4 를 정한다(로그북 파일명이 그 값에 걸려 있다).
    preassigned_session_id=True,
    # 서버에 세션이 없다. API 는 무상태이고 이력은 플러그인이 든다.
    resume=False,
    # `system` 필드가 1회성 주입이다.
    system_prompt_flag=True,
    plugin_dirs=False,
    skill_bundle=False,
    # 1차는 tools 를 싣지 않는다.
    tool_allowlist_flags=False,
    per_call_mcp_config=False,
    # "키가 있는가" 로 재해석한다.
    login_guard=True,
    # 우리 큐를 만들지 않는다(1차). 턴 중 전송은 거부된다.
    queue_lifecycle=False,
    # 우리가 스트림을 끊고 영수증도 우리가 만든다.
    control_interrupt=True,
)

# 제어 요청 subtype. Claude CLI 와 **같은 문자열**을 쓴다 - 상태머신의 중단
# 판정이 어댑터의 이 값으로 우리 요청을 짝짓고, 값이 무엇이든 그 짝짓기만
# 성립하면 된다. 같게 두면 두 모드의 진단 로그가 같은 어휘를 쓴다.
API_CONTROL_INTERRUPT = "interrupt"

# 상시 고지 1줄(docs/13 5-1). 독이 읽어 머리말 안내 영역에 넣는다. 문면을
# 어댑터가 쥐는 이유는 백엔드 이름 템플릿화와 같은 축이다 - 독에 백엔드별
# 문면을 쌓지 않는다.
CHAT_ONLY_NOTICE = ("이 모드는 채팅 전용입니다. QGIS 를 조작하거나 데이터를 "
                    "수집할 수 없습니다.")

# 권한 배지 문면(docs/13 5-2). "권한 미확인" 은 고장처럼 읽히므로 API
# 모드에서는 사실을 그대로 적는다.
CHAT_ONLY_BADGE = "채팅 전용 . 도구 0"

# 전송 전 점검이 실패했을 때의 사유(docs/13 3-4). 독이 차단 문구로 읽는다.
GATE_KEY_MISSING_REASON = "API 키를 설정해야 보낼 수 있습니다."
GATE_MODEL_MISSING_REASON = "모델명을 설정해야 보낼 수 있습니다."
GATE_BASE_URL_MISSING_REASON = "base URL 을 설정해야 보낼 수 있습니다."

# API 모드 시스템 프롬프트(사용자 결정 D-5, 2026-11-19. 초안 그대로).
#
# `posture.DOCK_PREAMBLE` 을 **쓰지 않는다.** 그 문면은 QGIS 도구 규칙
# (체크포인트, MCP 1개씩, 스킬 마커, 코드 실행 금지)이고 도구가 없는 모드에서
# 는 거짓 지시다. 세 줄로 줄인 것이 이 모드의 사실 전부다.
#
# 1차 구현에는 이 세 줄 **앞에** 틀 문장("너는 QGIS 안의 UPWISE Chat 독에서
# 실행된다. 다음 세 가지를 지켜라.")이 하나 더 있었다. 초안에 없는 줄이라
# D-5("초안 3줄 그대로")와 문면이 어긋났고(V57 판정 5-b) 지웠다. 역할 문맥은
# 2항이 그대로 말한다 - "이 창은 QGIS 안의 채팅이고 ...".
API_SYSTEM_PROMPT = (
    "1. 사용자에게는 한국어로 답한다.\n"
    "2. 이 창은 QGIS 안의 채팅이고 지도와 파일을 조작할 수 없다.\n"
    "3. 사용자가 QGIS 조작을 요청하면 그 사실을 먼저 알린다.\n"
)

#: 채팅 전용 포스처. 세 목록이 모두 비어 있다 - 도구가 0개이면 포스처 R/C/W
#: 의 차이가 소멸한다.
CHAT_POSTURE_NAME = "CHAT"
CHAT_POSTURE = posture.PostureSpec(CHAT_POSTURE_NAME, (), (), ())


class ApiAdapterBase(adapter.BackendAdapter):
    """HTTP 직결 어댑터의 공통부.

    상태를 들지 않는다. 그래서 레지스트리가 인스턴스 하나를 공유한다
    (`adapter_claude.ClaudeAdapter` 와 같은 계약). 설정은 **읽을 때마다**
    `llmkeys` 를 지나가므로, 사용자가 패널에서 바꾼 값이 다음 호출에 바로
    반영된다.
    """

    #: 제공자 식별자. 하위 클래스가 `name` 과 같은 값으로 둔다.
    provider = ""

    #: 상시 고지 문구. 독이 읽는다(docs/13 5-1).
    chat_only_notice = CHAT_ONLY_NOTICE

    #: 권한 배지 문면. 독이 읽는다(docs/13 5-2).
    chat_only_badge = CHAT_ONLY_BADGE

    #: 시스템 프롬프트. 요청 본문의 `system` 에 들어간다.
    system_prompt = API_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # 능력
    # ------------------------------------------------------------------

    @property
    def capabilities(self):
        """API_CAPABILITIES 하나를 돌려준다."""
        return API_CAPABILITIES

    # ------------------------------------------------------------------
    # 탐지 - 무해한 기본값 (docs/13 2-3 위임표)
    # ------------------------------------------------------------------

    known_executable_paths = ()
    executable_fallback_name = ""
    #: 자식 환경이 없다. 환경변수 경고도 제거 규칙도 성립하지 않는다.
    api_key_env = ""
    env_strip_exact = ()
    env_strip_prefixes = ()

    def find_executable(self, configured=None):
        """실행 파일이 없는 것이 **정상**이다. 그래서 FOUND 를 돌려준다.

        `MISSING` 을 돌려주면 전제조건 바가 "실행 파일 없음" 으로 입력을
        막는다(docs/13 2-3). 전송 가능 여부는 키와 모델이 가르고, 그 판정은
        `ApiBackend.start()` 의 전송 전 점검이 한다.

        Returns:
            tuple: (상태, "", 근거)
        """
        del configured
        from . import detect

        return detect.FOUND, "", "api backend: no executable"

    def verify_executable(self, exe, runner, timeout_s=90.0):
        """`runner` 를 부르지 않는다. 띄울 프로세스가 없다.

        Returns:
            tuple: (상태, "", 근거)
        """
        del exe, runner, timeout_s
        from . import detect

        return detect.FOUND, "", "api backend: nothing to verify"

    # ------------------------------------------------------------------
    # 세션과 argv
    # ------------------------------------------------------------------

    default_posture_name = CHAT_POSTURE_NAME
    default_builtin_tools = ()
    expect_mcp_servers_product = ()

    def new_session_id(self):
        """uuid4 문자열. 로그북 파일명이 이 값에 걸려 있다."""
        return str(uuid_mod.uuid4())

    def posture_spec(self, name=None):
        """채팅 전용 포스처 하나. 이름을 무엇으로 물어도 같은 것이다.

        세 목록이 비어 있으므로 포스처 상승이 뜻을 갖지 않는다 - 올릴
        권한이 없다는 사실을 `ApiBackend.elevate()` 가 말한다.
        """
        del name
        return CHAT_POSTURE

    def build_spawn_argv(self, exe, spec, session_id=None,
                         resume_session_id=None, mcp_config_path=None,
                         add_dirs=(), model=None, debug_file=None,
                         plugin_dirs=()):
        """빈 리스트. spawn 하지 않는다."""
        del (exe, spec, session_id, resume_session_id, mcp_config_path,
             add_dirs, model, debug_file, plugin_dirs)
        return []

    def build_dev_argv(self, exe, session_id=None, resume_session_id=None,
                       model=None):
        """빈 리스트. 개발 구성도 spawn 이 아니다."""
        del exe, session_id, resume_session_id, model
        return []

    def write_mcp_config(self, path, **kwargs):
        """**파일을 쓰지 않는다.** 모델이 MCP 를 보지 않는다.

        Returns:
            str: 빈 문자열.
        """
        del path, kwargs
        return ""

    def model_arg_from_settings(self, settings=None):
        """사용자가 고른 모델명. Anthropic 은 기본값으로 떨어진다.

        계약 서명에 `settings` 를 더한 것은 **선택 인자**다. 기본값으로
        부르면 계약 그대로이고(`QgsSettings` 를 읽는다), 주입된 설정으로
        도는 하네스와 `ApiBackend` 가 그 값을 넘긴다 - 안 넘기면 임시 INI
        로 도는 회차에서 모델명이 빈 문자열로 읽힌다.

        Args:
            settings: QSettings 호환 객체. None 이면 QgsSettings.

        Returns:
            str: 모델명. OpenAI 호환에서 미설정이면 빈 문자열이다.
        """
        return llmkeys.read_model(self.provider, settings=settings)

    def serialize_user_input(self, text, uuid=None):
        """로그북 입력 녹화에만 쓰는 한 줄.

        stdin 이 없으므로 **전송에는 쓰이지 않는다.** 그래도
        `adapter_claude` 와 같은 줄을 돌려주는 이유는 녹화본 포맷을 한
        가지로 두는 것이다 - 두 모드의 jsonl 을 같은 도구로 읽는다.

        Args:
            text: 사용자 입력 원문.
            uuid: 붙일 식별자. None 이면 키를 넣지 않는다.

        Returns:
            str: 개행 없는 한 줄.
        """
        import json

        payload = {"type": "user"}
        if uuid is not None:
            payload["uuid"] = uuid
        payload["message"] = {"role": "user",
                              "content": [{"type": "text", "text": text}]}
        payload["parent_tool_use_id"] = None
        return json.dumps(payload, ensure_ascii=False)

    control_interrupt_subtype = API_CONTROL_INTERRUPT
    #: 대기 메시지 취소가 없다(1차는 큐를 만들지 않는다).
    control_cancel_queued_subtype = ""

    # 런타임 광고 이름. **빈 문자열은 "판정하지 않는다"** 이므로 선언
    # 플래그만으로 기능이 산다(`adapter.py` 의 그 속성 주석). API 에는
    # 능력을 광고하는 세션 개시 이벤트가 없다.
    runtime_cap_queue_lifecycle = ""
    runtime_cap_interrupt = ""
    runtime_cap_cancel_queued = ""
    runtime_cap_interrupt_send_now = ""

    def serialize_control_request(self, request_id, subtype, **fields):
        """우리가 만든 영수증과 짝지을 제어 요청 줄(docs/13 6-3).

        `adapter_claude` 와 같은 형식이다. 이 줄은 stdin 으로 가지 않고
        로그북에만 남는다 - 요청과 영수증을 녹화에서 짝지어 볼 수 있어야
        취소 경로를 사후에 읽을 수 있다.

        Args:
            request_id: 발급한 식별자.
            subtype: 요청 종류.
            **fields: 요청별 인자. None 인 것은 키 자체를 넣지 않는다.

        Returns:
            str: 개행 없는 한 줄.
        """
        import json

        request = {"subtype": subtype}
        for key in sorted(fields):
            value = fields[key]
            if value is None:
                continue
            request[key] = value
        return json.dumps(
            {"type": "control_request", "request_id": request_id,
             "request": request},
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # 프로토콜 - 전부 위임 (docs/13 1-1 의 핵심 관측)
    # ------------------------------------------------------------------

    known_system_subtypes = protocol.KNOWN_SYSTEM_SUBTYPES
    transcript_block_max = protocol.TRANSCRIPT_BLOCK_MAX

    def parse_line(self, raw, ts=None, event=None, has_event=False):
        """`protocol.parse` 위임. `adapter_claude` 와 같은 분기다."""
        if has_event:
            return protocol.parse(raw, ts=ts, event=event)
        return protocol.parse(raw, ts=ts)

    def from_stream_line(self, line):
        """`protocol.from_stream_line` 위임."""
        return protocol.from_stream_line(line)

    def init_summary(self, event):
        """`protocol.init_summary` 위임. synthetic init 도 같은 스키마다."""
        return protocol.init_summary(event)

    def init_drift(self, first, current):
        """`protocol.init_drift` 위임."""
        return protocol.init_drift(first, current)

    def rate_limit_notice(self, event):
        """`rate_limit_event` 가 오지 않는다. 항상 None 이다."""
        del event
        return None

    def tool_result_text(self, block):
        """`protocol.tool_result_text` 위임. 1차에는 호출되지 않는다."""
        return protocol.tool_result_text(block)

    def strip_read_prefix(self, body, tool_name):
        """`protocol.strip_read_prefix` 위임. 1차에는 호출되지 않는다."""
        return protocol.strip_read_prefix(body, tool_name)

    def truncate_for_render(self, text, limit=None):
        """`protocol.truncate_for_render` 위임."""
        if limit is None:
            return protocol.truncate_for_render(text)
        return protocol.truncate_for_render(text, limit)

    # ------------------------------------------------------------------
    # 턴 의미
    # ------------------------------------------------------------------

    #: 제외 신호가 없다. 도구가 0개다.
    exclusion_marker = ""
    tool_search_tool_name = ""
    turn_ends_on_result = True

    def is_session_init_event(self, event):
        """synthetic init 1줄을 가른다. 스키마는 Claude 쪽과 같다."""
        return (isinstance(event, dict) and event.get("type") == "system"
                and event.get("subtype") == "init")

    def is_turn_end_event(self, event):
        """최상위 `type=result` 하나가 턴을 닫는다(docs/13 I-2)."""
        return isinstance(event, dict) and event.get("type") == "result"

    # ------------------------------------------------------------------
    # 게이트 - 비적용 (docs/13 3-4)
    # ------------------------------------------------------------------

    def check_init(self, init_event, expect_tools=None, expect_mcp_server=None,
                   first_init=None, expect_disallowed=(),
                   expect_mcp_servers=None, asset_path=None,
                   expect_allowed=()):
        """기동 자기점검 게이트가 **비적용**이다. 항상 통과로 둔다.

        점검할 플래그가 없다 - 노출 도구도, 사전승인도, MCP 서버도 0개다.
        전송을 막는 판정은 게이트가 아니라 전송 전 점검(키와 모델)이 하고,
        그 판정은 `ApiBackend.start()` 에 있다.

        Returns:
            dict: ok, items, mcp_servers.
        """
        del (init_event, expect_tools, expect_mcp_server, first_init,
             expect_disallowed, expect_mcp_servers, asset_path, expect_allowed)
        return {"ok": True, "items": [], "mcp_servers": []}

    def format_gate(self, result):
        """게이트 판정 한 줄. 비적용이라는 사실을 적는다."""
        ok = bool((result or {}).get("ok", True))
        return "gate not_applicable ok=%s items=0" % ok

    def failed_checks(self, result):
        """하드 실패 항목이 없다."""
        del result
        return ()

    def warn_checks(self, result):
        """경고 항목이 없다."""
        del result
        return ()

    def mcp_server_status(self, event_or_result, server_name=None):
        """MCP 서버가 없다. 근거를 `not_applicable` 로 적는다.

        Returns:
            tuple: (상태, "", 근거)
        """
        del event_or_result, server_name
        from . import detect

        return detect.MISSING, "", "not_applicable"

    def soft_server_missing(self, result, server_name=None):
        """볼 서버가 없으므로 미연결로 단정하지 않는다."""
        del result, server_name
        return False

    # ------------------------------------------------------------------
    # 미로그인 가드 - "키가 있는가" 로 재해석 (docs/13 3-4)
    # ------------------------------------------------------------------

    def login_evidence(self, home=None, env=None):
        """키가 설정됐는가. **값을 보지 않고 길이만 본다.**

        Returns:
            tuple: (found, reason)
        """
        del home, env
        if llmkeys.key_present(self.provider):
            return True, "llm_key_present"
        return False, "llm_key_missing"

    def text_shows_not_logged_in(self, text):
        """본문으로 판정하지 않는다. 401 이 그 사실을 말한다."""
        del text
        return False

    def interactive_only_input(self, text):
        """대화형 전용 명령이 없다. CLI 가 아니다."""
        del text
        return ""

    def login_slash_notice(self, home=None, env=None):
        """가로챌 슬래시 명령이 없다."""
        del home, env
        return "", True, "not_applicable"

    # ------------------------------------------------------------------
    # 구체 어댑터 전용 멤버 (계약 밖. ApiBackend 와 패널만 부른다)
    # ------------------------------------------------------------------

    def request_material(self, system, messages, settings=None, tools=None):
        """`apiclient.build_request` 에 넘길 kwargs 묶음.

        **키를 지금 읽는다.** 들고 있지 않는 이유는 사용자가 패널에서
        키를 바꾸거나 지웠을 때 다음 턴이 바로 그 사실을 따라야 하기
        때문이다(docs/13 3-3 H-1).

        Args:
            system: 시스템 프롬프트. 빈 문자열이면 어댑터 기본값을 쓴다.
            messages: 평면 이력.
            settings: QSettings 호환 객체. None 이면 QgsSettings.
            tools: 2차가 쓸 자리. 1차는 그대로 넘기고 무시된다.

        Returns:
            dict: `build_request(provider, **kwargs)` 형태.
        """
        raise NotImplementedError

    def probe_material(self, settings=None):
        """0토큰 키 점검 요청 재료(docs/13 3-4).

        Returns:
            tuple: (url, headers, None)
        """
        from . import apiclient

        return apiclient.build_key_probe(
            self.provider, key=llmkeys.read_key(self.provider,
                                                settings=settings),
            base_url=llmkeys.read_base_url(settings=settings))

    def translator(self, session_id, user_uuid):
        """이 제공자의 번역기 1개. 턴마다 새로 만든다.

        Args:
            session_id: 우리 세션 식별자.
            user_uuid: 이 턴의 사용자 메시지 uuid.

        Returns:
            apiclient 의 번역기 인스턴스.
        """
        raise NotImplementedError

    def send_ready(self, settings=None):
        """전송 전 점검. 키와 모델이 갖춰졌는가(docs/13 3-4).

        Args:
            settings: QSettings 호환 객체.

        Returns:
            tuple: (보낼 수 있는가, 사용자 대면 사유). 통과면 사유는 빈
                문자열이고, **사유에 값이 들어가지 않는다.**
        """
        ok, why = llmkeys.is_configured(self.provider, settings=settings)
        if ok:
            return True, ""
        if why == "model_missing":
            return False, GATE_MODEL_MISSING_REASON
        if why == "base_url_missing":
            return False, GATE_BASE_URL_MISSING_REASON
        return False, GATE_KEY_MISSING_REASON


class AnthropicApiAdapter(ApiAdapterBase):
    """Anthropic Messages API 직결(채팅 전용).

    `name` 문자열은 **설정에 저장되므로 바꾸지 않는다**
    (`adapter_registry.DEFAULT_BACKEND_NAME` 과 같은 규약).
    """

    name = llmkeys.PROVIDER_ANTHROPIC
    display_name = "Anthropic API (채팅 전용)"
    provider = llmkeys.PROVIDER_ANTHROPIC

    def request_material(self, system, messages, settings=None, tools=None):
        """Anthropic 요청 재료. `max_tokens` 는 **필수**라 반드시 보낸다."""
        return {
            "provider": self.provider,
            "key": llmkeys.read_key(self.provider, settings=settings),
            "model": llmkeys.read_model(self.provider, settings=settings),
            "system": system or self.system_prompt,
            "messages": list(messages or ()),
            "max_tokens": llmkeys.read_max_tokens(settings=settings),
            "base_url": None,
            "tools": tools,
        }

    def translator(self, session_id, user_uuid):
        """Anthropic SSE 번역기 1개."""
        from . import apiclient

        return apiclient.AnthropicTranslator(session_id, user_uuid)


class OpenAiCompatApiAdapter(ApiAdapterBase):
    """OpenAI 호환 범용 API 직결(채팅 전용).

    base URL 과 모델명을 사용자가 적는다 - OpenAI 본가, Ollama, LM Studio,
    vLLM 이 같은 경로 규약(`/chat/completions`)을 쓴다. **키는 선택**이다
    (로컬 서버는 요구하지 않는다).
    """

    name = llmkeys.PROVIDER_OPENAI
    display_name = "OpenAI 호환 API (채팅 전용)"
    provider = llmkeys.PROVIDER_OPENAI

    def request_material(self, system, messages, settings=None, tools=None):
        """OpenAI 호환 요청 재료. `max_tokens` 를 **보내지 않는다**.

        근거는 docs/13 2-2-1 이다 - 본가는 최신 모델에서
        `max_completion_tokens` 로 바꿨고 로컬 서버는 `max_tokens` 를
        받는다 `[추측]`. 둘 중 하나를 고르면 반대쪽에서 400 이다.
        """
        return {
            "provider": self.provider,
            "key": llmkeys.read_key(self.provider, settings=settings),
            "model": llmkeys.read_model(self.provider, settings=settings),
            "system": system or self.system_prompt,
            "messages": list(messages or ()),
            "max_tokens": None,
            "base_url": llmkeys.read_base_url(settings=settings),
            "tools": tools,
        }

    def translator(self, session_id, user_uuid):
        """OpenAI 호환 chunk 번역기 1개."""
        from . import apiclient

        return apiclient.OpenAiTranslator(session_id, user_uuid)
