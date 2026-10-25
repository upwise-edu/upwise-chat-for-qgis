"""Claude Code CLI 어댑터 (docs/7 2-10 경계 1~7의 Claude 쪽 결박).

무엇을 하는가
    `adapter.BackendAdapter` 계약을 Claude Code CLI 의 실제 지식에 묶는다.
    그 지식은 세 모듈에 있다(docs/7 2-10 전수조사).

        detect.py    실행 파일 탐지, 미로그인 가드 3종
        posture.py   argv 플래그 조립, 포스처 3분류, 기동 게이트 1~6
        protocol.py  stream-json 파싱, 공통 이벤트 모델로의 접기

왜 위임인가
    이 어댑터는 **새 로직을 쓰지 않는다.** 위 세 모듈의 함수를 그대로
    부른다. 그래야 "어댑터를 끼운 뒤에도 argv 와 판정이 리터럴로 같다" 를
    등호로 증명할 수 있다(이번 회차의 절대 조건). 로직을 옮기면 같은 값을
    낸다는 것을 다시 측정해야 하고, 그 측정은 유료 경로를 탄다.

    바꾼 것은 **누가 그 함수를 부르는가** 하나다. 0.5.x 에서는
    `process.py`·`machine.py`·`plugin.py` 가 직접 불렀고, 그래서 제2
    백엔드를 넣으려면 그 셋을 전부 고쳐야 했다. 이제 셋은 어댑터만 보고,
    Codex 는 `adapter_codex.py` 하나로 들어온다.

Claude 백엔드의 능력 (docs/7 3-1 과의 대조)
    열두 플래그 전부 True 다(0.6.1 에 `queue_lifecycle`·`control_interrupt`
    두 축이 늘었고 둘 다 실측됐다). Codex 는 `long_lived`·`partial_deltas`·
    `preassigned_session_id`·`system_prompt_flag`·`plugin_dirs`·
    `skill_bundle` 이 False 또는 미검증이고, 그 차이가 docs/7 4 의
    "능력 축소 백엔드" 라는 설계 방향의 내용이다.

설계 정본: docs/7.gpt_mode_backend_design_v1.md 2-10, 4
"""

from . import adapter, posture, protocol

# 자식 환경에서 제거할 Claude 고유 키(process.child_env 의 묶음 1).
#
# 실제 QGIS 환경에는 없는 변수이고, 개발 중 Claude Code 안에서 테스트할 때만
# 상속된다. 제거해야 테스트가 실제 환경과 같아진다(README 5 함정 S0 행:
# 부모가 Claude Code 세션이면 env 9개가 상속된다).
#
# **문자열을 바꾸지 않는다** - `process.child_env` 가 0.1.x 부터 이 두 규칙
# (정확 일치 `CLAUDECODE`, 접두 `CLAUDE_CODE_`)으로 걸렀고 하네스 19 가
# 그 동작을 양성·음성으로 가른다.
CLAUDE_ENV_STRIP_EXACT = ("CLAUDECODE",)
CLAUDE_ENV_STRIP_PREFIXES = ("CLAUDE_CODE_",)

# 구독 대신 API 과금이 될 수 있음을 경고할 환경변수. 기동 진단 한 줄의 근거다.
CLAUDE_API_KEY_ENV = "ANTHROPIC_API_KEY"

# 제외 신호(설계 3-5 "거부와 제외는 다른 신호"). A14 축3a 실녹화 원문이
# `<tool_use_error>Error: No such tool available: mcp__dummy__probe_write
# </tool_use_error>` 였고 permission_denied 이벤트는 0건이었다. 거부는 구조화
# 필드로 판별하지만(V28-21) 제외에는 전용 이벤트가 없다 - 그래서 제외만 본문
# 문자열로 가른다. 소문자로 둔다(판정이 lower() 뒤에 비교한다).
CLAUDE_EXCLUSION_MARKER = "no such tool available"

# "도구 찾는 중" 으로 따로 표시하는 내장 도구(설계 4-2 ToolSearch 행).
CLAUDE_TOOL_SEARCH_NAME = "ToolSearch"

# Claude 백엔드의 능력. 열 축 전부 True 다 - 이 어댑터가 기준선이고,
# 제2 백엔드의 능력은 이것과의 차집합으로 읽힌다.
CLAUDE_CAPABILITIES = adapter.BackendCapabilities(
    long_lived=True,
    partial_deltas=True,
    preassigned_session_id=True,
    resume=True,
    system_prompt_flag=True,
    plugin_dirs=True,
    skill_bundle=True,
    tool_allowlist_flags=True,
    per_call_mcp_config=True,
    login_guard=True,
    # 0.6.1 실측 2축(동결 녹화본 outputs/queue_probe_20261024_131353).
    # 메시지에 uuid 를 붙이면 `command_lifecycle` 이 오고, control 요청의
    # 왕복은 같은 ms 안에 돌아왔다.
    queue_lifecycle=True,
    control_interrupt=True,
)

# 제어 요청 subtype 리터럴(실관측). 호출자가 문자열을 들지 않게 어댑터가
# 쥔다 - 호출자 3파일에 백엔드 리터럴을 남기지 않는 규약(docs/7 2-10)이다.
CLAUDE_CONTROL_INTERRUPT = "interrupt"
CLAUDE_CONTROL_CANCEL_QUEUED = "cancel_async_message"

# init 이 광고하는 런타임 능력 이름(실측 13종 중 우리가 쓰는 셋).
# 판본 추이 10종(2.1.295) -> 11종(2.1.306) -> 13종(2.1.310) 이고 번들 지시가
# "Open set - ignore unknown values; check each capability for exactly the
# behavior you use" 이므로, 판본을 고정하지 않고 쓰는 기능만 이름으로 본다.
# 정본 docs/10.cli_control_protocol_v1.md 8 절.
CLAUDE_CAP_MSG_LIFECYCLE = "msg_lifecycle_v1"
CLAUDE_CAP_INTERRUPT_RECEIPT = "interrupt_receipt_v1"

# 대기 작업 취소 축의 광고 이름. **주의: 이 매핑은 `[미측]` 추론이다.**
# 13종 목록에 `cancel_async_message` 전용 이름이 없고, 번들 표에서
# `interrupt_cancel_queued_v1` 은 `interrupt + cancel_queued:true` 쪽에
# 붙는다(docs/10 2 절). 우리가 보내는 요청은 per-uuid `cancel_async_message`
# (docs/10 3 절)이므로 둘의 동일성은 측정되지 않았다. 그래도 이 이름을 쓰는
# 이유는 **틀렸을 때의 방향이 안전한 쪽**이기 때문이다 - 광고에 없으면 취소
# 버튼이 아무것도 하지 않을 뿐이고(어댑터가 subtype 을 모르는 경우와 같은
# 처분), 반대로 광고를 안 보고 보내면 구 CLI 에서 그 줄이 어떻게 읽히는지
# 모른 채 과금 경로에 들어간다.
CLAUDE_CAP_CANCEL_QUEUED = "interrupt_cancel_queued_v1"


class ClaudeAdapter(adapter.BackendAdapter):
    """Claude Code CLI 백엔드.

    상태를 들지 않는다. 그래서 모듈 수준에 하나만 두고 공유한다
    (`adapter_registry.default()`). 상태를 들면 독이 둘일 때 섞인다.
    """

    name = "claude"
    display_name = "Claude Code"

    # ------------------------------------------------------------------
    # 능력
    # ------------------------------------------------------------------

    @property
    def capabilities(self):
        """CLAUDE_CAPABILITIES 하나를 돌려준다."""
        return CLAUDE_CAPABILITIES

    # ------------------------------------------------------------------
    # 탐지
    # ------------------------------------------------------------------

    api_key_env = CLAUDE_API_KEY_ENV
    env_strip_exact = CLAUDE_ENV_STRIP_EXACT
    env_strip_prefixes = CLAUDE_ENV_STRIP_PREFIXES

    # 탐지가 아직 안 돌았을 때 argv 머리에 쓰는 맨이름. 리팩터 전
    # `plugin._make_spec` 이 쓰던 리터럴 "claude" 와 같은 값이다.
    executable_fallback_name = "claude"

    @property
    def known_executable_paths(self):
        """detect.CLAUDE_KNOWN_PATHS 그대로.

        속성으로 두는 이유는 `detect` 를 모듈 수준에서 import 하지 않기
        때문이다 - `machine.py` 가 이 어댑터를 쓰는데 그 모듈은 헤드리스
        재생 조건(Qt/qgis 무의존)을 지켜야 하고, import 사슬을 얕게
        두는 것이 그 조건을 지키는 가장 싼 방법이다.
        """
        from . import detect

        return detect.CLAUDE_KNOWN_PATHS

    def find_executable(self, configured=None):
        """`detect.find_claude_exe` 위임. 반환 3-튜플이 그대로다."""
        from . import detect

        return detect.find_claude_exe(configured)

    def verify_executable(self, exe, runner, timeout_s=90.0):
        """`detect.verify_claude_exe` 위임."""
        from . import detect

        return detect.verify_claude_exe(exe, runner, timeout_s)

    # ------------------------------------------------------------------
    # 세션·argv
    # ------------------------------------------------------------------

    default_posture_name = posture.POSTURE_R
    default_builtin_tools = posture.BUILTIN_TOOLS_R
    expect_mcp_servers_product = posture.EXPECT_MCP_SERVERS_PRODUCT

    def new_session_id(self):
        """`posture.new_session_id` 위임(uuid4 문자열)."""
        return posture.new_session_id()

    def posture_spec(self, name=None):
        """`posture.posture_spec` 위임. None 이면 R 이다."""
        return posture.posture_spec(
            self.default_posture_name if name is None else name)

    def build_spawn_argv(self, exe, spec, session_id=None,
                         resume_session_id=None, mcp_config_path=None,
                         add_dirs=(), model=None, debug_file=None,
                         plugin_dirs=()):
        """`posture.build_posture_argv` 위임. 인자 순서까지 같다."""
        return posture.build_posture_argv(
            exe,
            spec,
            session_id=session_id,
            resume_session_id=resume_session_id,
            mcp_config_path=mcp_config_path,
            add_dirs=add_dirs,
            model=model,
            debug_file=debug_file,
            plugin_dirs=plugin_dirs,
        )

    def build_dev_argv(self, exe, session_id=None, resume_session_id=None,
                       model=None):
        """`posture.build_dev_argv` 위임."""
        return posture.build_dev_argv(
            exe,
            session_id=session_id,
            resume_session_id=resume_session_id,
            model=model,
        )

    def write_mcp_config(self, path, **kwargs):
        """`posture.write_mcp_config` 위임. 돌려주는 값은 쓴 파일 경로다.

        받는 키는 `config`·`embedded_python`·`server_env`·`profile_paths`·
        `collect_python` 이고, 그 밖의 키는 무시한다 - 제2 백엔드가 쓰는
        키가 섞여 들어와도 여기서 터지지 않아야 한다.
        """
        known = ("config", "embedded_python", "server_env", "profile_paths",
                 "collect_python")
        kw = {k: kwargs[k] for k in known if k in kwargs}
        return posture.write_mcp_config(path, **kw)

    def model_arg_from_settings(self):
        """저장된 모델 선택을 `--model` 값으로. 기본 선택이면 None(F6)."""
        return posture.model_arg(posture.read_model_choice())

    def serialize_user_input(self, text, uuid=None):
        """stream-json 의 user 메시지 한 줄(설계 2-4).

        `process.stream_json_user` 와 같은 형식이고, 그 함수가 이제 이
        메서드로 위임한다 - 직렬화 포맷은 백엔드 고유 지식이다
        (docs/7 2-10 경계 6).

        uuid 를 붙이는 이유
            CLI 2.1.310 은 자기 메시지 큐를 들고 있는데, **uuid 가 없으면
            `command_lifecycle` 을 내보내지 않는다**(실관측). 0.6.0 까지
            이 함수가 uuid 를 안 붙여서 큐가 보이지 않았다. 또 `result` 의
            `user_message_uuids` 가 메시지와 턴을 1:1 로 짝지어 주는데,
            그 짝짓기도 uuid 가 있어야 성립한다.

        키 순서를 녹화본과 같게 둔 이유
            동결 녹화본의 stdin 이 `type`·`uuid`·`message`·
            `parent_tool_use_id` 순이었고, 그 바이트로 큐 동작이 측정됐다.
            순서가 의미를 갖는다는 근거는 없지만 측정된 형태를 바꿀 이유도
            없다.

        Args:
            text: 사용자 입력 원문.
            uuid: 붙일 클라이언트 식별자. None 이면 0.6.0 과 **바이트
                동일**한 줄이 나온다(키를 아예 넣지 않는다).

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

    control_interrupt_subtype = CLAUDE_CONTROL_INTERRUPT
    control_cancel_queued_subtype = CLAUDE_CONTROL_CANCEL_QUEUED

    # 런타임 광고 이름(0.6.1, V47-A07). 선언 플래그와 다른 축이고,
    # 프로세스 계층이 init 광고에서 이 이름들을 찾아 하향 조정한다.
    runtime_cap_queue_lifecycle = CLAUDE_CAP_MSG_LIFECYCLE
    runtime_cap_interrupt = CLAUDE_CAP_INTERRUPT_RECEIPT
    runtime_cap_cancel_queued = CLAUDE_CAP_CANCEL_QUEUED

    def serialize_control_request(self, request_id, subtype, **fields):
        """stream-json 의 control_request 한 줄(0.6.1 실관측 축자).

            {"type":"control_request","request_id":"<보내는 쪽 지정>",
             "request":{"subtype":"interrupt"}}

        응답은 같은 `request_id` 를 반향한다 - 그것이 짝짓기 키다.

        None 인 선택 인자를 버리는 이유
            측정된 왕복은 **인자 없는 interrupt** 였다(응답이 대기 메시지를
            `still_queued` 로 명시했고 지우지 않았다). `cancel_queued=None`
            을 null 로 실어 보내면 그 요청은 측정된 형태와 다른 바이트가
            되고, CLI 가 null 을 어떻게 읽는지는 측정하지 않았다.

        Args:
            request_id: 이 요청의 식별자.
            subtype: `interrupt` 또는 `cancel_async_message`.
            **fields: 요청별 인자. interrupt 는 `cancel_queued`(bool)·
                `send_now`(bool)·`message_uuid`(str)·`reason`(str) 이
                선택이고, `cancel_async_message` 는 `message_uuid` 가
                필수다. None 인 것은 키 자체를 넣지 않는다.

        Returns:
            str: 개행 없는 한 줄.
        """
        import json

        request = {"subtype": subtype}
        # 키 순서를 재현 가능하게 둔다. dict 순서가 바이트에 그대로 나오므로
        # 정렬하지 않으면 호출마다 다른 줄이 날 수 있다(kwargs 순서 의존).
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
    # 프로토콜
    # ------------------------------------------------------------------

    known_system_subtypes = protocol.KNOWN_SYSTEM_SUBTYPES
    transcript_block_max = protocol.TRANSCRIPT_BLOCK_MAX

    def parse_line(self, raw, ts=None, event=None, has_event=False):
        """`protocol.parse` 위임.

        `has_event` 가 False 면 event 를 아예 넘기지 않는다 - protocol 쪽
        기본값이 `_UNSET` 센티넬이고 그때만 자기가 json.loads 한다.
        None 을 넘기면 "비 JSON 으로 확정" 이라는 다른 뜻이 된다.
        """
        if has_event:
            return protocol.parse(raw, ts=ts, event=event)
        return protocol.parse(raw, ts=ts)

    def from_stream_line(self, line):
        """`protocol.from_stream_line` 위임."""
        return protocol.from_stream_line(line)

    def init_summary(self, event):
        """`protocol.init_summary` 위임."""
        return protocol.init_summary(event)

    def init_drift(self, first, current):
        """`protocol.init_drift` 위임."""
        return protocol.init_drift(first, current)

    def rate_limit_notice(self, event):
        """`protocol.rate_limit_notice` 위임."""
        return protocol.rate_limit_notice(event)

    def tool_result_text(self, block):
        """`protocol.tool_result_text` 위임."""
        return protocol.tool_result_text(block)

    def strip_read_prefix(self, body, tool_name):
        """`protocol.strip_read_prefix` 위임(Read 도구 cat -n 접두)."""
        return protocol.strip_read_prefix(body, tool_name)

    def truncate_for_render(self, text, limit=None):
        """`protocol.truncate_for_render` 위임. None 이면 모듈 기본 상한."""
        if limit is None:
            return protocol.truncate_for_render(text)
        return protocol.truncate_for_render(text, limit)

    # ------------------------------------------------------------------
    # 턴 의미
    # ------------------------------------------------------------------

    exclusion_marker = CLAUDE_EXCLUSION_MARKER
    tool_search_tool_name = CLAUDE_TOOL_SEARCH_NAME
    turn_ends_on_result = True

    def is_session_init_event(self, event):
        """`type=system` 과 `subtype=init` 둘 다 맞을 때만 참.

        stream-json 모드는 **턴마다** init 이 재출현한다(session_id 는
        동일, README 5 함정 S0 행). 그래서 이 판별은 "새 세션" 이 아니라
        "게이트를 다시 돌릴 자리" 를 뜻한다.
        """
        return (isinstance(event, dict) and event.get("type") == "system"
                and event.get("subtype") == "init")

    def is_turn_end_event(self, event):
        """최상위 `type=result` 하나가 턴을 닫는다(설계 4-1, S3 판정 (d))."""
        return isinstance(event, dict) and event.get("type") == "result"

    # ------------------------------------------------------------------
    # 기동 자기점검 게이트
    # ------------------------------------------------------------------

    def check_init(self, init_event, expect_tools=None, expect_mcp_server=None,
                   first_init=None, expect_disallowed=(),
                   expect_mcp_servers=None, asset_path=None,
                   expect_allowed=()):
        """`posture.check_init` 위임. expect_tools None 은 R 기본값이다."""
        return posture.check_init(
            init_event,
            expect_tools=(self.default_builtin_tools if expect_tools is None
                          else expect_tools),
            expect_mcp_server=expect_mcp_server,
            first_init=first_init,
            expect_disallowed=expect_disallowed,
            expect_mcp_servers=expect_mcp_servers,
            asset_path=asset_path,
            expect_allowed=expect_allowed,
        )

    def format_gate(self, result):
        """`posture.format_gate` 위임."""
        return posture.format_gate(result)

    def failed_checks(self, result):
        """`posture.failed_checks` 위임."""
        return posture.failed_checks(result)

    def warn_checks(self, result):
        """`posture.warn_checks` 위임."""
        return posture.warn_checks(result)

    def mcp_server_status(self, event_or_result, server_name=None):
        """`detect.mcp_status_from_init` 위임(`init.mcp_servers` 스키마)."""
        from . import detect

        if server_name is None:
            return detect.mcp_status_from_init(event_or_result)
        return detect.mcp_status_from_init(event_or_result, server_name)

    def soft_server_missing(self, result, server_name=None):
        """`posture.soft_server_missing` 위임. None 이면 수집 서버다."""
        if server_name is None:
            return posture.soft_server_missing(result)
        return posture.soft_server_missing(result, server_name)

    # ------------------------------------------------------------------
    # 미로그인 가드
    # ------------------------------------------------------------------

    def login_evidence(self, home=None, env=None):
        """`detect.login_evidence` 위임(soft 추정)."""
        from . import detect

        return detect.login_evidence(home, env)

    def text_shows_not_logged_in(self, text):
        """`detect.text_shows_not_logged_in` 위임."""
        from . import detect

        return detect.text_shows_not_logged_in(text)

    def interactive_only_input(self, text):
        """`detect.interactive_only_slash` 위임(`/login`·`/logout`)."""
        from . import detect

        return detect.interactive_only_slash(text)

    def login_slash_notice(self, home=None, env=None):
        """`detect.login_slash_notice` 위임."""
        from . import detect

        return detect.login_slash_notice(home, env)
