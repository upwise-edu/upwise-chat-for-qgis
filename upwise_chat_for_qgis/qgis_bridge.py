"""QGIS 지도 제어 전담 MCP stdio 서버 (0.3.0, 설계 docs/5 2-3 결정 O3).

Copyright (c) 2026 UPWISE. GPL-2.0-or-later.

왜 이 파일이 있나
    claude CLI 는 MCP 서버를 필요로 하고 stdio 서버는 **반드시 별 프로세스**
    이므로 QGIS 를 직접 만질 수 없다(설계 2-1 제약 2). 그래서 CLI 가 띄우는
    이 브리지가 플러그인 안의 내장 소켓 서버(`mcpserver/`)로 중계한다.
    0.2.x 는 이 자리에 상류 `uvx qgis-mcp-server` 6,054줄을 썼다. 제품이 쓰는
    표면은 78종이고 그 래퍼는 합 730줄·중앙값 6줄이라(설계 E21·E23), 중계만
    하는 자작 서버로 대체했다. 그 결과 **런타임 외부 의존이 0 이 된다** -
    uvx·네트워크·사용자 설치 플러그인이 전부 사라진다.

0.2.x 와 달라지는 성질 둘
    * 게이트 4 가 진짜 end-to-end 단정이 된다. 상류 브리지는 lazy connect
      라서(설계 E16) `mcp_servers connected` 가 "프로세스가 떴다" 만 뜻했다.
      이 브리지는 **기동 시 즉시 접속하고 ping 하며, 실패하면 비정상 종료**
      한다. PASS 가 "QGIS 가 실제로 응답했다" 가 된다(설계 2-3 근거 4).
    * 쓸 수 없는 도구가 사라진다. `tools/list` 를 우리가 소유하므로 78종만
      광고한다. 지금은 120종이 광고되고 그중 42종은 어느 포스처 allowlist 에도
      없어서, 모델이 집으면 거부 바가 뜨는 소모 경로였다(설계 E24).

서버측 거절 (설계 D-B4 - 이것이 CLI 플래그와 다른 겹이다)
    CLI 는 `inputSchema` 밖 인자를 걸러 주지 않는다[실측 A99]. 거르지 않으면
    그 인자가 내장 서버까지 가서 `_dispatch` 에 거절당하고, 모델은 "도구가
    고장났다" 로 읽는다. 그래서 **이름과 인자를 여기서 먼저 거절**한다.
    내장 서버도 같은 것을 또 거절한다(`mcpserver/exposure.py`) - 소켓은 같은
    사용자의 아무 프로세스나 닿을 수 있어서 브리지만으로는 가드가 아니다.

stdlib 전용·단일 파일인 이유
    백엔드가 자식 환경에서 PYTHON 오염 4키를 제거하고(장부 V28-30) 그 정화가
    손자인 이 서버까지 상속된다. `PYTHONPATH` 없는 환경에서 자기 모듈을 찾아야
    하므로 단일 파일로 두고 `-I` 로 띄운다 - `-I` 는 sys.path 에 스크립트
    폴더만 남긴다. 패키지 상대 import 도 쓰지 않는다. `collect_server.py` 와
    같은 제약이다.

인터프리터
    이 파일을 띄우는 command 는 `<QGIS_ROOT>/apps/PythonNNN/python.exe` 계열
    **절대경로**다. QGIS 런처의 `bin/python3.exe` 는 `-I` 아래에서 표준
    라이브러리를 못 찾아 즉사한다(장부 V28-P18). 해석은 backend/detect 가 한다.

설계 정본: docs/5.embedded_server_design_v1.md 2-3, 4-3, 4-5, 4-6
"""

import json
import os
import socket
import struct
import sys
import time

# ------------------------------------------------------------------ 상수·규약

PROTOCOL_FALLBACK = "2025-06-18"

# 서버 이름. **설정 키와 같을 필요가 없다**(설계 E20 실측): 도구 이름 접두사는
# `--mcp-config` 의 서버 키에서 나오고 `serverInfo.name` 과는 무관하다. 상류도
# 자기 이름이 "Qgis_mcp" 인데 접두사는 `mcp__qgis__` 였다. 설정 키는 `qgis` 로
# 두어 `mcp__qgis__*` 를 불변으로 유지한다(설계 4-1).
SERVER_NAME = "upwise_qgis"

# 소켓 프레이밍. 내장 서버 `mcpserver/wire.py` 와 같아야 한다(설계 E1).
HEADER_STRUCT = struct.Struct(">I")
RECV_CHUNK_SIZE = 65536
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB - 내장 서버의 인바운드 한도와 같다

# 소켓 왕복 타임아웃. 상류 값(protocol.py TIMEOUT_DEFAULT/LONG)과 같은 숫자지만
# **규칙이 다르다**: 서버가 자기 예산에서 끊고 브리지는 그보다 늦게 끊는다.
#
# 왜 늦게 끊어야 하나[V32-A53 실측 2026-10-12]: 두 시계가 같으면 소켓이 먼저
# 또는 동시에 끊긴다. 그러면 서버가 보내려던 구조화 취소 메시지("Processing
# cancelled after Xs. Pass a larger 'timeout'...")가 아니라 socket.timeout 이
# 모델에게 간다 - 모델은 무엇을 바꿔야 하는지 모른 채 재시도하고, 서버는
# 백그라운드에서 끝까지 돌아 파일만 생긴다. 0.3.0 실기에서 execute_processing
# 6건이 이 경로였다(outputs/gui_check_0_3_0/log_analysis_261012.md D 보충).
# 그래서 소켓 타임아웃 = 서버 예산 + MARGIN 이다.
TIMEOUT_DEFAULT = 30.0
TIMEOUT_LONG = 60.0

# 서버 예산에 더하는 여유(초). 취소 메시지 한 왕복(직렬화 + loopback 프레임)에
# 필요한 시간이고, 이벤트 루프가 취소를 알아차리는 지연까지 덮어야 한다.
# 10초는 상류가 서버 예산을 55 로 두어 60 과 5초 벌린 것(handlers/processing.py
# `_PROCESSING_TIMEOUT` 주석)의 두 배다 - 그 5초가 실기에서 모자랐다.
TIMEOUT_MARGIN = 10.0

# `timeout` 인자를 **스키마에 가진** 명령 -> 그 명령의 서버측 기본 예산(초).
# 값은 vendor 핸들러 상수를 거울로 한 것이다(handlers/processing.py
# `_PROCESSING_TIMEOUT = 55`). 자산 78종 중 `timeout` property 를 가진 것은
# execute_processing 하나다[V32-A53 전수 조사]. 서버에는 timeout 을 받는 핸들러가
# 둘 더 있지만(execute_processing_batch, execute_code) 노출 집합 밖이라
# ToolSurface 가 이름에서 거절한다. 노출을 늘릴 때 이 표도 같이 늘려야 하고,
# 하네스 45 의 정합 항목이 둘의 어긋남을 FAIL 로 잡는다.
SERVER_BUDGETS = {
    "execute_processing": 55.0,
}

# `socket.settimeout` 이 표현할 수 있는 상한(초). 정책 상한이 아니라 표현 한계다 -
# 2147483.647 = 2**31-1 밀리초이고 이를 넘기면 OverflowError 가 난다[실측
# 2026-10-12: settimeout(2147484.0) -> "timeout doesn't fit into C timeval"].
# 서버는 이런 값도 자르지 않으므로 브리지도 정책으로는 자르지 않는다. 다만
# 표현 못 하는 값으로 소켓을 만들면 호출 전체가 OverflowError 로 죽으므로,
# 여기서만 깎고 로그에 남긴다(24.8일이라 실사용 값은 닿지 않는다).
SOCKET_TIMEOUT_CEILING = 2147483.647

# 긴 핸들러. 이벤트 루프를 펌프하며 도는 것들이다(설계 2-1 제약 1).
# `SERVER_BUDGETS` 에 있는 이름은 이 집합이 아니라 그 표가 정한다 - 모델이 준
# 예산을 따라가야 하므로 고정값 60 으로는 부족하다. 여기 남는 6종은 예산 인자가
# 없어서 서버가 몇 초에 끊을지 모델이 못 바꾼다. 그래서 60 고정을 유지한다.
LONG_COMMANDS = frozenset({
    "execute_processing",
    "create_checkpoint",
    "restore_checkpoint",
    "raster_calculator",
    "zonal_statistics",
    "spatial_join",
    "field_calculator",
})

# 기동 시 접속 재시도. 플러그인이 서버를 띄운 직후에 CLI 가 우리를 spawn 하는
# 경합이 있을 수 있어 몇 번 다시 붙는다.
#
# **연결 타임아웃을 따로 두는 이유**: 닫힌 loopback 포트에 붙는 데 Windows 가
# 약 2.2초를 쓴다[실측 2026-10-11, 하네스 32 B18]. 왕복 타임아웃(30초)을 그대로
# 쓰면 5회 재시도가 11초를 넘기고, 그러면 게이트 4 가 "느린 성공" 과 "실패" 를
# 구분하지 못한다. 그래서 접속만 2초로 자르고 시도를 3회로 둔다 -
# **최악 대기는 3 x (2.0 + 0.25) 로 약 7초**다.
CONNECT_ATTEMPTS = 3
CONNECT_BACKOFF = 0.25
PREFLIGHT_CONNECT_TIMEOUT = 2.0

# 모델에게 보내는 텍스트 본문 상한(설계 4-6 사전 명세). 소켓은 10 MB 를
# 통과시키는데 그것을 그대로 주면 맥락이 터진다. 자원(`qgis://cache`)을
# 구현하지 않는 대신 하드 상한 + 구조화 절단 보고로 간다.
MAX_TEXT_BYTES = 256 * 1024

# `get_layer_features` 의 limit 상한. 상류 helpers.MAX_FEATURE_LIMIT 과 같은
# 값이고 거절 문구도 같다 - 모델이 보던 문구를 바꾸지 않는다(설계 4-5).
MAX_FEATURE_LIMIT = 50

# per-server env 계약(설계 4-3). 키는 여기 없다 - 토큰만 온다.
ENV_HOST = "UPWISE_QGIS_HOST"
ENV_PORT = "UPWISE_QGIS_PORT"
ENV_TOKEN = "UPWISE_QGIS_TOKEN"
ENV_TOOLS = "UPWISE_QGIS_TOOLS"
ENV_LOG = "UPWISE_QGIS_LOG"


class BridgeError(Exception):
    """도구 결과로 돌려줄 구조화 오류. 스택을 모델에 보내지 않는다."""


# --------------------------------------------------------------------- 로그

class ServerLog:
    """파일 전용 서버 로그. stderr 를 쓰지 않는다.

    stderr 는 claude CLI 가 읽어 독의 진단 패널로 흘리므로, 프로토콜 기록
    수십 줄이 그 채널을 메운다. `collect_server.py` 와 같은 규칙이다.
    """

    def __init__(self, path):
        """로그 파일 경로를 잡는다. 열기는 쓸 때 한다.

        Args:
            path: 로그 파일 절대경로. 빈 값이면 아무 것도 쓰지 않는다.
        """
        self.path = str(path or "")

    def write(self, kind, detail=""):
        """한 줄 즉시 flush. 로깅 실패가 브리지를 죽이지 않는다."""
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
        except Exception:  # noqa: BLE001 - 로깅 실패가 중계를 막지 않는다
            pass


# ------------------------------------------------------------------ 소켓 중계

class SocketClient:
    """내장 소켓 서버로 명령 1건을 보내고 응답을 받는다.

    매 명령마다 새 연결을 쓴다. 연결을 들고 있으면 내장 서버의 클라이언트
    슬롯(10개, 설계 E2)을 점유하고, 그 서버는 QGIS 이벤트 루프 안에서 도므로
    QGIS 재시작·프로젝트 전환 때 끊긴 소켓을 우리가 재협상해야 한다. 왕복
    비용은 loopback 에서 무시할 만하다.
    """

    def __init__(self, host, port, token, log):
        """접속 좌표를 잡는다.

        Args:
            host: 127.0.0.1 고정(설계 5-3). 비loopback 은 서버가 거절한다.
            port: 내장 서버가 bind 후 회수한 실포트(ephemeral).
            token: 세션 토큰. 플러그인 적재마다 새로 난다.
            log: ServerLog.
        """
        self.host = host
        self.port = int(port)
        self.token = token
        self.log = log

    def send(self, cmd_type, params, timeout):
        """명령 1건 왕복. 성공 시 `result` 를 돌려준다.

        Args:
            cmd_type: 내장 서버의 명령 이름.
            params: 인자 dict.
            timeout: 소켓 타임아웃(초).

        Returns:
            내장 서버 응답의 `result` 값.

        Raises:
            BridgeError: 접속·프레이밍·서버측 오류 전부.
        """
        request = {"type": cmd_type, "params": params}
        # 토큰은 모든 명령에 붙는다 - 내장 서버는 토큰 없이는 기동조차 하지
        # 않으므로(수정 5) 선택 항목이 아니다.
        if self.token:
            request["token"] = self.token
        payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
        if len(payload) > MAX_MESSAGE_SIZE:
            raise BridgeError("request is larger than the 10 MB frame limit")

        sock = None
        try:
            sock = socket.create_connection((self.host, self.port), timeout=timeout)
            sock.settimeout(timeout)
            sock.sendall(HEADER_STRUCT.pack(len(payload)) + payload)
            raw = self._recv_frame(sock)
        except BridgeError:
            raise
        except socket.timeout:
            raise BridgeError(
                "QGIS did not answer %s within %.0fs. A long tool may still be "
                "running; check the QGIS window." % (cmd_type, timeout))
        except OSError as exc:
            raise BridgeError(
                "cannot reach the embedded QGIS server at %s:%d (%s). Is the "
                "UPWISE Chat dock still open?" % (self.host, self.port, exc))
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

        try:
            response = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise BridgeError("malformed response from QGIS: %s" % exc)
        if not isinstance(response, dict):
            raise BridgeError("malformed response from QGIS: expected an object")
        if response.get("status") != "success":
            # 서버가 낸 사유를 그대로 올린다. 토큰 거절·없는 명령·틀린 인자가
            # 전부 이 경로다(설계 E1).
            raise BridgeError(str(response.get("message") or "QGIS reported an error"))
        return response.get("result")

    def _recv_frame(self, sock):
        """길이 접두 프레임 1개를 끝까지 읽는다."""
        header = self._recv_exactly(sock, 4)
        size = HEADER_STRUCT.unpack(header)[0]
        if size > MAX_MESSAGE_SIZE:
            raise BridgeError("response frame of %d bytes exceeds the 10 MB limit" % size)
        return self._recv_exactly(sock, size)

    @staticmethod
    def _recv_exactly(sock, size):
        """정확히 size 바이트를 읽는다. 중간에 끊기면 BridgeError."""
        chunks = []
        got = 0
        while got < size:
            chunk = sock.recv(min(RECV_CHUNK_SIZE, size - got))
            if not chunk:
                raise BridgeError(
                    "the embedded QGIS server closed the connection after %d of "
                    "%d bytes" % (got, size))
            chunks.append(chunk)
            got += len(chunk)
        return b"".join(chunks)


# --------------------------------------------------------- 도구 표면·인자 검사

class ToolSurface:
    """동봉한 스키마 자산 78종. 이름과 인자를 여기서 먼저 거절한다.

    자산은 상류 브리지의 생성 스키마에서 빌드 타임에 추출한 것이고(설계 4-4
    경로 A) 커밋돼 있다. 런타임에 uvx 가 돌지 않는다 - 그것이 "런타임 의존 0"
    의 내용이다(설계 함정 11).
    """

    def __init__(self, path, log):
        """자산을 읽어 이름 -> 스키마 표를 만든다.

        Args:
            path: `qgis_tools.json` 절대경로.
            log: ServerLog.

        Raises:
            SystemExit: 자산이 없거나 깨졌으면. 78종을 광고할 수 없는 상태로
                뜨면 게이트가 "연결됐다" 를 거짓으로 보고한다.
        """
        self.log = log
        try:
            with open(path, "r", encoding="utf-8") as fh:
                asset = json.load(fh)
        except (OSError, ValueError) as exc:
            log.write("FATAL", "tool asset unreadable: %s (%s)" % (path, exc))
            raise SystemExit("qgis_bridge: tool asset unreadable: %s" % exc)

        self.tools = asset.get("tools") or []
        if not self.tools:
            log.write("FATAL", "tool asset carries no tools: %s" % path)
            raise SystemExit("qgis_bridge: tool asset carries no tools")
        self.provenance = asset.get("_provenance") or {}
        self.by_name = {}
        for tool in self.tools:
            self.by_name[tool["name"]] = tool
        log.write("TOOLS", "loaded %d tools from %s" % (len(self.tools), path))

    def check(self, name, args):
        """이름과 인자를 자산에 대조한다.

        왜 브리지가 이것을 하나: CLI 는 `inputSchema` 밖 인자를 걸러 주지
        않는다[실측 A99]. 거르지 않으면 내장 서버 `_dispatch` 가 명명 파라미터
        밖 인자를 거절해(설계 함정 6) 모델에게는 "도구가 고장났다" 로 보인다.
        여기서 거절하면 **무엇이 틀렸는지** 가 결과에 실린다.

        Args:
            name: 도구 이름.
            args: 모델이 준 인자 dict.

        Returns:
            dict: 정규화된 인자.

        Raises:
            BridgeError: 이름이 없거나 인자가 스키마 밖이거나 필수가 빠졌을 때.
        """
        if name not in self.by_name:
            raise BridgeError(
                "unknown tool: %s. This build exposes %d QGIS tools."
                % (name, len(self.tools)))
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise BridgeError("arguments must be an object, got %s" % type(args).__name__)

        schema = self.by_name[name].get("inputSchema") or {}
        allowed = set((schema.get("properties") or {}).keys())
        unknown = sorted(set(args) - allowed)
        if unknown:
            raise BridgeError(
                "%s: unexpected argument(s) %s. Accepted: %s"
                % (name, ", ".join(unknown), ", ".join(sorted(allowed)) or "none"))
        missing = [k for k in (schema.get("required") or []) if k not in args]
        if missing:
            raise BridgeError(
                "%s: missing required argument(s) %s" % (name, ", ".join(missing)))
        return args


# ------------------------------------------------------------------ 응답 정형

def shape_diagnose(result, ctx):
    """`diagnose` 결과에 우리 환경을 덧붙인다 (설계 4-5).

    상류는 브리지 버전과 플러그인 버전을 비교해 불일치 경고 + `uv cache clean`
    조언을 붙였다. **그 조언을 쓰지 않는다** - 내장 서버에서는 두 반쪽이 같은
    배포물이라 버전이 어긋날 수 없고, uvx 는 경로에 없다. 대신 진단이 실제로
    답해야 하는 것을 넣는다: 어디에 붙었고 인증이 켜져 있나.

    Args:
        result: 내장 서버가 돌려준 diagnose 결과.
        ctx: Bridge 인스턴스.

    Returns:
        dict: `upwise` 절이 추가된 결과.
    """
    if not isinstance(result, dict):
        return result
    result["upwise"] = {
        "transport": "embedded socket server (no uvx, no external plugin)",
        "host": ctx.client.host,
        "port": ctx.client.port,
        "token_auth": bool(ctx.client.token),
        "bridge": "qgis_bridge.py (UPWISE Chat for QGIS)",
        "exposed_tools": len(ctx.surface.tools),
        "schema_upstream": ctx.surface.provenance.get("upstream", "unknown"),
    }
    return result


def check_layer_features_limit(args):
    """`get_layer_features` 의 limit 을 호출 전에 검사한다 (설계 4-5).

    상류 `helpers.feature_limit_error` 와 **같은 문구**를 쓴다 - 모델이 보던
    거절 문구를 바꾸지 않는다. 왕복 전에 거절하는 이유는 거절 사유가 소켓
    왕복에 의존하지 않기 때문이다. 조용히 깎지 않는 것이 요점이다: 200 을
    요청해 50 을 받으면 모델은 그 50 이 전부라고 읽는다.

    상류가 이 도구에 하던 나머지 하나 - 피처 20개 초과 시 `qgis://cache/{id}`
    자원 URI 부착 - 는 **구현하지 않는다**(설계 4-6·D-B9). `resources/read`·
    URI 템플릿 경로가 이 CLI 에서 미측이고, 제품의 실사용 도구 호출 22회가 그
    경로를 탄 증거가 없다. 대신 `truncate()` 의 하드 상한이 큰 결과를 받는다.

    Raises:
        BridgeError: limit 이 MAX_FEATURE_LIMIT 를 넘었을 때.
    """
    limit = args.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int):
        return
    if limit > MAX_FEATURE_LIMIT:
        raise BridgeError(
            "limit %d exceeds the maximum of %d; page through the rest with "
            "offset" % (limit, MAX_FEATURE_LIMIT))


def socket_timeout_for(name, args, log=None):
    """명령 1건의 소켓 왕복 타임아웃을 정한다 (V32-A53).

    규칙은 하나다: **서버가 예산에서 끊고 브리지는 그보다 늦게 끊는다.**
    `SERVER_BUDGETS` 에 있는 명령은 서버가 `timeout` 인자를 예산으로 그대로
    쓰므로(handlers/processing.py `budget = ... if timeout is None else
    float(timeout)`) 브리지도 같은 값을 읽고 `TIMEOUT_MARGIN` 만 더한다.
    이 함수를 call() 밖으로 꺼낸 이유는 하네스가 소켓 없이 전수 검사할 수
    있게 하려는 것이다.

    인자가 쓸 수 없는 값일 때 서버측 기본 예산으로 되돌리는 이유: 서버도
    `float(timeout)` 이 깨지는 값은 받지 않으므로(그 경우 핸들러가 예외를
    낸다) 브리지가 임의로 해석해 소켓만 늘려 두면 두 시계가 다시 어긋난다.

    Args:
        name: 도구 이름.
        args: 모델이 준 인자 dict (None 허용).
        log: ServerLog. 상한에서 깎았을 때만 쓴다.

    Returns:
        float: 소켓 타임아웃(초).
    """
    budget = SERVER_BUDGETS.get(name)
    if budget is None:
        # 예산 인자가 없는 명령. 고정값 두 단계를 그대로 쓴다.
        return TIMEOUT_LONG if name in LONG_COMMANDS else TIMEOUT_DEFAULT

    requested = (args or {}).get("timeout")
    # bool 을 먼저 걷어낸다 - `float(True)` 는 1.0 이라 통과해 버린다.
    if not isinstance(requested, bool):
        try:
            value = float(requested)
        except (TypeError, ValueError):
            value = None
        # NaN 은 비교가 전부 False 라 이 조건에서 함께 걸러진다.
        if value is not None and value > 0:
            budget = value

    timeout = budget + TIMEOUT_MARGIN
    if timeout > SOCKET_TIMEOUT_CEILING:
        # 표현 한계. 정책이 아니라 소켓 계층 제약이므로 사실만 남긴다.
        if log is not None:
            log.write("TIMEOUT_CEILING",
                      "%s requested=%r socket=%.3f capped=%.3f"
                      % (name, requested, timeout, SOCKET_TIMEOUT_CEILING))
        timeout = SOCKET_TIMEOUT_CEILING
    return timeout


def truncate(text, log):
    """텍스트 본문을 상한에서 자르고 절단 사실을 구조화해 붙인다 (설계 4-6).

    자르기 전 원 바이트를 로그에 남긴다 - 완료 판정 (m) 이 그것을 본다.

    Args:
        text: 직렬화된 결과 텍스트.
        log: ServerLog.

    Returns:
        tuple: (본문, 절단했는가)
    """
    raw = text.encode("utf-8")
    if len(raw) <= MAX_TEXT_BYTES:
        return text, False
    log.write("TRUNCATE", "original=%d limit=%d" % (len(raw), MAX_TEXT_BYTES))
    # 문자 경계에서 끊는다. errors="ignore" 가 잘린 멀티바이트를 버린다.
    head = raw[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
    note = {
        "truncated": True,
        "dropped": len(raw) - MAX_TEXT_BYTES,
        "original_bytes": len(raw),
        "hint": "narrow the request with limit/offset or an expression filter "
                "and call again",
    }
    return head + "\n" + json.dumps(note, ensure_ascii=False), True


# ------------------------------------------------------------------ 브리지 본체

def read_plugin_version(log):
    """플러그인 버전을 `metadata.txt` 에서 읽는다 - QGIS 가 읽는 그 파일이다.

    이 파일은 패키지 루트에 있으므로 `metadata.txt` 가 같은 폴더다. 상수로
    박지 않는 이유는 설계 함정 9 와 같다: 하드코딩한 버전은 릴리스 때마다
    어긋나고, `serverInfo.version` 과 `diagnose` 가 조용히 거짓을 보고한다.

    Returns:
        str: 버전 문자열. 읽을 수 없으면 "unknown".
    """
    import configparser

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata.txt")
    try:
        config = configparser.ConfigParser()
        config.read(path, encoding="utf-8")
        return config.get("general", "version", fallback="unknown")
    except (OSError, configparser.Error) as exc:
        log.write("version_unreadable", "%s (%s)" % (path, exc))
        return "unknown"


class Bridge:
    """MCP 메서드를 받아 내장 서버로 중계한다."""

    def __init__(self, env, log):
        """env 계약을 읽고 자산을 적재한다 (설계 4-3).

        Args:
            env: os.environ.
            log: ServerLog.
        """
        self.log = log
        host = env.get(ENV_HOST) or "127.0.0.1"
        port = env.get(ENV_PORT) or "0"
        token = (env.get(ENV_TOKEN) or "").strip()
        tools_path = env.get(ENV_TOOLS) or ""
        if not tools_path:
            # 자산 경로가 안 왔으면 자기 폴더에서 찾는다. `-I` 라 sys.path 에
            # 스크립트 폴더만 있으므로 __file__ 기준이 유일한 단서다.
            tools_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "qgis_tools.json")
        self.surface = ToolSurface(tools_path, log)
        self.client = SocketClient(host, port, token, log)
        self.version = read_plugin_version(log)

    def preflight(self):
        """기동 시 즉시 접속하고 ping 한다. 실패하면 비정상 종료한다.

        **이것이 게이트 4 를 진짜 end-to-end 단정으로 만든다**(설계 2-3 근거 4).
        상류 브리지는 lazy connect 라서 `mcp_servers connected` 가 "프로세스가
        떴다" 만 뜻했다. 여기서 죽으면 CLI 가 `status=failed` 를 보고하고
        게이트 4 가 하드 FAIL 을 낸다 - 그래야 "지도 제어가 가능한가" 가
        사용자에게 거짓으로 보고되지 않는다.

        Raises:
            SystemExit: 재시도 후에도 못 붙었을 때.
        """
        if self.client.port <= 0:
            self.log.write("FATAL", "no port in %s" % ENV_PORT)
            raise SystemExit(
                "qgis_bridge: %s is not set; the plugin passes the embedded "
                "server's real port" % ENV_PORT)
        if not self.client.token:
            self.log.write("FATAL", "no token in %s" % ENV_TOKEN)
            raise SystemExit(
                "qgis_bridge: %s is not set; the embedded server refuses "
                "unauthenticated peers" % ENV_TOKEN)

        last = None
        for attempt in range(1, CONNECT_ATTEMPTS + 1):
            try:
                result = self.client.send("ping", {}, PREFLIGHT_CONNECT_TIMEOUT)
                self.log.write("PREFLIGHT_OK", "attempt=%d result=%r" % (attempt, result))
                return
            except BridgeError as exc:
                last = exc
                self.log.write("PREFLIGHT_RETRY", "attempt=%d %s" % (attempt, exc))
                if attempt < CONNECT_ATTEMPTS:
                    time.sleep(CONNECT_BACKOFF)
        self.log.write("FATAL", "preflight failed: %s" % last)
        raise SystemExit("qgis_bridge: cannot reach the embedded QGIS server: %s" % last)

    def call(self, name, args):
        """도구 1건 실행. (본문, 오류인가) 를 돌려준다."""
        try:
            args = self.surface.check(name, args)

            # QGIS 측 명령이 없는 하나(설계 E22). 브리지가 로컬에서 답한다.
            if name == "list_qgis_instances":
                return self._local_instances(), False

            if name == "get_layer_features":
                check_layer_features_limit(args)

            # 모델이 준 예산을 소켓에 반영한다(V32-A53). 서버보다 늦게 끊어야
            # 취소 메시지가 socket.timeout 을 앞지른다.
            timeout = socket_timeout_for(name, args, self.log)
            result = self.client.send(name, args, timeout)

            if name == "diagnose":
                result = shape_diagnose(result, self)
            return result, False
        except BridgeError as exc:
            return {"error": str(exc)}, True
        except Exception as exc:  # noqa: BLE001 - 브리지가 죽으면 세션이 degraded 된다
            self.log.write("TOOL_EXCEPTION", "%s %r" % (name, exc))
            return {"error": "bridge error on %s: %r" % (name, exc)}, True

    def _local_instances(self):
        """`list_qgis_instances` 를 로컬에서 답한다 (설계 4-4 끝).

        내장 서버는 하나뿐이고 다중 인스턴스 관리는 비범위다(설계 10장).
        이름을 유지하는 이유는 포스처 R allowlist 41종을 흔들지 않기 위함이다.
        """
        return {
            "instances": [{
                "name": "embedded",
                "host": self.client.host,
                "port": self.client.port,
                "reachable": True,
                "note": "the embedded server inside this QGIS window",
            }],
            "implicit_instance": "embedded",
            "note": "This build serves one embedded instance. There is no "
                    "instance argument to pass.",
        }


# ------------------------------------------------------------ MCP 프로토콜 처리

def send(obj, log):
    """JSON-RPC 한 줄 송신. 개행은 \\n 고정이다."""
    body = json.dumps(obj, ensure_ascii=False)
    log.write("SEND", body[:1200])
    sys.stdout.write(body + "\n")
    sys.stdout.flush()


def tool_result(rid, payload, is_error, log):
    """MCP tools/call 응답 한 건. 본문은 JSON 텍스트 블록 하나다.

    블록이 하나인 것은 설계 4-3 의 규약이다. 상류는 레이어·프로젝트 변경
    도구에 `resource_link` 블록을 하나 더 붙였는데, 그 URI 는 `resources/read`
    로만 읽을 수 있고 **우리는 자원을 구현하지 않는다**(설계 4-6). 읽을 수 없는
    링크를 붙이면 모델이 그 경로를 시도하고 -32601 을 받는다. 텍스트 본문은
    상류와 같다 - 상류도 그 블록은 `json.dumps(result)` 였다.
    """
    text = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, indent=2)
    text, _cut = truncate(text, log)
    return {"jsonrpc": "2.0", "id": rid,
            "result": {"content": [{"type": "text", "text": text}],
                       "isError": bool(is_error)}}


def handle(req, bridge, log):
    """요청 1건 처리. 알림이면 None 을 돌려준다."""
    method = req.get("method", "")
    rid = req.get("id")

    if method == "initialize":
        params = req.get("params") or {}
        # 요청이 준 값을 되돌려주고 없으면 폴백한다(설계 4-3). 우리가 버전을
        # 협상하지 않는 이유는 메서드 6개가 2024-11-05 이후로 안 바뀌어서다.
        ver = params.get("protocolVersion") or PROTOCOL_FALLBACK
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": ver,
                           "capabilities": {"tools": {"listChanged": False}},
                           "serverInfo": {"name": SERVER_NAME,
                                          "version": bridge.version}}}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"tools": bridge.surface.tools}}
    if method == "tools/call":
        params = req.get("params") or {}
        payload, is_err = bridge.call(params.get("name"), params.get("arguments"))
        return tool_result(rid, payload, is_err, log)
    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return {"jsonrpc": "2.0", "id": rid, "result": {key: []}}
    if rid is None:
        # 알림에는 응답하지 않는다. id 없는 요청에 -32601 을 보내면 규약 위반이다.
        return None
    # `server/discover` 가 여기 온다. CLI 가 보내고 -32601 을 정상으로 받는
    # 것이 실측이다(장부 V28-A19 축) - 수집 서버와 같은 처분이다.
    log.write("unknown_method", method)
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": "method not found: %s" % method}}


def main():
    """stdin 의 JSON-RPC 줄을 끝까지 처리한다."""
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdin.reconfigure(encoding="utf-8")
    log = ServerLog(os.environ.get(ENV_LOG, ""))
    log.write("START", "pid=%d python=%s" % (os.getpid(), sys.executable))

    bridge = Bridge(os.environ, log)
    # 기동 시 즉시 접속한다. 실패하면 여기서 비정상 종료한다 - lazy connect 를
    # 쓰지 않는 것이 게이트 4 의 의미를 바꾼다(설계 2-3 근거 4).
    bridge.preflight()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        log.write("RECV", line[:1200])
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if not isinstance(req, dict):
            continue
        try:
            resp = handle(req, bridge, log)
        except Exception as exc:  # noqa: BLE001 - 핸들러 예외로 브리지가 죽지 않는다
            log.write("HANDLER_ERR", repr(exc))
            continue
        if resp is not None:
            send(resp, log)
    log.write("STOP", "stdin closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
