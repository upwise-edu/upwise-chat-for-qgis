"""백엔드 어댑터 계약 (docs/7 2-10 경계 1~7).

왜 이 층이 있는가
    0.5.x 까지 플러그인은 Claude Code CLI 하나만 띄웠고, CLI 고유의 지식
    (실행 파일 위치, argv 플래그 이름, stream-json 이벤트 스키마, 턴 종료
    규칙, 미로그인 신호 문자열)이 `detect.py`·`posture.py`·`protocol.py`
    세 모듈에 흩어져 있었다. 그 셋이 Claude 종속의 90% 이상이다
    (docs/7 2-10, scout 전수조사 2026-10-15).

    제2 백엔드(OpenAI Codex CLI)를 넣으려면 그 지식을 **한 군데로 모아
    교체 가능하게** 해야 한다. 이 모듈이 그 계약이고, 계약을 Claude 쪽에
    묶는 것이 `adapter_claude.py` 다. 제2 백엔드는 `adapter_codex.py` 를
    하나 더 쓰고 레지스트리에 등록하는 것으로 들어온다 - 호출자
    (`process.py`·`machine.py`·`plugin.py`)는 손대지 않는다.

이 모듈이 하지 않는 것
    구체 백엔드를 import 하지 않는다. 그래야 순환이 생기지 않는다
    (`adapter_claude` -> `posture`/`protocol`/`detect` 는 단방향이다).
    stdlib 도 쓰지 않는다 - 계약 선언뿐이다.

공통 모델은 어디 있는가
    `ParsedLine`·`ContentBlock`·`StreamInfo`·`KIND_*` 는 **백엔드 공통**
    이고 `protocol.py` 에 남는다(docs/7 2-10 경계 3). 어댑터는 자기
    백엔드의 원시 이벤트를 그 공통 모델로 접어 돌려준다. Codex 의
    `thread.started`/`turn.completed`/`item.*` 도 같은 모델로 접힌다.

    반대로 **어댑터에 귀속되는 것**은 `KNOWN_SYSTEM_SUBTYPES`,
    `EXCLUSION_MARKER`, "턴 종료 = result 이벤트 하나" 규칙, argv 플래그
    리터럴, 실행 파일 탐지 경로, 게이트 1~6 이다(docs/7 2-10 경계 3·4).

설계 정본: docs/7.gpt_mode_backend_design_v1.md 2-10, 4, 4-1
"""


class BackendCapabilities(object):
    """백엔드가 할 수 있는 것과 못 하는 것 (docs/7 4 구조 차이 3축).

    Codex CLI 는 Claude Code 의 기능 부분집합이다(docs/7 3-1 실측). 그래서
    추상화를 "동일 기능 복제" 로 잡으면 거짓말이 된다 - 능력 플래그를 두고
    호출자가 분기하는 것이 docs/7 4 의 방향이다.

    플래그는 **기능 유무**만 말한다. "어떻게 하는가" 는 어댑터 메서드가 쥔다.
    """

    __slots__ = (
        "long_lived",
        "partial_deltas",
        "preassigned_session_id",
        "resume",
        "system_prompt_flag",
        "plugin_dirs",
        "skill_bundle",
        "tool_allowlist_flags",
        "per_call_mcp_config",
        "login_guard",
    )

    def __init__(self, long_lived=True, partial_deltas=True,
                 preassigned_session_id=True, resume=True,
                 system_prompt_flag=True, plugin_dirs=True,
                 skill_bundle=True, tool_allowlist_flags=True,
                 per_call_mcp_config=True, login_guard=True):
        """능력 플래그를 굳혀 둔다.

        Args:
            long_lived: 한 프로세스가 여러 턴을 산다(Claude). False 면 턴마다
                재spawn 이다(Codex `exec` + `exec resume`, docs/7 3-1).
            partial_deltas: 토큰 단위 부분 델타가 온다. False 면 item 단위
                갱신뿐이고 UI 는 문단 단위로 그린다(docs/7 4 축 2).
            preassigned_session_id: 호출자가 세션 id 를 미리 정해 줄 수 있다
                (`--session-id`). False 면 첫 이벤트에서 수확한다.
            resume: 세션 재개를 지원한다.
            system_prompt_flag: 1회성 시스템 프롬프트 주입 플래그가 있다
                (`--append-system-prompt`). False 면 영속 파일 우회다
                (Codex 는 AGENTS.md, docs/7 4 축 3).
            plugin_dirs: 플러그인 폴더 공급 플래그가 있다(`--plugin-dir`).
            skill_bundle: 스킬 번들·슬래시 명령·첫 줄 마커 규약이 성립한다.
                False 면 프리셋은 자연어 프롬프트 경로로 간다.
            tool_allowlist_flags: 도구 단위 노출·사전승인·제외 플래그가 있다.
            per_call_mcp_config: 1회 호출 한정 MCP 설정 주입이 가능하다.
            login_guard: 미로그인 가드 3종(A·B·C)이 정의된다.
        """
        self.long_lived = bool(long_lived)
        self.partial_deltas = bool(partial_deltas)
        self.preassigned_session_id = bool(preassigned_session_id)
        self.resume = bool(resume)
        self.system_prompt_flag = bool(system_prompt_flag)
        self.plugin_dirs = bool(plugin_dirs)
        self.skill_bundle = bool(skill_bundle)
        self.tool_allowlist_flags = bool(tool_allowlist_flags)
        self.per_call_mcp_config = bool(per_call_mcp_config)
        self.login_guard = bool(login_guard)

    def as_dict(self):
        """진단 로그와 하네스가 읽는 dict. 플래그 이름이 그대로 키다."""
        return {name: getattr(self, name) for name in self.__slots__}

    def __repr__(self):
        """진단 한 줄. True 인 플래그만 적는다."""
        on = [n for n in self.__slots__ if getattr(self, n)]
        return "<BackendCapabilities %s>" % ",".join(on)


class BackendAdapter(object):
    """한 백엔드 CLI 를 다루는 데 필요한 것 전부의 단일 창구.

    호출자가 백엔드 고유 이름을 알지 않아도 되게 만드는 것이 목적이다.
    `process.py`·`machine.py`·`plugin.py` 는 이 객체의 메서드와 속성만
    쓰고, `claude` 라는 문자열도 argv 플래그 이름도 모른다.

    구현 규칙 둘
        (1) 메서드 **서명은 백엔드 무관**이어야 한다. 백엔드 고유 인자가
            필요하면 그 어댑터의 내부로 넣는다.
        (2) 돌려주는 값은 공통 모델이다 - `protocol.ParsedLine`,
            `posture.PostureSpec` 꼴의 3목록 묶음, `(상태, 값, 근거)`
            3-튜플, 게이트 dict.

    미구현 메서드는 `NotImplementedError` 를 던진다. 능력이 없는 것은
    예외가 아니라 `capabilities` 의 False 와 "무해한 기본값" 으로 말한다 -
    예외로 말하면 호출자가 try 로 감싸야 하고, 그 try 가 진짜 버그를
    삼킨다.
    """

    #: 레지스트리 키이자 로그·설정에 적히는 식별자. ASCII 소문자.
    name = ""

    #: 사용자에게 보이는 이름. UI 문구 템플릿이 쓴다(docs/7 2-10 경계 7).
    display_name = ""

    # ------------------------------------------------------------------
    # 능력
    # ------------------------------------------------------------------

    @property
    def capabilities(self):
        """BackendCapabilities 하나. 어댑터마다 상수로 들고 있는다."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 탐지 (docs/7 2-10 경계 1)
    # ------------------------------------------------------------------

    #: 실행 파일 알려진 위치들. PATH 조회 뒤의 폴백이다.
    known_executable_paths = ()

    #: 탐지가 아직 안 돌았을 때 argv 머리에 쓰는 맨이름. PATH 해석에 맡긴다.
    executable_fallback_name = ""

    #: 구독 대신 API 과금이 될 수 있음을 경고할 환경변수 이름. 없으면 "".
    api_key_env = ""

    #: 자식 환경에서 **정확히 일치하면** 제거할 키들(대문자 비교).
    env_strip_exact = ()

    #: 자식 환경에서 **접두사로** 제거할 키들(대문자 비교).
    env_strip_prefixes = ()

    def find_executable(self, configured=None):
        """실행 파일을 찾는다.

        Args:
            configured: 설정에 저장된 경로. 빈 값이면 PATH 와 알려진 위치.

        Returns:
            tuple: (상태, 경로 또는 "", 근거 문자열). 상태 문자열은
                `detect.FOUND`/`MISSING`/`UNKNOWN` 과 같은 값이다.
        """
        raise NotImplementedError

    def verify_executable(self, exe, runner, timeout_s=90.0):
        """실행 가능 여부와 버전을 본다. 워커 스레드에서 부른다.

        Args:
            exe: 실행 파일 경로.
            runner: callable(argv, timeout_s) -> (rc, stdout, stderr).
                프로세스 기동 정책을 한 군데로 모으기 위한 주입점이다.
            timeout_s: 상한.

        Returns:
            tuple: (상태, 버전 문자열 또는 "", 근거)
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 세션·argv (docs/7 2-10 경계 2·6)
    # ------------------------------------------------------------------

    def new_session_id(self):
        """spawn 1회에 쓸 세션 식별자.

        `capabilities.preassigned_session_id` 가 False 인 백엔드도 내부
        상관 id 로 쓸 값을 돌려준다 - 로그북 파일명이 그 값에 걸려 있다.
        """
        raise NotImplementedError

    #: 기본 포스처 이름.
    default_posture_name = ""

    #: 기본 포스처의 내장 도구 노출 목록. 게이트 기대값의 기본값이다.
    default_builtin_tools = ()

    #: 게이트가 볼 ((서버 이름, "hard"|"soft"), ...) 제품 목록.
    expect_mcp_servers_product = ()

    def posture_spec(self, name=None):
        """포스처 이름 하나를 (노출, 사전승인, 제외) 3목록 묶음으로.

        Args:
            name: 포스처 이름. None 이면 `default_posture_name`.

        Returns:
            posture.PostureSpec 호환 객체(`name`·`tools`·`allowed_tools`·
            `disallowed_tools` 네 속성).
        """
        raise NotImplementedError

    def build_spawn_argv(self, exe, spec, session_id=None,
                         resume_session_id=None, mcp_config_path=None,
                         add_dirs=(), model=None, debug_file=None,
                         plugin_dirs=()):
        """제품 argv 하나를 만든다.

        능력이 없는 인자는 **조용히 무시한다**. 예: Codex 에는
        `--plugin-dir` 대응물이 없으므로 `plugin_dirs` 를 받고 버린다.
        호출자가 백엔드마다 다른 호출을 쓰지 않게 하려는 것이다.

        Returns:
            list[str]: argv.
        """
        raise NotImplementedError

    def build_dev_argv(self, exe, session_id=None, resume_session_id=None,
                       model=None):
        """MCP 설정과 사전승인 없이 띄우는 개발 구성 argv.

        무과금 하네스가 이 구성을 쓴다. 게이트는 "MCP 서버 0개" 를 기대한다.
        """
        raise NotImplementedError

    def write_mcp_config(self, path, **kwargs):
        """MCP 설정을 백엔드가 읽는 형식으로 쓰고 경로를 돌려준다.

        형식과 주입 경로가 백엔드마다 다르다 - Claude 는 `--mcp-config`
        파일 1개이고, Codex 는 `-c mcp_servers.*` 오버라이드 또는
        `.codex/config.toml`(docs/7 3-1, 둘 다 스파이크 미검증)이다.
        그래서 "어디에 무엇을 쓰는가" 를 어댑터가 쥐고, 호출자는 경로
        후보와 서버 좌표만 넘긴다.

        Args:
            path: 쓸 파일 경로 후보.
            **kwargs: 백엔드별 서버 좌표. 모르는 키는 무시한다.

        Returns:
            str: argv 에 넘길 값(보통 쓴 파일 경로). 주입이 파일 경로가
                아닌 백엔드는 빈 문자열을 돌려줄 수 있다.
        """
        raise NotImplementedError

    def model_arg_from_settings(self):
        """사용자가 고른 모델을 argv 값으로. 기본 선택이면 None.

        None 이면 `build_spawn_argv` 가 모델 플래그를 **통째로 생략**해야
        한다 - 사용자의 CLI 설정을 플러그인이 덮어쓰지 않는다는 규약
        (설계 F6)이다.
        """
        return None

    def serialize_user_input(self, text):
        """stdin 에 쓸 사용자 메시지 한 줄.

        `capabilities.long_lived` 가 False 인 백엔드는 이 값을 stdin 대신
        argv 프롬프트로 쓸 수 있다 - 그 판단은 어댑터 안에서 한다.

        Returns:
            str: 개행을 포함하지 않는다. 호출자가 붙인다.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 프로토콜 (docs/7 2-10 경계 3)
    # ------------------------------------------------------------------

    #: 아는 system subtype 들. 이 목록 밖은 무시 + 기록이다(예외 금지).
    known_system_subtypes = ()

    #: 전사 영역이 위젯으로 유지하는 최근 블록 수.
    transcript_block_max = 200

    def parse_line(self, raw, ts=None, event=None, has_event=False):
        """원시 stdout 한 줄을 공통 `ParsedLine` 으로 접는다.

        Args:
            raw: 개행을 제거한 한 줄.
            ts: 리더 스레드가 찍은 수신 시각.
            event: 이미 파싱된 dict. 리더 스레드가 파싱까지 하므로 보통
                그 값을 넘긴다.
            has_event: `event` 인자가 유효한가. None 자체가 "비 JSON" 을
                뜻하는 값이라, "안 넘겼다" 와 구분하려면 이 플래그가 필요하다.

        Returns:
            protocol.ParsedLine. 어떤 입력에도 예외를 던지지 않는다.
        """
        raise NotImplementedError

    def from_stream_line(self, line):
        """`process.StreamLine(ts, raw, event)` 을 `ParsedLine` 으로."""
        raise NotImplementedError

    def init_summary(self, event):
        """세션 개시 이벤트에서 상태 칩과 드리프트 비교에 쓸 값만 뽑는다."""
        raise NotImplementedError

    def init_drift(self, first, current):
        """두 개시 요약을 비교해 어긋난 필드 목록을 돌려준다."""
        raise NotImplementedError

    def rate_limit_notice(self, event):
        """사용 한도 경고 한 줄. 평시에는 None. 없는 백엔드도 None."""
        return None

    def tool_result_text(self, block):
        """도구 결과 블록의 본문을 문자열로 꺼낸다."""
        raise NotImplementedError

    def strip_read_prefix(self, body, tool_name):
        """파일 읽기 도구 결과의 줄번호 접두를 제거한다.

        Returns:
            tuple: (화면용 문자열, 적용했는가, 사유 문자열)
        """
        raise NotImplementedError

    def truncate_for_render(self, text, limit=None):
        """렌더 상한을 적용한다.

        Returns:
            tuple: (화면용 문자열, 잘렸는가)
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 턴 의미 (docs/7 2-10 경계 3 "result 종료 규칙")
    # ------------------------------------------------------------------

    #: 도구가 제외됐다는 신호. 전용 이벤트가 없어 본문 문자열로 가른다.
    #: 소문자로 둔다 - 판정이 lower() 뒤에 비교한다.
    exclusion_marker = ""

    #: "도구 찾는 중" 으로 따로 표시하는 도구 이름. 없으면 "".
    tool_search_tool_name = ""

    #: 턴이 종료 이벤트 하나로 닫히는가. False 면 프로세스 종료가 턴 종료다.
    turn_ends_on_result = True

    def is_session_init_event(self, event):
        """이 원시 이벤트가 세션 개시 이벤트인가.

        기동 자기점검 게이트를 돌려야 하는 자리를 가른다. Claude 는
        `system/init`, Codex 는 `thread.started` 다(docs/7 3-1).

        Args:
            event: 파싱된 원시 이벤트 dict.

        Returns:
            bool
        """
        raise NotImplementedError

    def is_turn_end_event(self, event):
        """이 원시 이벤트가 턴을 닫는가.

        프로세스 계층이 입력 차단을 푸는 자리다. Claude 는 최상위
        `result` 하나, Codex 는 `turn.completed`/`turn.failed` 다.

        Args:
            event: 파싱된 원시 이벤트 dict.

        Returns:
            bool
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 기동 자기점검 게이트 (docs/7 2-10 경계 4)
    # ------------------------------------------------------------------

    def check_init(self, init_event, expect_tools=None, expect_mcp_server=None,
                   first_init=None, expect_disallowed=(),
                   expect_mcp_servers=None, asset_path=None,
                   expect_allowed=()):
        """세션 개시 이벤트가 준 플래그와 맞는지 검사한다.

        게이트 항목은 백엔드마다 다르다 - Claude 는 1~6 이고 Codex 는
        이벤트 스키마가 달라 재정의 대상이다(docs/7 4 꼬리). 그래서 항목
        구성은 어댑터가 쥐고, 호출자는 `ok`·`items` 와 아래 세 조회
        함수만 본다.

        Returns:
            dict: ok(bool), items(list), 그리고 관측값 요약.
        """
        raise NotImplementedError

    def format_gate(self, result):
        """게이트 판정을 진단 로그 한 줄로."""
        raise NotImplementedError

    def failed_checks(self, result):
        """입력을 막는 하드 실패 항목 이름들."""
        raise NotImplementedError

    def warn_checks(self, result):
        """차단하지 않는 경고 항목 이름들."""
        raise NotImplementedError

    def mcp_server_status(self, event_or_result, server_name=None):
        """개시 이벤트(또는 게이트 결과)에서 MCP 서버 하나의 연결 상태.

        서버 목록이 개시 이벤트의 어느 필드에 어떤 모양으로 실려 오는지는
        백엔드 고유 지식이다(docs/7 2-3). 서버 **이름**은 우리 것이라
        호출자가 넘긴다.

        Args:
            event_or_result: 개시 이벤트 dict, 또는 `mcp_servers` 를 담은
                게이트 결과 dict.
            server_name: 볼 서버 이름. None 이면 지도 제어 서버.

        Returns:
            tuple: (상태, status 문자열, 근거)
        """
        raise NotImplementedError

    def soft_server_missing(self, result, server_name=None):
        """소프트 MCP 서버 하나가 미연결인가.

        게이트가 그 서버를 보았고 연결이 아니었을 때만 True 다. 게이트가
        돌지 않았으면 미연결로 단정하지 않는다.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 미로그인 가드 (docs/7 3-2 스파이크 항목 4)
    # ------------------------------------------------------------------

    def login_evidence(self, home=None, env=None):
        """로그인 자격의 흔적이 있는가를 **추정**한다(soft).

        단정하지 않는다. 돌려주는 값은 전송 차단이 아니라 안내 1줄에만
        쓴다. 가드가 없는 백엔드는 (True, "not_applicable") 로 둔다 -
        없는 가드가 경고를 띄우는 것보다 조용한 쪽이 맞다.

        Returns:
            tuple: (found, reason)
        """
        return True, "not_applicable"

    def text_shows_not_logged_in(self, text):
        """닫힌 턴의 본문에 미로그인 신호가 있는가(hard)."""
        return False

    def interactive_only_input(self, text):
        """입력이 비대화형 모드에서 안 도는 대화형 전용 명령인가.

        Returns:
            str: 걸린 명령 이름. 아니면 빈 문자열.
        """
        return ""

    def login_slash_notice(self, home=None, env=None):
        """가로채기 공지를 자격 탐지 결과로 고른다.

        Returns:
            tuple: (공지 문구, found, reason)
        """
        return "", True, "not_applicable"

    # ------------------------------------------------------------------
    def __repr__(self):
        """진단 한 줄."""
        return "<%s name=%s>" % (type(self).__name__, self.name)
