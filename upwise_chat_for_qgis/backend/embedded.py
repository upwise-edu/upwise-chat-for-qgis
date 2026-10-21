"""내장 QGIS 소켓 서버의 수명주기 (0.3.0, 설계 docs/5 3-2·5-3).

Copyright (c) 2026 UPWISE. GPL-2.0-or-later.

무엇을 하나
    `mcpserver/` 의 소켓 서버를 띄우고 내리고, 세션 토큰을 내고, bind 후
    회수한 실포트를 들고 있는다. 상류 `plugin.py` 의 해당 부분을 가져오지
    않고 새로 쓴 이유는 그쪽이 **우리 제품의 정책이 아니라 상류의 UI** 라서다
    (툴바 액션·Run MCP 버튼·포트 스핀박스·아이콘 배지, 설계 3-2). 우리 독이
    그 자리이고, UI 가 없으니 더 짧다.

여기 없는 것
    독 배선·전제조건 문구·`--mcp-config` 조립은 **S10c 의 다른 파일**이 한다
    (`plugin.py`·`backend/posture.py`·`ui/`). 이 모듈은 상태와 자체 점검만
    들고 있고 UI 를 모른다.

자체 점검 (0.3.0 S10c, 설계 5-4 결정 D-B6 (b))
    0.2.x 는 "연결됐는가" 를 `qgis-connect-check` **스킬**에 물었다 - 유료
    1턴이고, 그 스킬은 남의 플러그인 버전을 조회해 3갈래로 보고했다. 내장
    서버는 우리 것이므로 플러그인이 **직접** 안다: `self_check()` 가 서버
    핸들러를 불러 포트·버전·레이어 수를 돌려준다. 모델 턴 0, 유료 토큰 0,
    결정적이다.

    **자기 소켓에 접속하지 않는다**(설계 함정 1). 서버는 GUI 스레드의
    `QTimer` 로 응답하므로 같은 스레드에서 블로킹 connect/recv 를 하면
    응답할 타이머가 그 스레드에 묶여 **교착**한다. 핸들러 직접 호출이
    소켓을 타지 않는 유일한 길이다.

토큰
    플러그인 적재마다 새로 난다. `UPWISE_QGIS_TOKEN` 으로 이 프로세스 환경에
    둔다 - 상류가 쓰는 `QGIS_MCP_TOKEN` 이 아니다. 같은 QGIS 프로세스에
    사용자의 상류 플러그인이 있으면 그쪽이 `QGIS_MCP_TOKEN` 을 매 명령마다
    다시 읽으므로, 그 이름을 쓰면 우리가 남의 서버 인증을 켜 버리고 그쪽
    uvx 피어가 토큰을 몰라 끊긴다(mcpserver/VENDOR.md 수정 10).

    **토큰의 한계를 과장하지 않는다.** 토큰은 `--mcp-config` 의 per-server env
    로 설정 파일에 평문으로 간다. 같은 사용자로 도는 프로세스에 대해서는
    경계가 아니다 - 상류도 같은 말을 한다. 토큰이 막는 것은 (a) 다른 사용자,
    (b) 포트를 훑는 비표적 접속이다. 같은 사용자 경로를 좁히는 것은 토큰이
    아니라 **노출 집합 축소와 서버측 거절**이다(`mcpserver/exposure.py`).

포트
    기본은 0(ephemeral)이고 bind 후 실포트를 회수한다. 9876 을 기본값으로
    쓰지 않는 이유는 `SO_EXCLUSIVEADDRUSE` 로 둘이 못 잡아서다 - 우리가 먼저
    잡으면 사용자의 Run MCP 가 실패하고, 사용자 눈에는 우리 플러그인이 남의
    기능을 깬 것으로 보인다(설계 함정 4). 고급 사용자를 위해 QgsSettings 키로
    고정할 수 있게는 두었다.
"""

import json
import os
import secrets
import socket
import time

from qgis.core import QgsMessageLog, QgsSettings
from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..mcpserver.compat import MSG_CRITICAL, MSG_INFO
from ..mcpserver.constants import SETTINGS_PREFIX
from ..mcpserver.server import TOKEN_ENV, QgisMCPServer
from ..mcpserver.wire import HEADER_STRUCT, RECV_CHUNK_SIZE, frame

LOG_TAG = "UPWISE Chat"

# 호스트는 고정이다. 비loopback 은 서버가 거절하고(상류 유지분), 애초에
# 내장 서버를 네트워크에 낼 이유가 없다.
HOST = "127.0.0.1"

# 포트 고정용 고급 설정 키. 기본값 0 은 ephemeral 이다. 독에 노출하지 않는다 -
# 바꿔야 하는 사용자는 터미널에서 내장 서버에 붙으려는 경우뿐이고 그것은
# 선택 항목이다(설계 5-3).
PORT_SETTING_KEY = "%s/port" % SETTINGS_PREFIX

# 세션 토큰 길이(바이트). token_urlsafe 는 이것을 base64url 로 늘린다.
TOKEN_BYTES = 32

# ----------------------------------------------------------------------
# 소켓 프로브 (0.3.x UI 패스 2차 U6)
#
# 왜 self_check 로는 안 되는가
#     `self_check()` 는 핸들러를 **직접** 부른다(위 "자체 점검" 참조). 그것이
#     재는 것은 "서버 객체가 살아 있고 가드가 비었는가" 다. 소켓이 실제로
#     응답하는지는 재지 못한다 - 그래서 U6 이 요구하는 경고 두 축을 가를 수
#     없다. ① 서버 무응답(소켓은 열려 있는데 답이 안 온다) ② 포트 해제 후 타
#     프로세스 재점유(답은 오는데 우리 서버의 답이 아니다). 둘 다 **소켓을
#     타야만** 보이는 사실이다. 그래서 축을 따로 신설했다.
#
# 왜 GUI 스레드에서 돌리지 않는가
#     설계 함정 1 이 그 교착을 적어 두었다. 서버는 GUI 스레드의 QTimer 로
#     응답하므로 같은 스레드에서 블로킹 connect/recv 를 하면 응답할 타이머가
#     그 스레드에 묶인다. 프로브는 `PortProbe`(QThread) 안에서만 돈다.
#     `probe_once` 는 그래서 **stdlib 와 wire 프레이밍만** 쓴다 - QGIS 객체를
#     만지는 코드가 섞이면 그 스레드에서 쓸 수 없다.
# ----------------------------------------------------------------------

# 프로브 판정 5값. 경고 두 축을 그대로 값으로 옮긴 것이다.
#     OK         우리 서버가 우리 토큰을 받아 success 로 답했다
#     DOWN       아무도 그 포트를 듣지 않는다            (축 ①)
#     NO_ANSWER  듣기는 하는데 한 프레임도 못 받았다      (축 ①)
#     FOREIGN    답은 왔는데 우리 서버의 답이 아니다      (축 ②)
#     OFF        우리가 서버를 띄우지 않았다 (경고가 아니다)
PROBE_OK = "OK"
PROBE_DOWN = "DOWN"
PROBE_NO_ANSWER = "NO_ANSWER"
PROBE_FOREIGN = "FOREIGN"
PROBE_OFF = "OFF"

# 프로브 소켓 타임아웃(초). loopback 왕복은 밀리초 단위이므로 0.8 초는 "서버가
# 긴 디스패치에 묶였다" 를 가리기에 충분히 길고, 백그라운드 스레드의 수명을
# 사용자가 눈치챌 만큼 늘리지는 않는다.
PROBE_TIMEOUT_S = 0.8

# 프로브가 보내는 명령. `ping` 은 노출 집합에 있고(mcpserver/exposure.py) 인자가
# 없으며 프로젝트 상태를 바꾸지 않는다. 브리지의 preflight 도 같은 것을 쓴다.
PROBE_COMMAND = "ping"

# 토큰이 틀렸을 때 서버가 돌려주는 문구의 판별 조각. 전문을 박지 않는 이유는
# 상류 문구가 바뀔 수 있기 때문이고, 이 판정은 **어차피 FOREIGN 한 값**으로만
# 쓰인다(어느 쪽이든 우리 토큰을 모르는 상대다).
PROBE_AUTH_MARK = "Authentication failed"


def _probe_recv_exactly(sock, size):
    """정확히 size 바이트를 읽는다. 중간에 끊기면 None.

    `qgis_bridge.SocketClient._recv_exactly` 와 같은 일을 하지만 예외를 올리지
    않고 None 을 돌려준다 - 프로브는 "못 읽었다" 를 판정값으로 바꿀 뿐이고,
    브리지처럼 호출을 실패로 끝낼 필요가 없다.

    Args:
        sock: 연결된 소켓.
        size: 읽을 바이트 수.

    Returns:
        bytes 또는 None.
    """
    chunks = []
    got = 0
    while got < size:
        chunk = sock.recv(min(RECV_CHUNK_SIZE, size - got))
        if not chunk:
            return None
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def probe_once(host, port, token, timeout=PROBE_TIMEOUT_S):
    """소켓으로 `ping` 한 번 왕복하고 판정 하나를 돌려준다 (U6).

    **GUI 스레드에서 부르지 않는다**(모듈 머리 주석의 교착). `PortProbe.run`
    이 유일한 호출 지점이고, 하네스는 임시 소켓 서버를 자기가 띄워 이 함수를
    직접 재다.

    프레이밍은 `mcpserver/wire` 의 것을 그대로 쓴다. 같은 형식을 여기서 다시
    적으면 서버가 형식을 바꿀 때 프로브만 조용히 틀린다.

    Args:
        host: 접속 호스트.
        port: 접속 포트. 0 이하면 접속하지 않고 OFF 를 돌려준다.
        token: 세션 토큰. **돌려주는 dict 에는 담지 않는다.**
        timeout: 소켓 타임아웃(초).

    Returns:
        dict: verdict(PROBE_*), port, why(사용자에게 보일 수 있는 한 줄),
            elapsed_ms. 토큰 값은 어느 칸에도 들어가지 않는다.
    """
    t0 = time.time()
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 0
    if port <= 0:
        return {"verdict": PROBE_OFF, "port": 0,
                "why": "내장 서버가 떠 있지 않습니다", "elapsed_ms": 0.0}

    request = {"type": PROBE_COMMAND, "params": {}}
    # 토큰은 모든 명령에 붙는다. 없으면 서버가 거절하고, 그 거절은 FOREIGN 과
    # 같은 모양이라 판정이 흐려진다 - 그래서 빈 토큰도 그대로 보낸다.
    if token:
        request["token"] = token
    payload = json.dumps(request, ensure_ascii=False).encode("utf-8")

    sock = None
    connected = False
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        connected = True
        sock.settimeout(timeout)
        sock.sendall(frame(payload))
        header = _probe_recv_exactly(sock, HEADER_STRUCT.size)
        raw = None
        if header is not None:
            raw = _probe_recv_exactly(sock, HEADER_STRUCT.unpack(header)[0])
    except socket.timeout:
        # 연결 전 타임아웃은 "아무도 없다" 에 가깝고(loopback), 연결 뒤
        # 타임아웃은 "듣지만 답을 못 한다" 다. 두 축을 섞지 않는다.
        verdict = PROBE_NO_ANSWER if connected else PROBE_DOWN
        return {"verdict": verdict, "port": port,
                "why": "%.1f초 안에 응답이 없습니다" % timeout,
                "elapsed_ms": (time.time() - t0) * 1000.0}
    except OSError as exc:
        verdict = PROBE_NO_ANSWER if connected else PROBE_DOWN
        return {"verdict": verdict, "port": port, "why": "%r" % (exc,),
                "elapsed_ms": (time.time() - t0) * 1000.0}
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    elapsed = (time.time() - t0) * 1000.0
    if not raw:
        return {"verdict": PROBE_NO_ANSWER, "port": port,
                "why": "응답 프레임이 끊겼습니다", "elapsed_ms": elapsed}
    try:
        response = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        # 우리 프로토콜이 아니다. 같은 번호를 다른 프로그램이 듣고 있다.
        return {"verdict": PROBE_FOREIGN, "port": port,
                "why": "우리 서버의 응답 형식이 아닙니다", "elapsed_ms": elapsed}
    if not isinstance(response, dict):
        return {"verdict": PROBE_FOREIGN, "port": port,
                "why": "우리 서버의 응답 형식이 아닙니다", "elapsed_ms": elapsed}
    if response.get("status") == "success":
        return {"verdict": PROBE_OK, "port": port, "why": "정상",
                "elapsed_ms": elapsed}
    message = str(response.get("message") or "")
    if PROBE_AUTH_MARK in message:
        return {"verdict": PROBE_FOREIGN, "port": port,
                "why": "이 포트의 서버가 우리 세션 토큰을 받지 않습니다",
                "elapsed_ms": elapsed}
    return {"verdict": PROBE_FOREIGN, "port": port,
            "why": message or "서버가 오류를 보고했습니다", "elapsed_ms": elapsed}


class PortProbe(QThread):
    """프로브 1회를 GUI 스레드 밖에서 돌리는 스레드 (U6).

    왜 스레드 하나가 1회만 도는가
        주기는 UI 가 QTimer 로 정한다(렌더 틱 예산이 UI 쪽 사실이다). 스레드가
        자기 루프를 들고 있으면 독을 닫은 뒤에도 소켓을 때리고, 멈추라는 신호를
        주고받는 코드가 또 필요해진다. 1회 실행 뒤 끝나는 스레드가 더 짧다.

    시그널 하나를 낸다.

        result_ready(object)  `probe_once` 의 판정 dict. 토큰 값은 없다.
    """

    result_ready = pyqtSignal(object)

    def __init__(self, host, port, token, timeout=PROBE_TIMEOUT_S, parent=None):
        """접속 좌표만 잡는다. 소켓은 `run()` 에서 연다."""
        super().__init__(parent)
        self._host = host
        self._port = port
        self._token = token
        self._timeout = timeout

    def run(self):
        """프로브 1회. 예외도 판정으로 바꿔 올린다.

        예외를 올리면 Qt 가 스레드 밖에서 그것을 받지 못해 조용히 사라지고,
        UI 는 "확인 중" 에서 멈춘 채로 남는다.
        """
        try:
            result = probe_once(self._host, self._port, self._token,
                                self._timeout)
        except Exception as exc:  # noqa: BLE001 - 프로브 실패가 UI 를 멈추지 않는다
            result = {"verdict": PROBE_NO_ANSWER, "port": self._port,
                      "why": "%r" % (exc,), "elapsed_ms": 0.0}
        self.result_ready.emit(result)


class EmbeddedServer:
    """내장 소켓 서버 하나의 수명주기.

    플러그인 인스턴스마다 하나다. 서버 객체를 둘 만들어도 재진입 가드는
    프로세스 전역이므로(VENDOR.md 수정 7) 디스패치가 겹치지 않는다.
    """

    def __init__(self, iface=None, on_clients_changed=None):
        """상태만 잡는다. 소켓은 `start()` 에서 연다.

        Args:
            iface: QGIS iface. 핸들러가 캔버스를 만질 때 쓴다.
            on_clients_changed: 클라이언트 수가 바뀔 때 부를 콜백.
        """
        self.iface = iface
        self.on_clients_changed = on_clients_changed
        self.server = None
        self.token = ""
        self.start_error = None
        # 도는 프로브 스레드 하나(U6). 참조를 들고 있지 않으면 Python 이
        # 스레드 객체를 수거해 C++ 쪽이 먼저 사라진다.
        self._probe = None

    # ------------------------------------------------------------- 상태 조회

    @property
    def running(self):
        """소켓이 열려 있고 타이머가 도는가."""
        return bool(self.server is not None and self.server.running)

    @property
    def port(self):
        """bind 후 회수한 실포트. 안 떴으면 0."""
        return int(self.server.port) if self.running else 0

    def bridge_env(self):
        """브리지에 넘길 per-server env (설계 4-3).

        조립은 S10c 의 `posture` 가 한다. 여기서는 **우리가 아는 값만** 돌려
        준다 - 로그 경로와 자산 경로는 플러그인 프로필을 아는 쪽이 채운다.

        Returns:
            dict: 호스트·포트·토큰. 서버가 안 떴으면 빈 dict - 뜨지 못할
                설정을 적으면 `status=failed` 가 사유를 흐린다(설계 4-3).
        """
        if not self.running:
            return {}
        return {
            "UPWISE_QGIS_HOST": HOST,
            "UPWISE_QGIS_PORT": str(self.port),
            TOKEN_ENV: self.token,
        }

    # --------------------------------------------------------- 소켓 프로브 (U6)

    def probe_target(self):
        """프로브가 접속할 좌표 (U6).

        Returns:
            dict: host·port. 서버가 안 떴으면 빈 dict. **토큰은 담지 않는다** -
                이 값은 독이 읽어 표시에 쓰므로, 토큰이 필요한 쪽은
                `start_probe` 안에서만 그것을 본다.
        """
        if not self.running:
            return {}
        return {"host": HOST, "port": self.port}

    def start_probe(self, on_result):
        """소켓 프로브 1회를 백그라운드 스레드로 띄운다 (U6).

        **여기서 소켓을 열지 않는다.** 이 메서드는 GUI 스레드에서 불리고, 그
        스레드가 서버의 응답 타이머를 들고 있다(설계 함정 1). 소켓 작업은
        `PortProbe.run` 안에서만 일어난다.

        Args:
            on_result: callable(dict). 판정 dict 하나를 받는다. 서버가 꺼져
                있으면 소켓을 타지 않고 **그 자리에서** OFF 판정으로 부른다 -
                스레드를 띄울 이유가 없고, UI 가 "확인 중" 에서 멈추지도
                않아야 한다.

        Returns:
            bool: 스레드를 띄웠는가. 꺼져 있거나 앞 프로브가 아직 돌면 False.
        """
        if not callable(on_result):
            return False
        if not self.running:
            on_result({"verdict": PROBE_OFF, "port": 0,
                       "why": self.start_error or "내장 서버가 꺼져 있습니다",
                       "elapsed_ms": 0.0})
            return False
        # 겹쳐 띄우지 않는다. 앞 프로브가 타임아웃을 기다리는 중이면 이번 틱은
        # 건너뛴다 - 느린 서버에 스레드를 쌓는 것이 더 나쁘다.
        previous = self._probe
        if previous is not None:
            try:
                if previous.isRunning():
                    return False
            except RuntimeError:
                # 이미 지워진 QThread 래퍼. 다음 줄에서 새것으로 갈린다.
                pass
        probe = PortProbe(HOST, self.port, self.token)
        probe.result_ready.connect(on_result)
        self._probe = probe
        probe.start()
        return True

    # ------------------------------------------------------------- 자체 점검

    def self_check(self):
        """내장 서버에 직접 물어 한 줄 보고를 만든다 (설계 5-4 (b)·8-3 (j)).

        소켓을 타지 않는다. 서버 객체의 `diagnose` 핸들러를 **그대로 부른다** -
        `@command` 로 등재된 메서드이고 소켓 경로와 같은 코드다. 그래서
        "점검은 통과하는데 모델 호출은 실패" 같은 갈림이 생기지 않는다.

        디스패치 가드를 존중한다. 재진입 가드가 켜져 있으면(다른 호출이 핸들러
        안에서 이벤트 루프를 펌프하는 중) 점검을 **건너뛴다**. 끼어들면
        상류가 자기 가드로 막으려 했던 교차 디스패치를 우리가 만든다
        (설계 2-5·함정 2).

        Returns:
            dict: state 는 "OK"·"BUSY"·"DOWN"·"ERROR" 중 하나.
                text 는 독에 그대로 띄우는 한 줄. detail 은 진단 로그용이고
                **토큰 값은 들어가지 않는다**(on/off 만).
        """
        if not self.running:
            return {
                "state": "DOWN",
                "text": "내장 QGIS 서버가 꺼져 있습니다: %s" % (
                    self.start_error or "사유 미기록"),
                "detail": {"running": False, "why": self.start_error or ""},
            }

        # 가드 조회 자체가 예외를 내면 점검이 아니라 버그다 - 그 경우도
        # 보고로 끝낸다(점검이 QGIS 를 멈추게 하지 않는다).
        try:
            busy = bool(self.server._in_dispatch)  # noqa: SLF001 - 상류 공개 속성
        except Exception as exc:  # noqa: BLE001
            return {"state": "ERROR",
                    "text": "내장 서버 상태를 읽지 못했습니다: %r" % (exc,),
                    "detail": {"running": True, "why": repr(exc)}}
        if busy:
            return {
                "state": "BUSY",
                "text": "내장 QGIS 서버가 작업 중입니다. 잠시 뒤 다시 누르세요.",
                "detail": {"running": True, "in_dispatch": True,
                           "port": self.port},
            }

        try:
            result = self.server.diagnose()
        except Exception as exc:  # noqa: BLE001 - 핸들러 예외도 보고로 끝낸다
            QgsMessageLog.logMessage(
                "self check raised: %r" % (exc,), LOG_TAG, MSG_CRITICAL)
            return {"state": "ERROR",
                    "text": "내장 서버 점검이 실패했습니다: %r" % (exc,),
                    "detail": {"running": True, "why": repr(exc)}}

        checks = {}
        for entry in (result or {}).get("checks") or ():
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                checks[entry["name"]] = entry.get("detail")
        qgis_version = (checks.get("qgis") or {}).get("qgis_version") \
            if isinstance(checks.get("qgis"), dict) else None
        layer_count = (checks.get("project") or {}).get("layer_count") \
            if isinstance(checks.get("project"), dict) else None
        plugin_version = checks.get("plugin_version")
        detail = {
            "running": True,
            "port": self.port,
            "token": "on" if self.token else "off",
            "status": (result or {}).get("status"),
            "qgis_version": qgis_version,
            "plugin_version": plugin_version,
            "layer_count": layer_count,
            "clients": checks.get("connected_clients"),
        }
        text = ("내장 QGIS 서버 정상 - 포트 %d, 토큰 on, 플러그인 %s, "
                "QGIS %s, 레이어 %s개" % (
                    self.port, plugin_version or "unknown",
                    qgis_version or "unknown",
                    layer_count if layer_count is not None else "?"))
        return {"state": "OK", "text": text, "detail": detail}

    # --------------------------------------------------------------- 수명주기

    def start(self):
        """토큰을 내고 소켓을 연다.

        Returns:
            bool: 떴으면 True. 실패 사유는 `start_error` 에 남는다.
        """
        if self.running:
            return True
        self.start_error = None

        # 적재마다 새 토큰이다. 재사용하면 이전 세션의 설정 파일에 남은 토큰이
        # 계속 유효해진다.
        self.token = secrets.token_urlsafe(TOKEN_BYTES)
        os.environ[TOKEN_ENV] = self.token

        port = self._configured_port()
        self.server = QgisMCPServer(
            host=HOST, port=port, iface=self.iface,
            on_clients_changed=self.on_clients_changed)
        try:
            started = self.server.start()
        except Exception as exc:  # noqa: BLE001 - 적재가 예외로 멈추면 독이 안 뜬다
            self.start_error = "embedded server raised on start: %r" % (exc,)
            QgsMessageLog.logMessage(self.start_error, LOG_TAG, MSG_CRITICAL)
            self._forget()
            return False

        if not started:
            # 서버가 사유를 적어 둔다(포트 점유·토큰 부재·비loopback).
            self.start_error = self.server.start_error or "embedded server did not start"
            QgsMessageLog.logMessage(self.start_error, LOG_TAG, MSG_CRITICAL)
            self._forget()
            return False

        QgsMessageLog.logMessage(
            "embedded QGIS server on %s:%d, token auth on" % (HOST, self.port),
            LOG_TAG, MSG_INFO)
        return True

    def stop(self):
        """소켓·타이머·체크포인트 임시폴더를 내리고 토큰을 지운다.

        `server.stop()` 이 소켓·타이머·클라이언트·체크포인트 임시폴더를 전부
        정리한다(상류 코드 그대로). 우리가 더 하는 것은 환경에서 토큰을 빼는
        것뿐이다 - 남겨 두면 다음 적재의 서버가 뜨기 전에 낡은 토큰이 유효한
        것처럼 보인다.
        """
        if self.server is not None:
            try:
                self.server.stop()
            except Exception as exc:  # noqa: BLE001 - unload 가 예외로 멈추면 안 된다
                QgsMessageLog.logMessage(
                    "embedded server raised on stop: %r" % (exc,), LOG_TAG, MSG_CRITICAL)
        # 도는 프로브 스레드를 남기지 않는다(U6). unload 뒤에 스레드가 살아
        # 있으면 Qt 가 종료 시점에 경고를 내고, 그 스레드가 이미 닫힌 포트에
        # 붙으려 한다. 타임아웃의 두 배까지만 기다린다.
        probe = self._probe
        if probe is not None:
            try:
                probe.wait(int(PROBE_TIMEOUT_S * 2000))
            except RuntimeError:
                pass
            self._probe = None
        self._forget()

    def _forget(self):
        """서버 참조와 토큰을 버린다."""
        self.server = None
        self.token = ""
        os.environ.pop(TOKEN_ENV, None)

    @staticmethod
    def _configured_port():
        """고급 설정에 고정 포트가 있으면 그것, 없으면 0(ephemeral).

        QgsSettings 접두사는 우리 것이다(`upwise_chat/embedded_server`).
        상류의 `qgis_mcp/port` 를 읽지도 쓰지도 않는다 - 그쪽은 사용자가
        설치한 플러그인의 설정이다(VENDOR.md 수정 1).
        """
        try:
            value = QgsSettings().value(PORT_SETTING_KEY, 0, type=int)
        except Exception:  # noqa: BLE001 - 설정 읽기 실패가 기동을 막지 않는다
            return 0
        # 1024 미만은 특권 포트다. 0 과 유효 범위만 받는다.
        if value and 1024 <= int(value) <= 65535:
            return int(value)
        return 0
