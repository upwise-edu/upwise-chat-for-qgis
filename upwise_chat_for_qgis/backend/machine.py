"""stream-json 이벤트에서 UI 상태머신 (설계 4-1, 4-2, 4-4, 4-5).

    NO_BACKEND -> STARTING -> (init 게이트) -> READY
    READY -> SENT(사용자 줄 write 완료) -> RUNNING(assistant/delta)
         -> [TOOL(tool_use~tool_result). ToolSearch 는 "도구 찾는 중" 으로 구분]
         -> RUNNING -> DONE(result) -> READY
    어디서든: ERROR -> RESTARTING -> STARTING
    비차단 오버레이: AWAITING_APPROVAL (상태를 멈추지 않고 겹쳐 뜬다)

이 모듈이 막는 버그 둘

    (1) 텍스트 두 번 보이기. stream_event 의 text_delta 로 그려 둔 버퍼에
        assistant 의 권위 텍스트를 **더하면** 전부 두 번 보인다. 그래서 블록을
        키로 찾아 **치환**한다(설계 4-2 assistant text 행. "stream-json UI 의 1번 버그").
    (2) 턴을 너무 일찍 닫기. message_stop 은 블록 경계일 뿐이고 도구가 뒤따르는
        턴에서 먼저 도착한다. 턴은 최상위 result 로만 닫는다(설계 4-1).

Qt 를 import 하지 않는다. 위젯 갱신은 S4 가 이 객체의 상태를 읽어서 한다.
그래야 녹화본 재생만으로 과금 없이 검증된다(설계 10 보조 원칙).

0.5.5 부터 **백엔드 고유 이벤트 지식을 직접 들지 않는다.** 원시 줄을 공통
모델로 접는 것, 제외 신호 문자열, "도구 찾는 중" 도구 이름은 생성자가 받은
어댑터에 물어 본다(docs/7 2-10 경계 3). 공통 모델(`protocol.ParsedLine`·
`KIND_*`·렌더 상한)은 백엔드 무관이라 그대로 `protocol` 에서 읽는다.

권위 블록 짝짓기(실측 기반)
    assistant 이벤트는 블록 1개씩 따로 오고, 그 블록의 content_block_stop 보다
    먼저 도착한다(S2 녹화본: start(0) deltas assistant stop(0) start(1) ...).
    그래서 "같은 api_message_id 에서 아직 닫히지 않은, 같은 종류의 블록" 이
    유일한 짝이다. tool_use 는 content_block_start 에 id 가 실려 오므로 id 로
    먼저 짝짓는다. 짝이 없으면(부분 메시지 스트림이 꺼진 구성) 새 블록을 만든다.

설계 정본: docs/1.mvp_design_v1.md 4-1 ~ 4-5, 3-5 항목 3
"""

import time

from . import adapter_registry, protocol

# ----------------------------------------------------------------------
# 상태
# ----------------------------------------------------------------------

NO_BACKEND = "NO_BACKEND"
STARTING = "STARTING"
READY = "READY"
SENT = "SENT"
RUNNING = "RUNNING"
TOOL = "TOOL"
DONE = "DONE"
ERROR = "ERROR"
RESTARTING = "RESTARTING"

# 침묵 워치독(설계 4-5). 총 경과로 끊지 않는다. 같은 전처리 과업 실측이 141.7 s 라
# 총 경과 기준은 정상 작업을 죽인다.
SILENCE_WARN_S = 120.0
TURN_TOTAL_MAX_S = 30.0 * 60.0

# 아래 두 상수는 **백엔드 고유 지식**이고 정본은 어댑터다(docs/7 2-10 경계 3).
# 0.5.5 리팩터에서 리터럴을 `adapter_claude.py` 로 옮겼고, 여기는 기본 백엔드의
# 값을 그대로 비추는 창구로 남긴다 - 앞 회차 하네스가 이 이름으로 값을 읽으므로
# 지우면 그쪽이 깨지고, 리터럴을 두 벌로 두면 한쪽만 바뀐다.
#
# "도구 찾는 중" 으로 따로 표시하는 도구(설계 4-2 ToolSearch 행).
TOOL_SEARCH_NAME = adapter_registry.default().tool_search_tool_name

# 제외 신호(설계 3-5 "거부와 제외는 다른 신호"). A14 축3a 실녹화 원문이
# `<tool_use_error>Error: No such tool available: mcp__dummy__probe_write
# </tool_use_error>` 였고 permission_denied 이벤트는 0건이었다.
# 거부는 구조화 필드로 판별하지만(V28-21) 제외에는 전용 이벤트가 없다.
# 그래서 제외만 본문 문자열로 가른다 - 그것이 유일한 신호다.
EXCLUSION_MARKER = adapter_registry.default().exclusion_marker


class RenderBlock(object):
    """전사에 그려지는 블록 1개.

    버퍼와 권위 텍스트를 따로 들고 있고, 화면에 쓰는 값은 text() 하나다.
    권위 텍스트가 오면 버퍼를 치환하므로 몇 번 와도 결과가 같다(멱등).
    """

    __slots__ = ("key", "message_id", "index", "kind", "chunks", "authoritative",
                 "closed", "replaced_n", "tool_use_id", "tool_name", "args_chunks",
                 "args_authoritative", "oversize")

    def __init__(self, key, message_id, index, kind):
        self.key = key
        self.message_id = message_id
        self.index = index
        self.kind = kind
        self.chunks = []
        self.authoritative = None
        self.closed = False
        self.replaced_n = 0
        self.tool_use_id = ""
        self.tool_name = ""
        # input_json_delta 조각. 파싱하지 않는다(설계 4-2).
        self.args_chunks = []
        self.args_authoritative = None
        self.oversize = False

    def append_delta(self, text):
        """스트리밍 조각을 버퍼에 더한다."""
        if text:
            self.chunks.append(text)

    def set_authoritative(self, text):
        """권위 텍스트로 치환한다. 누적이 아니라 치환이다."""
        self.authoritative = text if isinstance(text, str) else ""
        self.replaced_n += 1

    def text(self):
        """화면에 쓸 값. 권위 텍스트가 있으면 그것, 없으면 버퍼."""
        if self.authoritative is not None:
            return self.authoritative
        return "".join(self.chunks)

    def streamed_text(self):
        """버퍼만. 중복 검사와 진단에 쓴다."""
        return "".join(self.chunks)

    def args_writing(self):
        """도구 인자를 아직 쓰는 중인가(설계 4-2 input_json_delta 행)."""
        return bool(self.args_chunks) and self.args_authoritative is None

    def __repr__(self):
        return "<RenderBlock %s %s len=%d>" % (self.kind, self.key, len(self.text()))


class ToolCard(object):
    """도구 호출 1건의 카드. tool_use 로 열리고 tool_result 로 닫힌다."""

    __slots__ = ("tool_use_id", "name", "tool_input", "result_raw", "result_display",
                 "result_truncated", "strip_applied", "strip_reason", "is_error",
                 "denied", "excluded", "closed", "orphan", "stage")

    def __init__(self, tool_use_id, name, tool_input, tool_search_name=None):
        """카드 하나를 연다.

        Args:
            tool_use_id: 도구 호출 id.
            name: 도구 이름.
            tool_input: 도구 인자 dict.
            tool_search_name: "도구 찾는 중" 으로 구분 표시할 도구 이름
                (0.5.5). None 이면 기본 백엔드의 값이다 - 3인자 호출을
                쓰는 앞 회차 하네스를 깨지 않기 위한 기본값이다.
        """
        self.tool_use_id = tool_use_id
        self.name = name
        self.tool_input = tool_input or {}
        self.result_raw = None
        self.result_display = ""
        self.result_truncated = False
        self.strip_applied = False
        self.strip_reason = ""
        self.is_error = None
        self.denied = False
        # 제외는 거부가 아니다. 카드 제목과 바 문구가 갈라져야 한다(설계 3-5).
        self.excluded = False
        self.closed = False
        # tool_use_id 를 모르는 tool_result 로 만들어진 카드
        self.orphan = False
        # ToolSearch 는 "도구 찾는 중" 으로 구분 표시한다(설계 4-2).
        search_name = (TOOL_SEARCH_NAME if tool_search_name is None
                       else tool_search_name)
        self.stage = "searching_tools" if name == search_name else "running"

    def __repr__(self):
        return "<ToolCard %s %s closed=%s>" % (self.name, self.tool_use_id[:12], self.closed)


class DenialAttempt(object):
    """거부된 도구 시도 1건(설계 3-5 항목 3).

    바는 턴마다 하나이고 그 안에 시도 목록을 쌓는다. B2 가 Bash 거부 뒤 Write 를
    또 시도해 다시 거부된 실측이 있다(A07 ln120~122, ln149~151).
    """

    __slots__ = ("tool_name", "tool_input", "tool_use_id", "reason", "reason_type",
                 "paired")

    def __init__(self, tool_name, tool_input, tool_use_id):
        self.tool_name = tool_name
        self.tool_input = tool_input or {}
        self.tool_use_id = tool_use_id
        # 2차 신호(tool_result is_error) 의 본문 전문. 절단하지 않는다(설계 3-5).
        self.reason = ""
        # 거부 사유 축. `decision_reason_type` 원값이고(관측값 "mode") 문구
        # 분류보다 안정적이다(장부 V28-22 b). 바는 이 값으로 분류한다.
        self.reason_type = ""
        self.paired = False

    def __repr__(self):
        return "<DenialAttempt %s reason_type=%s paired=%s>" % (
            self.tool_name, self.reason_type, self.paired)


class ExclusionAttempt(object):
    """이 포스처에 없는 도구를 모델이 부른 1건(설계 3-5 "제외" 행).

    거부와 코드 경로를 갈라 두는 자리다. 제외를 거부로 표시하면 사용자가
    "허용" 을 눌러도 아무 일이 없다 - allowlist 를 넓혀도 `--disallowedTools`
    가 이기기 때문이다(A14 축3). 그래서 재시도 버튼을 띄우지 않는다.
    """

    __slots__ = ("tool_name", "tool_input", "tool_use_id", "reason")

    def __init__(self, tool_name, tool_input, tool_use_id, reason=""):
        self.tool_name = tool_name
        self.tool_input = tool_input or {}
        self.tool_use_id = tool_use_id
        self.reason = reason

    def __repr__(self):
        return "<ExclusionAttempt %s>" % (self.tool_name,)


class Turn(object):
    """턴 1개. result 로만 닫힌다(설계 4-1)."""

    __slots__ = ("turn_no", "started_ts", "ended_ts", "blocks", "block_index",
                 "cards", "card_order", "denials", "exclusions", "is_error",
                 "result_text", "closed_by", "interrupted", "replay_text",
                 "desync", "thinking_tokens", "user_message_uuids")

    def __init__(self, turn_no, started_ts):
        self.turn_no = turn_no
        self.started_ts = started_ts
        self.ended_ts = None
        self.blocks = []
        self.block_index = {}
        self.cards = {}
        self.card_order = []
        self.denials = []
        # 제외는 거부와 다른 목록이다. 한 턴에 둘이 같이 날 수 있다.
        self.exclusions = []
        self.is_error = None
        self.result_text = ""
        self.closed_by = ""
        # init 이 턴 중에 다시 와서(재spawn) 버려진 턴
        self.interrupted = False
        self.replay_text = ""
        self.desync = ""
        self.thinking_tokens = 0
        # 이 턴을 닫은 result 가 실어 온 `user_message_uuids`(0.6.1).
        # 턴과 메시지를 1:1 로 짝지어 주는 실관측 필드다.
        self.user_message_uuids = []

    def open_cards(self):
        """아직 결과가 안 온 카드 목록."""
        return [self.cards[cid] for cid in self.card_order if not self.cards[cid].closed]

    def first_text_line(self):
        """이 턴 첫 assistant 텍스트 블록의 첫 줄.

        0.1.4 부터 마커 판정 입력은 assistant_text() 다(V28-A48). 이 메서드는
        진단과 전사 요약용으로 남긴다 - 응답이 무엇으로 시작했는지가 거짓
        음성의 원인을 가르는 단서였다.

        "thinking" 과 "tool_use" 블록은 건너뛴다. 마커 규칙이 걸려 있는 것은
        스킬이 사용자에게 내놓는 텍스트 응답이고, 생각 블록은 그 규칙의 대상이
        아니다(각 SKILL.md "출력 규칙").

        Returns:
            str: 첫 줄. 텍스트 블록이 없으면 빈 문자열.
        """
        for rb in self.blocks:
            if rb.kind != "text":
                continue
            body = rb.text()
            if not (body or "").strip():
                # 빈 텍스트 블록은 아직 델타가 안 온 껍데기일 수 있다.
                continue
            return body.split("\n", 1)[0]
        return ""

    def assistant_text(self):
        """이 턴 assistant 텍스트 블록 전부를 줄바꿈으로 이어 돌려준다.

        0.1.4(V28-A48) 마커 판정 입력이다. first_text_line() 은 첫 블록의 첫
        줄만 주므로, 모델이 스킬을 부르기 전에 안내 문장을 먼저 말한 턴에서
        마커를 놓쳤다. 도구 호출이 끼면 텍스트 블록이 여러 개로 갈라지므로
        블록 하나가 아니라 **턴의 모든 텍스트 블록**을 이어야 한다.

        "thinking" 과 "tool_use" 블록은 first_text_line() 과 같은 이유로
        건너뛴다. 마커 규칙이 걸려 있는 것은 사용자에게 내놓는 텍스트
        응답이다(각 SKILL.md "출력 규칙").

        블록 사이를 줄바꿈으로 잇는 이유는 판정식이 줄 시작 앵커를 쓰기
        때문이다. 블록을 그냥 붙이면 앞 블록 끝에 줄바꿈이 없을 때 다음 블록
        첫 줄의 마커가 줄 중간이 되어 버린다.

        Returns:
            str: 이어 붙인 본문. 텍스트 블록이 없으면 빈 문자열.
        """
        parts = []
        for rb in self.blocks:
            if rb.kind != "text":
                continue
            body = rb.text()
            if not (body or "").strip():
                continue
            parts.append(body)
        return "\n".join(parts)

    def denial_bar_open(self):
        """거부 재시도 바를 띄워야 하는가. 턴당 바는 하나다(설계 3-5)."""
        return bool(self.denials)

    def __repr__(self):
        return "<Turn %d blocks=%d closed_by=%s>" % (
            self.turn_no, len(self.blocks), self.closed_by or "(open)")


class TurnMachine(object):
    """stream-json 이벤트를 받아 상태와 전사를 유지한다.

    UI 는 feed_batch() 를 50 ms 드레인 배치마다 부르고, 그 뒤 state 와
    current_turn/turns 를 읽어 다시 그린다. 이벤트 1건당 콜백을 만들지 않는다
    (설계 2-6).
    """

    def __init__(self, on_note=None, clock=None, backend=None):
        """
        Args:
            on_note: callable(tag, detail). 진단 한 줄을 받는다. 보통
                SessionLogbook.diag 를 넘긴다. None 이면 내부 리스트에만 쌓는다.
            clock: 시각 함수. 테스트에서 바꿔 끼운다.
            backend: 백엔드 어댑터(0.5.5, docs/7 2-10 경계 3). None 이면
                기본 백엔드다. 이벤트를 공통 모델로 접는 것, 제외 신호,
                "도구 찾는 중" 도구 이름이 어댑터에 귀속된다.
        """
        self._backend = backend or adapter_registry.default()
        self._on_note = on_note
        self._clock = clock or time.time
        self.state = NO_BACKEND
        self.awaiting_approval = False

        self.turns = []
        self.current_turn = None
        self.last_closed_turn = None
        self._turn_seq = 0
        self._expected_user_text = None

        # 블록 짝짓기용. 아직 닫히지 않은 블록을 메시지별로 들고 있다.
        self._open_blocks = {}

        # init 과 상태 칩
        self.init_count = 0
        self.first_init = None
        self.chip = None
        self.drift = []

        # 세기만 하는 것들. (c) 판정의 근거다.
        self.counts = {}
        self.unknown_system_subtypes = {}
        self.unknown_types = {}
        self.nonjson_count = 0
        self.message_stop_count = 0
        self.oversize_count = 0
        self.notes = []
        self.handler_errors = []
        self.rate_limit_warnings = []
        self.desync_warnings = []

        self.last_event_ts = None
        self.lines_seen = 0

        # ----- 0.6.1 큐 수명과 제어 응답 -----

        # command_uuid -> 마지막 state. `completed`/`cancelled` 에서 지운다.
        # **대기 건수의 원천이다.** `result.queued_turn_count` 는 쓰지 않는다
        # (실관측: B 가 대기 중인 시점의 result 도 0 이었다. 그 필드로 그리면
        # 영구 0 이다).
        self.lifecycle = {}
        self.lifecycle_events = 0

        # 우리가 발급한 메시지 uuid 집합. 재방출 user 줄이 우리 것인지
        # 가르는 유일한 기준이다. **비어 있으면 판정을 하지 않는다** -
        # 등록이 없는 재생에서 모든 줄을 CLI 생성분으로 몰면 전사가 빈다.
        #
        # **재spawn 에서 비우지 않는다.** 재개(`--resume`)는 이전 세션의
        # 메시지를 다시 방출할 수 있고, 그때 집합을 비웠으면 우리가 보낸
        # 메시지가 CLI 생성분으로 잘못 분류된다. 집합이 커지는 쪽이 안전한
        # 방향이다(세션 1개의 메시지 수는 수백 단위다).
        self._issued_uuids = set()
        self._expected_user_uuid = None

        # 우리가 보낸 제어 요청. request_id -> subtype.
        self._our_control_ids = {}
        self.control_responses = []
        self.unmatched_control_responses = []

        # 우리 interrupt 의 응답을 받았는가. 이 사실만이 "중단 직후" 의
        # 근거다(추측 금지). 중단된 턴 1개를 분류하면 내려간다.
        self._interrupt_ack_open = False
        self.interrupt_acks = 0
        self.interrupted_turns = 0

        # uuid 가 우리 발급 집합에 없는 재방출 user 줄. CLI 생성분이다
        # (실관측: interrupt 직후 `[Request interrupted by user]` 가 CLI
        # 자기 uuid 로 온다). 분류만 하고 렌더는 UI 단계가 정한다.
        self.synthetic_user_lines = []

    # ------------------------------------------------------------------
    # 진단
    # ------------------------------------------------------------------

    def note(self, tag, detail=""):
        """진단 한 줄. 로그와 내부 목록에 같이 남긴다."""
        self.notes.append((tag, str(detail)))
        if self._on_note is not None:
            try:
                self._on_note(tag, detail)
            except Exception as exc:  # noqa: BLE001 - 로깅 실패가 UI 를 멈추지 않는다
                self.handler_errors.append("note_sink %r" % (exc,))

    def _bump(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1

    # ------------------------------------------------------------------
    # 수명 신호 (프로세스 계층이 부른다)
    # ------------------------------------------------------------------

    def note_starting(self):
        """spawn 직후. init 을 기다린다."""
        self.state = STARTING

    def note_sent(self, text, uuid=None):
        """사용자 줄을 stdin 에 넣은 직후(설계 4-1 SENT).

        replay 로 돌아오는 텍스트와 비교하기 위해 보낸 값을 기억한다.

        Args:
            text: 보낸 원문.
            uuid: 그 줄에 붙인 클라이언트 식별자(0.6.1). None 이면 0.6.0
                과 동작이 같다 - 합성 user 줄 판별과 uuid 짝짓기만 꺼진다.
        """
        self._expected_user_text = text
        self._expected_user_uuid = uuid
        if uuid:
            self.note_issued_uuid(uuid)
        self.state = SENT
        self._start_turn(reason="sent")

    def note_issued_uuid(self, uuid):
        """우리가 발급한 메시지 uuid 를 등록한다(0.6.1).

        `note_sent` 와 따로 두는 이유
            녹화본 재생에는 `note_sent` 가 없다(턴을 임의로 열면 전사가
            달라진다). 그래도 "어느 uuid 가 우리 것인가" 는 알아야 합성
            user 줄을 가를 수 있으므로, 턴을 열지 않는 등록 창구가 필요하다.

        Args:
            uuid: 등록할 식별자. 빈 값이면 아무것도 하지 않는다.
        """
        if uuid:
            self._issued_uuids.add(uuid)

    def note_control_sent(self, request_id, subtype):
        """우리가 보낸 제어 요청을 등록한다(0.6.1).

        등록하지 않은 request_id 의 응답은 짝 없는 응답으로 분류된다.
        중단 판정의 근거가 **우리 요청의 응답 수신 사실**이므로, 이 등록이
        없으면 중단된 턴을 중단으로 분류하지 않는다(추측하지 않는다).

        Args:
            request_id: 발급한 식별자.
            subtype: 요청 종류.
        """
        if request_id:
            self._our_control_ids[request_id] = subtype

    def note_cancelled(self):
        """사용자 취소. 열린 턴을 "취소됨" 으로 마감한다(설계 2-5).

        취소는 턴 중단이 아니라 백엔드 재시작이다. 그래서 턴은 result 로 닫히지
        않고 여기서 버려진다. 전사는 지우지 않는다. `closed_by` 를 "cancelled"
        로 두어 result 로 닫힌 턴과 구분한다(설계 4-1 의 "턴은 result 로만
        끝난다" 는 스트림 이벤트 규칙이고, 사용자 중단은 그 바깥이다).

        Returns:
            int or None: 마감한 턴 번호. 열린 턴이 없으면 None.
        """
        turn = self.current_turn
        turn_no = None
        if turn is not None and not turn.closed_by:
            turn.interrupted = True
            turn.closed_by = "cancelled"
            turn.ended_ts = self._clock()
            turn_no = turn.turn_no
            self.note("turn_cancelled", "turn=%d" % turn_no)
        self.current_turn = None
        self._expected_user_text = None
        self._expected_user_uuid = None
        self.state = RESTARTING
        return turn_no

    def note_died(self, rc, tail=""):
        """백엔드 사망. 전사는 유지한다(설계 8)."""
        self.state = ERROR
        self.note("machine_died", "rc=%s tail=%s" % (rc, (tail or "")[:200]))

    def note_restarting(self):
        """재시작 대기(설계 2-5 백오프). 다음 spawn 에서 note_starting() 이 온다."""
        self.state = RESTARTING

    # ------------------------------------------------------------------
    # 입력
    # ------------------------------------------------------------------

    def feed_batch(self, lines):
        """드레인 배치 하나를 처리한다.

        Args:
            lines: process.StreamLine 또는 protocol.ParsedLine 의 리스트.

        Returns:
            int: 처리한 줄 수.
        """
        n = 0
        for line in lines:
            self.feed(line)
            n += 1
        return n

    def feed(self, line):
        """한 줄을 처리한다.

        예외를 밖으로 내보내지 않는다. 한 줄이 이상해서 독이 죽으면 전사 전체를
        잃기 때문이다. 다만 조용히 삼키지도 않는다. handler_errors 에 남기고
        진단 로그에 찍어 검증 하네스가 0 건을 확인할 수 있게 한다.
        """
        parsed = (line if isinstance(line, protocol.ParsedLine)
                  else self._backend.from_stream_line(line))
        self.lines_seen += 1
        self.last_event_ts = parsed.ts if parsed.ts is not None else self._clock()
        if parsed.oversize:
            self.oversize_count += 1
            self.note("oversize_line", "bytes=%d" % parsed.raw_bytes)
        try:
            self._dispatch(parsed)
        except Exception as exc:  # noqa: BLE001 - 한 줄의 실패가 독을 죽이지 않는다
            self.handler_errors.append("%s/%s %r" % (parsed.kind, parsed.subtype, exc))
            self.note("handler_error", "%s/%s %r" % (parsed.kind, parsed.subtype, exc))

    def _dispatch(self, parsed):
        kind = parsed.kind
        if kind == protocol.KIND_SYSTEM:
            self._on_system(parsed)
        elif kind == protocol.KIND_USER:
            self._on_user(parsed)
        elif kind == protocol.KIND_ASSISTANT:
            self._on_assistant(parsed)
        elif kind == protocol.KIND_STREAM:
            self._on_stream(parsed)
        elif kind == protocol.KIND_RESULT:
            self._on_result(parsed)
        elif kind == protocol.KIND_RATE_LIMIT:
            self._on_rate_limit(parsed)
        elif kind == protocol.KIND_LIFECYCLE:
            self._on_lifecycle(parsed)
        elif kind == protocol.KIND_CONTROL_RESPONSE:
            self._on_control_response(parsed)
        elif kind == protocol.KIND_NONJSON:
            # 무시 + 로그(설계 4-2 마지막 행들).
            self.nonjson_count += 1
            self._bump("nonjson")
            self.note("nonjson", parsed.raw[:200])
        else:
            self._on_unknown(parsed)

    # ------------------------------------------------------------------
    # system
    # ------------------------------------------------------------------

    def _on_system(self, parsed):
        subtype = parsed.subtype
        self._bump("system/" + subtype)
        if subtype == "init":
            self._on_init(parsed)
        elif subtype == "status":
            # 무시. 진단 로그에만(설계 4-2). 페이로드 구조는 미측 D08.
            self.note("status", str(parsed.event.get("status") or ""))
        elif subtype == "permission_denied":
            self._on_permission_denied(parsed)
        elif subtype == "thinking_tokens":
            # S2 실측으로 추가된 4번째 subtype. 접힌 "생각 중" 영역의 보조 표시에만 쓴다.
            if self.current_turn is not None:
                try:
                    self.current_turn.thinking_tokens = int(
                        parsed.event.get("estimated_tokens") or 0)
                except (TypeError, ValueError):
                    pass

    def _on_init(self, parsed):
        """첫 init 은 READY 로 올리고, 이후 init 은 턴 경계 표시만 한다(설계 4-2).

        전사를 비우지 않는다. 재spawn(--resume) 뒤에도 사용자가 보던 전사가
        남아 있어야 한다.
        """
        self.init_count += 1
        summary = self._backend.init_summary(parsed.event)
        self.chip = summary
        if self.init_count == 1:
            self.first_init = summary
            self.state = READY
            self.note("init_first", "model=%s mode=%s tools_n=%d mcp=%s" % (
                summary["model"], summary["permission_mode"],
                summary["tools_n"], list(summary["mcp_servers"])))
            return
        diffs = self._backend.init_drift(self.first_init, summary)
        self.drift = diffs
        self.note("init_again", "n=%d drift=%s" % (self.init_count, diffs or "none"))
        # 턴 중에 init 이 오면 그 턴은 재spawn 으로 끊긴 것이다. result 로만 닫는다는
        # 규칙을 지키려고 닫지 않고 버린 것으로 표시한다. 전사는 그대로 둔다.
        if self.current_turn is not None and not self.current_turn.closed_by:
            self.current_turn.interrupted = True
            self.current_turn.closed_by = "abandoned_init"
            self.current_turn.ended_ts = parsed.ts
            self.note("turn_abandoned", "turn=%d" % self.current_turn.turn_no)
            self.current_turn = None
        self.state = READY

    def _on_permission_denied(self, parsed):
        """거부 재시도 바의 1차 신호(설계 3-5 항목 3).

        **구조화 필드로만 만든다.** 이벤트에 `tool_name`, `tool_use_id`,
        `decision_reason_type` 가 실려 온다(장부 V28-21, A20 녹화 재확인).
        문구를 파싱하지 않는다 - 문구는 바뀌고 필드는 CLI 가 분류한 값이다.

        짝짓기는 `tool_use_id` 로 한다. 위치(마지막 열린 카드)로 묶으면 병렬
        tool_use 가 섞인 턴에서 다른 호출에 붙는다. 설계 3-5 가 "문자열 매칭이
        아니라 id 매칭" 이라고 적은 자리다. id 가 없거나 못 찾을 때만 위치로
        떨어지고, 그 사실을 진단에 남긴다.
        """
        turn = self._ensure_turn("permission_denied")
        event = parsed.event if isinstance(parsed.event, dict) else {}
        ev_tool = event.get("tool_name") or ""
        ev_id = event.get("tool_use_id") or ""
        reason_type = event.get("decision_reason_type") or ""

        card = turn.cards.get(ev_id) if ev_id else None
        paired_by = "tool_use_id"
        if card is None:
            open_cards = turn.open_cards()
            card = open_cards[-1] if open_cards else None
            paired_by = "position" if card is not None else "none"

        if card is not None:
            card.denied = True
            # 이름은 이벤트 필드를 권위로 쓴다. 카드 이름은 같은 값이어야 하고,
            # 다르면 짝짓기가 틀린 것이므로 진단에 남는다.
            name = ev_tool or card.name
            if ev_tool and card.name and ev_tool != card.name:
                self.note("denial_name_mismatch",
                          "event=%s card=%s" % (ev_tool, card.name))
            attempt = DenialAttempt(name, card.tool_input, ev_id or card.tool_use_id)
        else:
            # tool_use 를 못 본 거부. 이벤트 필드만으로 바를 세운다.
            attempt = DenialAttempt(ev_tool or "(unknown)", {}, ev_id)
            self.note("denied_without_tool_use",
                      "turn=%d tool=%s" % (turn.turn_no, ev_tool or "(unknown)"))

        attempt.reason_type = reason_type
        turn.denials.append(attempt)
        self.awaiting_approval = True
        self.note("permission_denied",
                  "turn=%d tool=%s reason_type=%s paired_by=%s n=%d"
                  % (turn.turn_no, attempt.tool_name, reason_type or "(none)",
                     paired_by, len(turn.denials)))

    # ------------------------------------------------------------------
    # user
    # ------------------------------------------------------------------

    def _on_user(self, parsed):
        """replay 와 tool_result 두 경로가 같은 type 으로 온다(설계 4-2)."""
        for block in parsed.blocks:
            if block.btype == "tool_result":
                self._on_tool_result(parsed, block)
            elif block.btype in ("text", "thinking"):
                # 0.6.1: uuid 가 우리 발급 집합에 없으면 CLI 생성분이다.
                # 집합이 비어 있으면(등록 없는 경로) 판정하지 않는다 -
                # 그때 전부 CLI 생성분으로 몰면 전사가 빈다.
                if (self._issued_uuids and parsed.uuid
                        and parsed.uuid not in self._issued_uuids):
                    self._on_synthetic_user(parsed, block)
                else:
                    self._on_replay(parsed, block)
            else:
                self._bump("user_block/" + (block.btype or "(none)"))
                self.note("user_block_unknown", block.btype or "(none)")

    def _on_replay(self, parsed, block):
        """전송 확인 신호. 렌더하지 않는다(설계 4-2).

        사용자 말풍선은 전송 즉시 그렸으므로 여기서 또 그리면 두 번 보인다.
        """
        self._bump("user/replay")
        turn = self._ensure_turn("replay")
        turn.replay_text = (turn.replay_text + block.text) if turn.replay_text else block.text
        if self._expected_user_text is not None:
            if block.text != self._expected_user_text:
                msg = "sent=%r replay=%r" % (
                    self._expected_user_text[:80], (block.text or "")[:80])
                turn.desync = msg
                self.desync_warnings.append(msg)
                self.note("desync", msg)
            self._expected_user_text = None
        else:
            self.note("replay_no_expectation", "len=%d" % len(block.text or ""))
        if self.state in (SENT, READY, DONE):
            self.state = RUNNING

    def _on_synthetic_user(self, parsed, block):
        """CLI 가 스스로 방출한 user 줄(0.6.1 실관측).

        interrupt 직후 CLI 가 `[Request interrupted by user]` 를 **자기
        uuid** 로 내보낸다. 우리 발급 집합에 없는 uuid 가 그 식별자다
        (문구로 가르지 않는다 - 문구는 바뀌고 uuid 규약은 바뀌지 않는다).

        여기서는 **분류만** 한다. 사용자 말풍선으로 섞이지 않게 재방출
        경로에서 빼 두고, 어떻게 보일지는 UI 단계가 정한다.
        """
        self._bump("user/synthetic")
        self.synthetic_user_lines.append((parsed.uuid, block.text or ""))
        self.note("synthetic_user_line",
                  "uuid=%s text=%r" % (parsed.uuid[:12], (block.text or "")[:80]))

    def _on_tool_result(self, parsed, block):
        """열린 도구 카드에 결과를 접어 넣는다(설계 4-2, 4-3).

        is_error 는 성공 시 None, 거부 시 True 로 실측됐다. `is True` 로 비교하지
        않고 참/거짓만 본다.
        """
        self._bump("user/tool_result")
        turn = self._ensure_turn("tool_result")
        cid = block.tool_use_id or ""
        card = turn.cards.get(cid)
        if card is None:
            card = ToolCard(cid, "(unknown)", {},
                            self._backend.tool_search_tool_name)
            card.orphan = True
            turn.cards[cid] = card
            turn.card_order.append(cid)
            self.note("tool_result_orphan", "id=%s" % cid[:16])
        body = self._backend.tool_result_text(block)
        card.result_raw = body
        display, applied, reason = self._backend.strip_read_prefix(body, card.name)
        card.strip_applied = applied
        card.strip_reason = reason
        card.result_display, card.result_truncated = (
            self._backend.truncate_for_render(display))
        card.is_error = block.is_error
        card.closed = True
        if block.is_error:
            # 2차 신호. 아직 사유가 안 채워진 거부 시도에 전문을 붙인다(설계 3-5).
            attached = False
            for attempt in reversed(turn.denials):
                if not attempt.paired:
                    attempt.reason = body
                    attempt.paired = True
                    if not attempt.tool_use_id and cid:
                        attempt.tool_use_id = cid
                    if attempt.tool_name == "(unknown)" and card.name != "(unknown)":
                        attempt.tool_name = card.name
                    attached = True
                    break
            if not attached:
                # 거부 신호 없이 온 오류. 둘로 갈라진다(설계 3-5).
                #   제외  "No such tool available" + 권한 이벤트 없음
                #         -> 전용 목록에 넣고 안내 바를 띄운다(재시도 버튼 없음)
                #   그 외  도구 자체의 실행 오류. 빨간 테두리만 쓰고 바는 없다
                if self._backend.exclusion_marker in (body or "").lower():
                    card.excluded = True
                    turn.exclusions.append(
                        ExclusionAttempt(card.name, card.tool_input,
                                         card.tool_use_id, body))
                    self.note("tool_excluded",
                              "turn=%d tool=%s n=%d"
                              % (turn.turn_no, card.name, len(turn.exclusions)))
                else:
                    self.note("tool_error_without_denial", "tool=%s" % card.name)
        if not turn.open_cards():
            if self.state == TOOL:
                self.state = RUNNING

    # ------------------------------------------------------------------
    # assistant
    # ------------------------------------------------------------------

    def _on_assistant(self, parsed):
        """권위 블록. 스트리밍 버퍼를 치환한다(설계 4-2)."""
        msg = parsed.event.get("message")
        message_id = ""
        if isinstance(msg, dict):
            message_id = msg.get("id") or ""
        turn = self._ensure_turn("assistant")
        if self.state in (SENT, READY, DONE):
            self.state = RUNNING
        for block in parsed.blocks:
            if block.btype == "tool_use":
                self._on_tool_use(turn, message_id, block)
            elif block.btype in ("text", "thinking"):
                self._bump("assistant/" + block.btype)
                rb = self._match_block(turn, message_id, block.btype, "")
                rb.set_authoritative(block.text)
            else:
                self._bump("assistant_block/" + (block.btype or "(none)"))
                self.note("assistant_block_unknown", block.btype or "(none)")

    def _on_tool_use(self, turn, message_id, block):
        """도구 카드를 열고 상태를 TOOL 로 바꾼다(설계 4-2)."""
        self._bump("assistant/tool_use")
        rb = self._match_block(turn, message_id, "tool_use", block.tool_use_id)
        rb.tool_use_id = block.tool_use_id
        rb.tool_name = block.name
        rb.args_authoritative = block.tool_input
        cid = block.tool_use_id or ""
        card = turn.cards.get(cid)
        if card is None:
            card = ToolCard(cid, block.name, block.tool_input,
                            self._backend.tool_search_tool_name)
            turn.cards[cid] = card
            turn.card_order.append(cid)
        else:
            card.name = block.name or card.name
            card.tool_input = block.tool_input or card.tool_input
        self.state = TOOL

    # ------------------------------------------------------------------
    # stream_event
    # ------------------------------------------------------------------

    def _on_stream(self, parsed):
        """블록 경계 관리와 스트리밍 버퍼. 턴 종료로 쓰지 않는다(설계 4-2)."""
        info = parsed.stream
        if info is None:
            return
        etype = info.etype
        self._bump("stream/" + (etype or "(none)"))
        if etype == "message_stop":
            # 턴 종료가 아니다. 세어만 둔다((d) 판정의 근거).
            self.message_stop_count += 1
            return
        if etype in ("message_start", "message_delta"):
            return
        turn = self._ensure_turn("stream")
        if self.state in (SENT, READY, DONE):
            self.state = RUNNING
        if etype == "content_block_start":
            self._open_block(turn, info)
            return
        if etype == "content_block_stop":
            key = (info.message_id, info.index)
            rb = turn.block_index.get(key)
            if rb is not None:
                rb.closed = True
                self._open_blocks.pop(key, None)
            return
        if etype == "content_block_delta":
            self._bump("delta/" + (info.delta_type or "(none)"))
            key = (info.message_id, info.index)
            rb = turn.block_index.get(key)
            if rb is None:
                # start 를 못 본 delta. 블록을 만들어 두고 기록한다.
                rb = self._make_block(turn, info.message_id, info.index,
                                      self._kind_for_delta(info.delta_type))
                self.note("delta_without_start", "key=%s type=%s" % (
                    key, info.delta_type))
            if info.delta_type in ("text_delta", "thinking_delta"):
                rb.append_delta(info.delta_text)
            elif info.delta_type == "input_json_delta":
                # 조립만 한다. 부분 JSON 을 파싱하지 않는다(설계 4-2).
                if info.delta_text:
                    rb.args_chunks.append(info.delta_text)
            # signature_delta 등은 화면에 쓸 것이 없다. 세기만 했다.
            return

    def _kind_for_delta(self, delta_type):
        if delta_type == "text_delta":
            return "text"
        if delta_type == "thinking_delta":
            return "thinking"
        if delta_type == "input_json_delta":
            return "tool_use"
        return delta_type or "unknown"

    def _open_block(self, turn, info):
        cb = info.content_block or {}
        kind = cb.get("type") or "unknown"
        rb = self._make_block(turn, info.message_id, info.index, kind)
        if kind == "tool_use":
            rb.tool_use_id = cb.get("id") or ""
            rb.tool_name = cb.get("name") or ""
        return rb

    def _make_block(self, turn, message_id, index, kind):
        key = (message_id, index)
        rb = turn.block_index.get(key)
        if rb is None:
            rb = RenderBlock(key, message_id, index, kind)
            turn.block_index[key] = rb
            turn.blocks.append(rb)
            self._open_blocks[key] = rb
        return rb

    def _match_block(self, turn, message_id, kind, tool_use_id):
        """권위 블록의 짝을 찾는다. 없으면 만든다.

        순서대로 본다.
            1. tool_use 면 같은 tool_use_id 의 블록
            2. 같은 message_id 에서 아직 닫히지 않은 같은 종류의 마지막 블록
            3. 같은 message_id 의 같은 종류 중 마지막 블록(stop 이 먼저 온 구성)
            4. 없으면 새 블록(부분 메시지 스트림이 꺼진 구성)
        """
        if kind == "tool_use" and tool_use_id:
            for rb in reversed(turn.blocks):
                if rb.kind == "tool_use" and rb.tool_use_id == tool_use_id:
                    return rb
        same = [rb for rb in turn.blocks if rb.message_id == message_id and rb.kind == kind]
        for rb in reversed(same):
            if not rb.closed:
                return rb
        if same:
            self.note("match_closed_block", "mid=%s kind=%s" % (message_id[:18], kind))
            return same[-1]
        # 스트리밍 없이 권위 블록만 온 경우. 인덱스를 음수로 따로 둬서
        # 나중에 오는 start/delta 의 키와 섞이지 않게 한다.
        synth_index = -1 - len([rb for rb in turn.blocks if rb.index is not None and rb.index < 0])
        self.note("authoritative_only_block", "mid=%s kind=%s idx=%d" % (
            message_id[:18], kind, synth_index))
        return self._make_block(turn, message_id, synth_index, kind)

    # ------------------------------------------------------------------
    # result, rate_limit, unknown
    # ------------------------------------------------------------------

    def _on_result(self, parsed):
        """턴을 닫는 유일한 이벤트(설계 4-1).

        프로세스는 죽지 않았으므로 is_error 가 참이어도 재시작하지 않는다
        (설계 4-2 result 행). usage/cost 는 미측 D09 라 쓰지 않는다.
        """
        self._bump("result")
        ev = parsed.event
        turn = self.current_turn
        if turn is None:
            self.note("result_without_turn", str(ev.get("subtype") or ""))
            self.state = READY
            return
        turn.is_error = ev.get("is_error")
        text = ev.get("result")
        turn.result_text = text if isinstance(text, str) else ""
        turn.ended_ts = parsed.ts
        turn.closed_by = "result"
        # 0.6.1: 턴과 메시지를 uuid 로 짝짓는다. 기존 텍스트 기반 짝짓기
        # (`_expected_user_text` / desync)를 **대체하지 않고 병행**한다 -
        # 텍스트 축은 재방출 왕복을 재고 이 축은 result 와 메시지를 잇는다.
        turn.user_message_uuids = self._result_message_uuids(ev)
        # 0.6.1 V47-A03: 이 턴이 실어 온 uuid 를 미결 집합에서 정산한다.
        # 프로세스 계층의 `_settle_by_result` 와 **같은 처방이고 대상만
        # 다르다** - 그쪽은 입력 게이트(`is_busy`)의 원천을, 이쪽은 UI
        # "대기 N건" 의 원천을 든다. 한쪽만 정산하면 입력은 열렸는데 대기
        # 바가 영구히 1 을 가리키는 어긋난 상태가 난다.
        self._settle_lifecycle_by_result(turn.user_message_uuids)
        if self._expected_user_uuid is not None:
            if self._expected_user_uuid not in turn.user_message_uuids:
                msg = ("sent_uuid=%s result_uuids=%s"
                       % (self._expected_user_uuid[:12],
                          [u[:12] for u in turn.user_message_uuids]))
                self.desync_warnings.append(msg)
                self.note("uuid_desync", msg)
            self._expected_user_uuid = None
        # 중단된 턴을 백엔드 사망으로 오판하지 않는다(실관측: 그 뒤 새
        # spawn 없이 같은 프로세스가 다음 메시지를 정상 처리했다).
        if self._is_interrupted_result(ev):
            turn.interrupted = True
            turn.closed_by = "interrupted"
            self.interrupted_turns += 1
            # 창을 닫는다. interrupt 1발이 턴 1개를 중단시킨다.
            self._interrupt_ack_open = False
            self.note("turn_interrupted",
                      "turn=%d subtype=%s is_error=%s acks=%d"
                      % (turn.turn_no, ev.get("subtype"), turn.is_error,
                         self.interrupt_acks))
        # DONE 은 순간 상태다(설계 4-1 의 DONE(result) -> READY). 상태값으로
        # 머물지 않고, 닫힌 턴은 last_closed_turn 으로 조회한다. UI 가 "완료"
        # 표시를 할 재료는 턴 객체에 다 있다.
        self.state = DONE
        self.last_closed_turn = turn
        self.note("turn_closed", "turn=%d is_error=%s denials=%d" % (
            turn.turn_no, turn.is_error, len(turn.denials)))
        self.current_turn = None
        self._expected_user_text = None
        self._expected_user_uuid = None
        # 거부 바는 턴이 닫혀도 사용자가 누를 때까지 남는다(설계 3-5). 다만
        # 거부가 없던 턴이 끝났으면 오버레이를 내린다.
        if not turn.denials:
            self.awaiting_approval = False
        self.state = READY

    # ------------------------------------------------------------------
    # 큐 수명과 제어 응답 (0.6.1)
    # ------------------------------------------------------------------

    def _on_lifecycle(self, parsed):
        """큐 수명 이벤트 1건으로 uuid 별 상태를 갱신한다.

        제거 키는 `command_uuid`(우리가 붙인 메시지 uuid)다. 줄 자신의
        `uuid` 로 지우면 들어온 적 없는 키를 지우는 것이라 집합이 영원히
        비지 않는다.

        `completed`/`cancelled` 만 제거다. 번들 스키마의 `discarded`·
        `refused` 는 관측되지 않았으므로 제거 조건에 넣지 않는다 - 관측
        없이 넓히면 아직 살아 있는 메시지를 끝난 것으로 지운다.
        """
        info = parsed.info
        if info is None:
            return
        self.lifecycle_events += 1
        self._bump("lifecycle/" + (info.state or "(none)"))
        if not info.command_uuid:
            self.note("lifecycle_without_command_uuid", parsed.raw[:120])
            return
        if info.state in (protocol.LIFECYCLE_COMPLETED,
                          protocol.LIFECYCLE_CANCELLED):
            self.lifecycle.pop(info.command_uuid, None)
        else:
            self.lifecycle[info.command_uuid] = info.state
            if info.state not in protocol.KNOWN_LIFECYCLE_STATES:
                self.note("lifecycle_unknown_state", str(info.state))
        self.note("lifecycle",
                  "state=%s cmd=%s queued=%d outstanding=%d"
                  % (info.state, info.command_uuid[:12],
                     len(self.lifecycle), self.outstanding_count()))

    def _on_control_response(self, parsed):
        """제어 응답을 request_id 로 우리 요청과 짝짓는다.

        짝이 없는 응답을 버리지 않는다 - CLI 가 originate 하는 요청의
        응답이 섞여 올 수 있고, 이 단계는 답하지 않되 관측은 남긴다.

        우리 interrupt 의 응답이면 "중단 직후" 창을 연다. 그 창이 중단된
        턴을 백엔드 결함과 가르는 유일한 근거다(추측하지 않는다).
        """
        info = parsed.info
        if info is None:
            return
        self._bump("control_response/" + (info.subtype or "(none)"))
        matched = self._our_control_ids.pop(info.request_id, "")
        self.control_responses.append((info.request_id, info.subtype,
                                       dict(info.payload), matched))
        if not matched:
            self.unmatched_control_responses.append(
                (info.request_id, info.subtype))
            self.note("control_response_unmatched",
                      "request_id=%s subtype=%s"
                      % (info.request_id or "(none)", info.subtype or "(none)"))
            return
        if matched == self._backend.control_interrupt_subtype:
            self._interrupt_ack_open = True
            self.interrupt_acks += 1
        self.note("control_response",
                  "request_id=%s subtype=%s kind=%s payload_keys=%s"
                  % (info.request_id, info.subtype or "(none)", matched,
                     ",".join(sorted(info.payload))))

    def queued_uuids(self):
        """아직 시작되지 않은(대기 중인) 메시지 uuid 들.

        UI 의 "대기 N건" 이 읽을 값이다.

        Returns:
            tuple: 수신 순서.
        """
        return tuple(k for k, v in self.lifecycle.items()
                     if v == protocol.LIFECYCLE_QUEUED)

    def running_uuids(self):
        """지금 실행 중인(started) 메시지 uuid 들.

        Returns:
            tuple
        """
        return tuple(k for k, v in self.lifecycle.items()
                     if v == protocol.LIFECYCLE_STARTED)

    def outstanding_count(self):
        """대기 건수. **`result.queued_turn_count` 와 다른 축이다.**

        세는 것은 `queued` 상태의 메시지 수 하나다(= `len(queued_uuids())`).
        실행 중인 것(`started`)은 세지 않는다 - UI 가 그리는 숫자는 "내
        차례를 기다리는 것이 몇 건인가" 이고, 실행 중인 메시지는 이미
        전사에 그려지고 있다. 실행 중인 것까지 보려면 `running_uuids()` 를
        같이 읽는다.

        Returns:
            int
        """
        return len(self.queued_uuids())

    def _result_message_uuids(self, ev):
        """result 가 실어 온 메시지 uuid 목록(0.6.1 실관측).

        복수형 필드가 권위다. 단수 필드도 같이 오지만(관측값 동일) 큐
        실행에서 복수형이 1건씩 들어온 것이 짝짓기의 근거였다.

        Returns:
            list[str]: 없으면 빈 리스트.
        """
        got = ev.get("user_message_uuids")
        if isinstance(got, (list, tuple)):
            return [u for u in got if isinstance(u, str)]
        one = ev.get("user_message_uuid")
        return [one] if isinstance(one, str) and one else []

    def _settle_lifecycle_by_result(self, message_uuids):
        """result 가 이름을 부른 uuid 를 미결 집합에서 지운다(V47-A03).

        왜 필요한가
            집합은 `completed`/`cancelled` 로만 빈다. 번들에
            `detachedToolCall: true` 와 "the turn can take them in as any
            turn does" 가 있어 **큐의 메시지가 한 턴에 접힐 수 있고**
            `[스키마]`, 접힌 uuid 에 종결 이벤트가 오지 않으면 그 uuid 가
            영구히 남아 "대기 N건" 이 내려가지 않는다.
            `result.user_message_uuids` 는 녹화 네 회차에서 1:1 이었고
            `[실측]`, 접힘이 일어나면 흡수한 턴의 그 필드에 여러 uuid 가
            실릴 자리다(docs/10 6 절).

        지우는 범위
            **result 가 이름을 부른 uuid 뿐이다.** 이름 없는 uuid 는
            손대지 않는다 - 그것이 아직 실행 중일 가능성을 우리는 배제할
            수 없다.

        Args:
            message_uuids: 이 result 의 `user_message_uuids`.

        Returns:
            int: 정산한 건수.
        """
        settled = []
        for msg_uuid in message_uuids or ():
            if self.lifecycle.pop(msg_uuid, None) is not None:
                settled.append(msg_uuid)
        if settled:
            self.note("settled_by_result",
                      "n=%d uuids=%s outstanding=%d"
                      % (len(settled),
                         ",".join(u[:12] for u in settled),
                         self.outstanding_count()))
        return len(settled)

    def _is_interrupted_result(self, ev):
        """이 result 가 "우리가 중단시킨 턴" 인가(0.6.1).

        네 조건을 **모두** 본다.

            1. 우리가 보낸 interrupt 의 응답을 받았다(`_interrupt_ack_open`)
            2. subtype 이 중단 subtype 이다
            3. `is_error` 가 참이다
            4. `result` 본문이 없다(키 부재 또는 None - 실관측은 키 부재)

        1 이 없으면 **판정하지 않는다.** 같은 모양의 result 가 다른 이유로
        날 수 있고, 그것을 중단으로 적으면 진짜 오류를 숨긴다. "직후" 를
        시간으로 재지 않는 이유도 같다 - 추측 대신 영수증을 쓴다.

        Returns:
            bool
        """
        if not self._interrupt_ack_open:
            return False
        if (ev.get("subtype") or "") != protocol.RESULT_SUBTYPE_ABORTED:
            return False
        if not ev.get("is_error"):
            return False
        return ev.get("result") is None

    def _on_rate_limit(self, parsed):
        """평시 무시, 신호가 있을 때만 경고 한 줄(설계 4-2)."""
        self._bump("rate_limit_event")
        notice = self._backend.rate_limit_notice(parsed.event)
        if notice:
            self.rate_limit_warnings.append(notice)
            self.note("rate_limit_warn", notice)

    def _on_unknown(self, parsed):
        """미지 이벤트. 예외를 던지지 않는다(설계 4-2).

        system 의 미지 subtype 과 미지 최상위 type 을 따로 센다. 버전업으로
        늘어난 것을 나중에 세어 보려면 둘을 구분해 둬야 한다.
        """
        ev = parsed.event
        if isinstance(ev, dict) and ev.get("type") == "system":
            key = parsed.subtype or "(none)"
            self.unknown_system_subtypes[key] = self.unknown_system_subtypes.get(key, 0) + 1
            self._bump("unknown_system_subtype")
            self.note("unknown_system_subtype", key)
            return
        key = parsed.subtype or "(none)"
        self.unknown_types[key] = self.unknown_types.get(key, 0) + 1
        self._bump("unknown_type")
        self.note("unknown_type", key)

    # ------------------------------------------------------------------
    # 턴
    # ------------------------------------------------------------------

    def _start_turn(self, reason):
        self._turn_seq += 1
        turn = Turn(self._turn_seq, self._clock())
        self.turns.append(turn)
        self.current_turn = turn
        self.note("turn_open", "turn=%d reason=%s" % (turn.turn_no, reason))
        return turn

    def _ensure_turn(self, reason):
        """턴이 없으면 연다.

        재생(녹화본)에는 note_sent() 가 없으므로 replay 또는 첫 assistant 에서
        턴이 열린다. 실사용에서는 note_sent() 가 먼저 열어 둔 턴을 그대로 쓴다.
        """
        if self.current_turn is None:
            return self._start_turn(reason)
        return self.current_turn

    # ------------------------------------------------------------------
    # 조회 (UI 가 읽는다)
    # ------------------------------------------------------------------

    def visible_blocks(self, limit=protocol.TRANSCRIPT_BLOCK_MAX):
        """위젯으로 유지할 최근 블록(설계 4-4). 그 위는 접는다."""
        blocks = []
        for turn in self.turns:
            blocks.extend(turn.blocks)
        return blocks[-limit:]

    def transcript_text(self):
        """전사의 텍스트 블록만 이어 붙인 값. 중복 검사와 진단에 쓴다."""
        parts = []
        for turn in self.turns:
            for rb in turn.blocks:
                if rb.kind == "text":
                    parts.append(rb.text())
        return "\n".join(parts)

    def tool_stage(self):
        """TOOL 상태의 표시 문구를 고른다(설계 4-2 ToolSearch 행)."""
        turn = self.current_turn
        if turn is None:
            return ""
        for card in turn.open_cards():
            if card.stage == "searching_tools":
                return "searching_tools"
        return "running" if turn.open_cards() else ""

    def silence_s(self, now=None):
        """마지막 이벤트로부터 흐른 시간(설계 4-5)."""
        if self.last_event_ts is None:
            return 0.0
        return max(0.0, (now if now is not None else self._clock()) - self.last_event_ts)

    def watchdog(self, now=None):
        """워치독 판정. 총 경과가 아니라 침묵이 기준이다(설계 4-5).

        Returns:
            tuple: (상태 문자열, 근거 수치). 상태는 "ok", "silent", "too_long".
        """
        now = now if now is not None else self._clock()
        silence = self.silence_s(now)
        turn = self.current_turn
        if turn is not None and turn.started_ts is not None:
            elapsed = now - turn.started_ts
            if elapsed > TURN_TOTAL_MAX_S:
                return "too_long", elapsed
        if turn is not None and silence > SILENCE_WARN_S:
            return "silent", silence
        return "ok", silence

    def summary(self):
        """하네스와 진단 번들이 쓰는 한 줄 요약 dict."""
        closed = [t for t in self.turns if t.closed_by == "result"]
        return {
            "state": self.state,
            "lines": self.lines_seen,
            "turns": len(self.turns),
            "turns_closed_by_result": len(closed),
            "turns_abandoned": len([t for t in self.turns if t.closed_by == "abandoned_init"]),
            "message_stop": self.message_stop_count,
            "init": self.init_count,
            "nonjson": self.nonjson_count,
            "unknown_system_subtypes": dict(self.unknown_system_subtypes),
            "unknown_types": dict(self.unknown_types),
            "denials": sum(len(t.denials) for t in self.turns),
            "exclusions": sum(len(t.exclusions) for t in self.turns),
            "handler_errors": len(self.handler_errors),
            "rate_limit_warnings": len(self.rate_limit_warnings),
            "desync": len(self.desync_warnings),
            "drift": list(self.drift),
            # 0.6.1. 키를 더하기만 한다 - 기존 키를 읽는 하네스는 그대로다.
            "lifecycle_events": self.lifecycle_events,
            "queued": self.outstanding_count(),
            "running": len(self.running_uuids()),
            "turns_interrupted": self.interrupted_turns,
            "interrupt_acks": self.interrupt_acks,
            "control_responses": len(self.control_responses),
            "control_responses_unmatched": len(self.unmatched_control_responses),
            "synthetic_user_lines": len(self.synthetic_user_lines),
        }
