"""stream-json 파서와 이벤트 모델 (설계 4-2, 4-3, 4-4).

이 모듈은 상태를 거의 들지 않는다. 한 줄(JSON 1개)을 받아 상태머신이 쓰기 쉬운
형태로 바꿔 주는 것이 전부다. 상태 전이와 전사 누적은 machine.py 가 한다.
Qt 를 import 하지 않는다. 그래야 QGIS 밖 하네스에서 녹화본 재생으로 검증할 수 있다.

이 층이 지키는 규칙 넷

    (1) 미지 이벤트로 예외를 던지지 않는다. system subtype 은 실측으로 4종
        (init, status, permission_denied, thinking_tokens) 이 확인됐지만 그것이
        전부라는 보장이 없다. 모르는 것은 kind 를 unknown 으로 표시해 올려 보내고
        상태머신이 세기만 한다(설계 4-2 마지막 행, S2 실측 보정).
    (2) 비 JSON 줄도 버리지 않는다. kind=nonjson 으로 올려 보낸다(설계 4-2).
    (3) cat -n 접두 제거는 Read 결과에만, 전 줄이 조건을 만족할 때만 한다(설계 4-3).
    (4) 부분 JSON(input_json_delta) 을 파싱하지 않는다(설계 4-2). 조립만 하고
        권위 있는 인자는 assistant 의 tool_use 블록에서 받는다.

실측 보정(S2, 2026-10-10 녹화본 s2_live_261010_005950.jsonl)

    * system subtype 4종. thinking_tokens 가 설계 표에 없었다.
    * init.tools 는 알파벳 정렬이라 비교는 집합으로 한다.
    * assistant 이벤트는 message 1개당 블록 1개씩 따로 온다. 블록이 닫히기
        직전(content_block_stop 앞)에 도착한다. 그래서 "열려 있는 같은 종류의
        블록" 과 짝지을 수 있다(machine.py 가 그 짝짓기를 한다).
    * input_json_delta 는 녹화본에 12건 있다(설계 표의 "관측 기록 없음" 은 보정 대상).

설계 정본: docs/1.mvp_design_v1.md 4-2, 4-3, 4-4
"""

import collections
import json
import re

# ----------------------------------------------------------------------
# 상수
# ----------------------------------------------------------------------

# 최상위 type 분류. 모르는 값은 KIND_UNKNOWN 으로 떨어진다.
KIND_SYSTEM = "system"
KIND_USER = "user"
KIND_ASSISTANT = "assistant"
KIND_STREAM = "stream_event"
KIND_RESULT = "result"
KIND_RATE_LIMIT = "rate_limit_event"
KIND_NONJSON = "nonjson"
KIND_UNKNOWN = "unknown"

# 0.6.1 에 승격된 두 최상위 type.
#
# 왜 승격하는가
#     둘 다 CLI 2.1.310 에서 실관측됐고(동결 녹화본
#     outputs/queue_probe_20261024_131353), 지금까지 KIND_UNKNOWN 으로
#     떨어져 상태머신의 `unknown_types` 카운터를 올렸다. 우리가 보내는
#     user 줄에 최상위 `uuid` 를 붙이는 순간 `command_lifecycle` 이 메시지
#     1건당 2~3줄씩 쏟아지므로, 승격하지 않으면 "미지 이벤트 0건" 을
#     단정하는 하네스가 전부 거짓 red 가 된다.
KIND_LIFECYCLE = "command_lifecycle"
KIND_CONTROL_RESPONSE = "control_response"

# `command_lifecycle.state` 실관측 4종(동결 녹화본 round1/round2).
#
# 번들 스키마에는 `discarded`·`refused` 도 적혀 있지만 **관측되지 않았다.**
# 그래서 "아는 것" 목록에만 넣고, 이 목록 밖의 state 는 미결 집합에서
# 무시하지 않고 그대로 들고 간다(열린 집합 취급).
LIFECYCLE_QUEUED = "queued"
LIFECYCLE_STARTED = "started"
LIFECYCLE_COMPLETED = "completed"
LIFECYCLE_CANCELLED = "cancelled"
KNOWN_LIFECYCLE_STATES = (LIFECYCLE_QUEUED, LIFECYCLE_STARTED,
                          LIFECYCLE_COMPLETED, LIFECYCLE_CANCELLED)

# 미결(아직 끝나지 않은) 상태들. 이 둘에 있는 uuid 가 "CLI 가 아직 들고
# 있는 메시지" 다.
LIFECYCLE_OPEN_STATES = (LIFECYCLE_QUEUED, LIFECYCLE_STARTED)

# 중단된 턴의 result subtype(실관측 round2 L20).
#
# 그 줄은 `is_error=true`·`result` 키 부재·`total_cost_usd=0`·
# `terminal_reason="aborted_streaming"` 이었고, **그 뒤 새 spawn 없이**
# 같은 프로세스가 다음 메시지를 정상 처리했다. 그래서 이 subtype 하나만
# 보고 백엔드 사망으로 분류하면 안 된다(machine 이 그 판정을 한다).
RESULT_SUBTYPE_ABORTED = "error_during_execution"

# 실측으로 확인된 system subtype 4종(S2). "아는 것" 목록일 뿐이고 이 목록 밖이
# 오면 무시 + 기록이다. 예외를 던지지 않는다.
KNOWN_SYSTEM_SUBTYPES = ("init", "status", "permission_denied", "thinking_tokens")

# 렌더 상한(설계 4-4).
# 한 줄이 이보다 크면 파싱은 하되 렌더는 요약만 한다. 읽기를 자르면 JSON 이 깨진다.
RENDER_LINE_BYTES_MAX = 8 * 1024 * 1024
# 도구 결과 카드 1개의 렌더 상한. 나머지는 "전문 보기" 로 넘긴다.
TOOL_RESULT_RENDER_MAX = 4000
# 전사 영역이 위젯으로 유지하는 최근 블록 수.
TRANSCRIPT_BLOCK_MAX = 200

# cat -n 접두(설계 4-3). QRegExp 가 아니라 표준 re 다(설계 7-4 금지 API).
_PREFIX_RE = re.compile(r"^(\d+)\t")
_NUMBER_ONLY_RE = re.compile(r"^(\d+)\t$")

_UNSET = object()


# ----------------------------------------------------------------------
# 이벤트 모델
# ----------------------------------------------------------------------

#: assistant/user 메시지 안의 content 블록 1개.
#:
#: role         "assistant" 또는 "user"
#: btype        "text", "thinking", "tool_use", "tool_result", 그 외 원문값
#: text         text/thinking 블록의 본문. 없으면 ""
#: name         tool_use 의 도구 이름
#: tool_input   tool_use 의 인자 dict
#: tool_use_id  tool_use 의 id, tool_result 의 tool_use_id
#: is_error     tool_result 의 is_error 원문(성공 시 None, 거부 시 True 로 실측)
#: content      tool_result 의 본문 원문(문자열 또는 리스트)
#: raw          블록 dict 원문
ContentBlock = collections.namedtuple(
    "ContentBlock",
    "role btype text name tool_input tool_use_id is_error content raw",
)

#: stream_event 한 건의 요약.
#:
#: etype           "message_start", "content_block_start", "content_block_delta",
#:                 "content_block_stop", "message_delta", "message_stop", ...
#: index           content_block 인덱스. 메시지 단위 이벤트는 None
#: delta_type      "text_delta", "thinking_delta", "input_json_delta",
#:                 "signature_delta" 등. delta 가 아니면 ""
#: delta_text      text_delta 의 text, thinking_delta 의 thinking,
#:                 input_json_delta 의 partial_json. 그 외는 ""
#: content_block   content_block_start 의 content_block dict
#: message_id      api_message_id. 블록 키의 앞자리로 쓴다
StreamInfo = collections.namedtuple(
    "StreamInfo", "etype index delta_type delta_text content_block message_id"
)

#: `command_lifecycle` 한 건.
#:
#: command_uuid  **우리가 user 줄에 붙인 uuid.** 이것이 메시지 식별자다
#:               (줄 자신의 `uuid` 와 다르다 - 혼동하면 미결 집합이 영구히
#:               비지 않는다)
#: state         "queued"/"started"/"completed"/"cancelled" 실관측
#: uuid          lifecycle 줄 자신의 uuid. 중복 수신 판별에만 쓴다
LifecycleInfo = collections.namedtuple("LifecycleInfo", "command_uuid state uuid")

#: `control_response` 한 건.
#:
#: request_id  **보내는 쪽이 정한 값이 반향된다.** 짝짓기의 유일한 키다
#: subtype     "success" 또는 그 외(실관측은 success 만)
#: payload     내부 `response` dict. interrupt 영수증은 여기에
#:             `still_queued` 가, cancel 영수증은 `cancelled` 가 들어온다
ControlResponseInfo = collections.namedtuple(
    "ControlResponseInfo", "request_id subtype payload")


class ParsedLine(object):
    """stdout 한 줄의 분류 결과.

    process.StreamLine 과 1:1 로 대응한다. 원문(raw)을 계속 들고 다니는 이유는
    감사 기록과 "전문 보기" 때문이다(설계 4-3 규칙 4).
    """

    __slots__ = (
        "ts",
        "raw",
        "event",
        "kind",
        "subtype",
        "session_id",
        "blocks",
        "stream",
        "oversize",
        "raw_bytes",
        "uuid",
        "info",
    )

    def __init__(self, ts, raw, event, kind, subtype="", session_id="",
                 blocks=(), stream=None, oversize=False, raw_bytes=0,
                 uuid="", info=None):
        """한 줄의 분류 결과를 담는다.

        Args:
            uuid: 최상위 `uuid` 원값(0.6.1). 재방출 user 줄이 **우리가 발급한
                것인가** 를 가르는 유일한 단서다 - CLI 가 interrupt 직후
                합성 user 줄을 자기 uuid 로 방출하므로(실관측 round2 L14),
                우리 발급 집합에 없는 uuid 가 곧 CLI 생성분이다.
            info: 종류별 부가 정보. `KIND_LIFECYCLE` 이면 `LifecycleInfo`,
                `KIND_CONTROL_RESPONSE` 이면 `ControlResponseInfo`.
                그 외에는 None 이다.
        """
        self.ts = ts
        self.raw = raw
        self.event = event
        self.kind = kind
        self.subtype = subtype
        self.session_id = session_id
        self.blocks = list(blocks)
        self.stream = stream
        self.oversize = oversize
        self.raw_bytes = raw_bytes
        self.uuid = uuid
        self.info = info

    def __repr__(self):
        return "<ParsedLine %s/%s blocks=%d>" % (self.kind, self.subtype, len(self.blocks))


def parse(raw, ts=None, event=_UNSET):
    """한 줄을 ParsedLine 으로 분류한다.

    Args:
        raw: stdout 원문 한 줄(개행 제거).
        ts: 수신 시각. 리더 스레드가 찍은 값을 그대로 넘긴다.
        event: 이미 파싱된 dict. process.py 의 리더 스레드가 파싱까지 하므로
            보통 그 값을 넘긴다. 생략하면 여기서 json.loads 한다.

    Returns:
        ParsedLine. 어떤 입력에도 예외를 던지지 않는다.
    """
    raw = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
    if event is _UNSET:
        try:
            event = json.loads(raw) if raw.strip() else None
        except (ValueError, TypeError):
            event = None
    raw_bytes = len(raw.encode("utf-8", "replace"))
    oversize = raw_bytes > RENDER_LINE_BYTES_MAX

    if not isinstance(event, dict):
        return ParsedLine(ts, raw, None, KIND_NONJSON, raw_bytes=raw_bytes, oversize=oversize)

    etype = event.get("type")
    session_id = event.get("session_id") or ""
    # 최상위 uuid 는 종류를 가리지 않고 꺼낸다. 문자열이 아닌 값이 와도
    # 호출자가 isinstance 검사를 또 하지 않게 여기서 빈 문자열로 접는다.
    line_uuid = event.get("uuid")
    line_uuid = line_uuid if isinstance(line_uuid, str) else ""

    if etype == "system":
        subtype = event.get("subtype") or ""
        kind = KIND_SYSTEM if subtype in KNOWN_SYSTEM_SUBTYPES else KIND_UNKNOWN
        return ParsedLine(ts, raw, event, kind, subtype, session_id,
                          raw_bytes=raw_bytes, oversize=oversize, uuid=line_uuid)

    if etype in ("assistant", "user"):
        kind = KIND_ASSISTANT if etype == "assistant" else KIND_USER
        return ParsedLine(ts, raw, event, kind, "", session_id,
                          blocks=content_blocks(event), raw_bytes=raw_bytes,
                          oversize=oversize, uuid=line_uuid)

    if etype == "stream_event":
        return ParsedLine(ts, raw, event, KIND_STREAM, "", session_id,
                          stream=stream_info(event), raw_bytes=raw_bytes,
                          oversize=oversize, uuid=line_uuid)

    if etype == "result":
        return ParsedLine(ts, raw, event, KIND_RESULT, event.get("subtype") or "", session_id,
                          raw_bytes=raw_bytes, oversize=oversize, uuid=line_uuid)

    if etype == "rate_limit_event":
        return ParsedLine(ts, raw, event, KIND_RATE_LIMIT, "", session_id,
                          raw_bytes=raw_bytes, oversize=oversize, uuid=line_uuid)

    # 큐 수명 이벤트. subtype 자리에 state 를 넣어 두면 상태머신이 다른
    # 종류와 같은 모양으로 분기할 수 있다.
    if etype == KIND_LIFECYCLE:
        info = lifecycle_info(event)
        return ParsedLine(ts, raw, event, KIND_LIFECYCLE, info.state, session_id,
                          raw_bytes=raw_bytes, oversize=oversize,
                          uuid=line_uuid, info=info)

    # 제어 응답. session_id 가 실려 오지 않는다(실관측) - 짝짓기 키는
    # request_id 하나다.
    if etype == KIND_CONTROL_RESPONSE:
        info = control_response_info(event)
        return ParsedLine(ts, raw, event, KIND_CONTROL_RESPONSE, info.subtype,
                          session_id, raw_bytes=raw_bytes, oversize=oversize,
                          uuid=line_uuid, info=info)

    # 모르는 최상위 type. 버전업 내구성을 위해 통과시킨다.
    return ParsedLine(ts, raw, event, KIND_UNKNOWN, str(etype or ""), session_id,
                      raw_bytes=raw_bytes, oversize=oversize, uuid=line_uuid)


def lifecycle_info(event):
    """`command_lifecycle` 한 건을 LifecycleInfo 로 접는다.

    `command_uuid` 가 **우리가 붙인 메시지 uuid** 이고 `uuid` 는 lifecycle
    줄 자신의 것이다. 둘을 바꿔 쓰면 미결 집합에서 제거가 영원히 일어나지
    않는다(제거 키가 들어온 적 없는 값이 되므로).

    Returns:
        LifecycleInfo. 어떤 입력에도 예외를 던지지 않는다.
    """
    if not isinstance(event, dict):
        return LifecycleInfo("", "", "")
    cmd = event.get("command_uuid")
    state = event.get("state")
    own = event.get("uuid")
    return LifecycleInfo(
        cmd if isinstance(cmd, str) else "",
        state if isinstance(state, str) else "",
        own if isinstance(own, str) else "",
    )


def control_response_info(event):
    """`control_response` 한 건을 ControlResponseInfo 로 접는다.

    축자 형태는 이중 중첩이다(실관측).

        {"type":"control_response",
         "response":{"subtype":"success","request_id":"...",
                     "response":{"still_queued":["..."]}}}

    바깥 `response` 는 봉투이고 안쪽 `response` 가 영수증 본문이다. 안쪽이
    없는 응답도 있을 수 있으므로 빈 dict 로 접는다.

    Returns:
        ControlResponseInfo. 어떤 입력에도 예외를 던지지 않는다.
    """
    if not isinstance(event, dict):
        return ControlResponseInfo("", "", {})
    envelope = event.get("response")
    if not isinstance(envelope, dict):
        return ControlResponseInfo("", "", {})
    rid = envelope.get("request_id")
    subtype = envelope.get("subtype")
    payload = envelope.get("response")
    return ControlResponseInfo(
        rid if isinstance(rid, str) else "",
        subtype if isinstance(subtype, str) else "",
        payload if isinstance(payload, dict) else {},
    )


def from_stream_line(line):
    """process.StreamLine(ts, raw, event) 을 ParsedLine 으로 바꾼다."""
    return parse(line.raw, ts=line.ts, event=line.event)


def content_blocks(event):
    """assistant/user 이벤트의 content 블록 목록.

    content 가 문자열인 변형(일부 경로에서 가능)도 text 블록 1개로 접어 준다.
    실측 녹화본에서는 assistant 1건당 블록 1개였지만, 병렬 tool_use(설계 8)는
    블록 2개를 한 메시지에 담는다. 그래서 목록으로 다룬다.
    """
    role = "assistant" if event.get("type") == "assistant" else "user"
    msg = event.get("message")
    if not isinstance(msg, dict):
        return []
    content = msg.get("content")
    if isinstance(content, str):
        return [ContentBlock(role, "text", content, "", {}, "", None, None, {"text": content})]
    if not isinstance(content, list):
        return []
    out = []
    for blk in content:
        if not isinstance(blk, dict):
            continue
        btype = blk.get("type") or ""
        text = ""
        if btype == "text":
            text = blk.get("text") or ""
        elif btype == "thinking":
            text = blk.get("thinking") or ""
        tool_input = blk.get("input")
        out.append(
            ContentBlock(
                role,
                btype,
                text,
                blk.get("name") or "",
                tool_input if isinstance(tool_input, dict) else {},
                blk.get("tool_use_id") or blk.get("id") or "",
                blk.get("is_error"),
                blk.get("content"),
                blk,
            )
        )
    return out


def stream_info(event):
    """stream_event 를 StreamInfo 로 접는다.

    delta 종류마다 본문 키 이름이 다르다(text / thinking / partial_json).
    상태머신이 종류마다 분기하지 않게 여기서 delta_text 하나로 모은다.
    partial_json 은 조립만 하고 파싱하지 않는다(설계 4-2).
    """
    inner = event.get("event")
    if not isinstance(inner, dict):
        return StreamInfo("", None, "", "", None, event.get("api_message_id") or "")
    etype = inner.get("type") or ""
    index = inner.get("index")
    delta = inner.get("delta")
    delta_type = ""
    delta_text = ""
    if isinstance(delta, dict):
        delta_type = delta.get("type") or ""
        if delta_type == "text_delta":
            delta_text = delta.get("text") or ""
        elif delta_type == "thinking_delta":
            delta_text = delta.get("thinking") or ""
        elif delta_type == "input_json_delta":
            delta_text = delta.get("partial_json") or ""
    cb = inner.get("content_block")
    message_id = event.get("api_message_id") or ""
    if not message_id:
        inner_msg = inner.get("message")
        if isinstance(inner_msg, dict):
            message_id = inner_msg.get("id") or ""
    return StreamInfo(etype, index, delta_type, delta_text,
                      cb if isinstance(cb, dict) else None, message_id)


# ----------------------------------------------------------------------
# cat -n 접두 제거 (설계 4-3)
# ----------------------------------------------------------------------


def strip_read_prefix(body, tool_name):
    """Read 결과의 `1\\t...` 접두를 제거한다.

    설계 4-3 의 네 규칙 그대로다.
        1. 대응 tool_use.name 이 "Read" 일 때만 적용한다.
        2. 모든 줄이 `^\\d+\\t` 를 만족할 때만 일괄 제거한다. 하나라도 어긋나면 원문.
        3. 마지막 줄이 번호만 있고 본문이 비면 그 줄을 버린다(실측 꼬리 형태).
        4. 원문은 jsonl 로그에 그대로 남는다(이 함수는 화면용 사본만 만든다).

    Args:
        body: tool_result 본문 문자열.
        tool_name: 짝지어진 tool_use 의 도구 이름.

    Returns:
        tuple: (화면용 문자열, 적용했는가, 사유 문자열)
    """
    if tool_name != "Read":
        return body, False, "tool_name=%s" % (tool_name or "(none)")
    if not isinstance(body, str) or not body:
        return body, False, "not_a_string_or_empty"
    lines = body.split("\n")
    tail_dropped = False
    # 규칙 3 을 규칙 2 보다 먼저 본다. 꼬리 줄은 번호만 있어 본문이 비므로,
    # 제거 후 빈 줄을 남기지 않기 위해서다.
    if len(lines) > 1 and _NUMBER_ONLY_RE.match(lines[-1]):
        lines = lines[:-1]
        tail_dropped = True
    out = []
    for ln in lines:
        m = _PREFIX_RE.match(ln)
        if not m:
            # 규칙 2: 하나라도 어긋나면 원문을 그대로 쓴다.
            return body, False, "line_without_prefix=%r" % ln[:40]
        out.append(ln[m.end():])
    return "\n".join(out), True, "lines=%d tail_dropped=%s" % (len(out), tail_dropped)


def tool_result_text(block):
    """tool_result 블록의 본문을 문자열로 꺼낸다.

    content 가 문자열인 형태(실측)와 블록 리스트인 형태(공개 스펙)를 모두 받는다.
    리스트면 text 조각만 이어 붙인다.
    """
    content = block.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text") or "")
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def truncate_for_render(text, limit=TOOL_RESULT_RENDER_MAX):
    """렌더 상한(설계 4-4)을 적용한다.

    Returns:
        tuple: (화면용 문자열, 잘렸는가)
    """
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    if len(text) <= limit:
        return text, False
    return text[:limit], True


# ----------------------------------------------------------------------
# init 요약과 드리프트 (설계 4-2 첫 행)
# ----------------------------------------------------------------------


def init_summary(event):
    """init 이벤트에서 상태 칩과 드리프트 비교에 쓸 값만 뽑는다.

    init 은 약 4.2 KB 라 전사에 원문을 넣지 않는다(설계 4-2). 여기서 뽑은 작은
    dict 만 UI 로 올린다.
    """
    tools = event.get("tools")
    mcp = event.get("mcp_servers")
    names = []
    if isinstance(mcp, list):
        for item in mcp:
            if isinstance(item, dict):
                names.append(str(item.get("name") or ""))
            else:
                names.append(str(item))
    return {
        "model": event.get("model") or "",
        "permission_mode": event.get("permissionMode") or "",
        # init.tools 는 알파벳 정렬이라 순서로 비교하면 안 된다(S2 실측).
        "tools": frozenset(tools) if isinstance(tools, list) else frozenset(),
        "tools_n": len(tools) if isinstance(tools, list) else 0,
        "mcp_servers": tuple(names),
        "session_id": event.get("session_id") or "",
        "cwd": event.get("cwd") or "",
        "version": event.get("claude_code_version") or "",
    }


def init_drift(first, current):
    """두 init 요약을 비교해 어긋난 필드 목록을 돌려준다.

    도구는 집합으로, 나머지는 값으로 비교한다. session_id 와 cwd 는 비교 대상이
    아니다. 재개(--resume)에서 session_id 는 같지만 cwd 는 사용자가 바꿀 수 있다
    (설계 8 의 프로젝트 전환 행이 그 경로를 따로 다룬다).

    Returns:
        list[str]: 빈 리스트면 드리프트 없음.
    """
    if not first or not current:
        return []
    diffs = []
    for key in ("model", "permission_mode", "version"):
        if first.get(key) != current.get(key):
            diffs.append("%s %s->%s" % (key, first.get(key), current.get(key)))
    f_tools = first.get("tools") or frozenset()
    c_tools = current.get("tools") or frozenset()
    if f_tools != c_tools:
        added = sorted(c_tools - f_tools)
        removed = sorted(f_tools - c_tools)
        diffs.append("tools +%s -%s" % (added, removed))
    if tuple(first.get("mcp_servers") or ()) != tuple(current.get("mcp_servers") or ()):
        diffs.append("mcp_servers %s->%s" % (first.get("mcp_servers"), current.get("mcp_servers")))
    return diffs


# ----------------------------------------------------------------------
# 사용 한도 경고 (설계 4-2 rate_limit_event 행)
# ----------------------------------------------------------------------


def rate_limit_notice(event):
    """한도 경고 한 줄을 만든다. 평시에는 None 이다.

    수치 표시는 비범위(설계 9)이고 경고 한 줄만 범위 안이다. 그래서 utilization
    값은 쓰지 않고 상태 신호만 본다.

    보수적으로 정한 것: `overageStatus` 는 경고 신호로 쓰지 않는다. 평시 녹화본
    두 건 모두 `overageStatus=rejected`(`overageDisabledReason=org_level_disabled`)
    였다. 조직 설정으로 초과분을 끈 상태의 정상값이므로, 그것으로 경고하면 항상
    켜져 있는 경고가 된다. 실제로 쓰고 있는 신호는 `isUsingOverage` 다.

    Returns:
        str or None
    """
    info = event.get("rate_limit_info")
    if not isinstance(info, dict):
        return None
    status = info.get("status")
    if status is not None and status != "allowed":
        return "사용 한도에 근접했습니다(status=%s). 리셋 %s" % (status, info.get("resetsAt"))
    if info.get("isUsingOverage") is True:
        return "추가 사용분으로 실행 중입니다. 리셋 %s" % info.get("resetsAt")
    return None
