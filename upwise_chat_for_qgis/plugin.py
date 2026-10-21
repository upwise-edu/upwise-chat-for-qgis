"""UPWISE Chat for QGIS 플러그인 본체.

이 모듈이 하는 일은 네 가지뿐이다.

    1. 전용 툴바 1개와 플러그인 메뉴 항목 1개 등록 (체크 가능한 토글 액션)
    2. 독 위젯을 오른쪽 독 영역에 등록
    3. 액션 체크 상태와 독 가시성 양방향 동기화
    4. unload() 에서 독의 백엔드를 끝내고 시그널, 독, 액션을 전부 되돌림

채팅 UI 는 독(ui/dock.py)이 가지고 있다. S5 가 여기에 붙인 것은 **백엔드 공장**
하나다. 공장이 포스처(설계 3-3)와 argv(5-1), MCP 설정 파일, cwd 를 묶어
SpawnSpec 을 만든다. 독은 claude 실행 파일을 직접 찾지 않는다.

S5 가 꽂는 지점 3개(설계 10-2 S5-2).
    1. UpwiseChatDock(backend_factory=...) 주입
    2. denial_retry_requested -> dock.elevate_and_resend + set_denial_retry_enabled(True)
    3. set_cwd(spec.cwd)

S6 이 붙인 것은 꽂는 지점 하나다. `dock.set_prerequisites(self.prereq)`.
탐지 객체는 독보다 오래 살아야 하므로(cwd 가 바뀌면 다시 계산한다, 설계 6-3)
플러그인이 소유하고 독은 읽는다.

0.2.1 이 붙인 것도 꽂는 지점 하나다. `dock.refresh_keys_state()`.
키 설정 상태(값이 아니라 "있는가")를 적재 시 1회 읽어 레다크터와 전제조건에
반영한다. 키 **값**을 만지는 코드는 backend/keystore 하나이고, 여기서 로그에
적는 것은 `keystore.summary()` 의 불리언뿐이다(설계 docs/2 5-2).

0.3.0 이 붙인 것은 수명주기 하나와 꽂는 지점 하나다(설계 docs/5 S10c).
    수명주기: `backend.embedded.EmbeddedServer` 를 적재에서 띄우고 unload 에서
    내린다. 포트는 ephemeral 이고 토큰은 적재마다 새로 난다. `_make_spec` 이
    그 접속 좌표를 `--mcp-config` 의 `qgis` 항목 env 로 넘긴다 - 그 항목이
    0.2.x 의 `uvx --from <github zip>` 을 대체한 **자작 브리지**다.
    꽂는 지점: `dock.set_self_check(server.self_check)`. [연결 점검] 이 모델을
    타지 않고 내장 서버 핸들러를 직접 불러 답한다(유료 1턴 -> 0턴).

    그리고 `-I` 부트 프로브를 `initGui()` 에서 **워커 스레드로 내렸다**
    (설계 함정 15). 0.2.x 에서 그것은 적재 중 동기 `subprocess.run` 이었고,
    실패해도 수집만 꺼지는 소프트 축이라 비용이 보이지 않았다. 같은
    인터프리터가 지도 제어의 전제가 되면 "적재가 멈춘 것처럼 보이는" 경로가
    된다. 기다림은 첫 전송 경로(`_await_python`)로 옮겼다.

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog, 중첩 이벤트 루프.
모달은 자동화를 정지시키므로 골격 단계에서도 쓰지 않는다. 상태 보고는
QgsMessageLog 로만 한다.

설계 정본: docs/1.mvp_design_v1.md 7-1(독 레이아웃), 7-4(리포 레이아웃), 10(S1)
"""

import os
from pathlib import Path

from qgis.core import Qgis, QgsMessageLog, QgsProject
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QIcon

# NOTE(Claude): Qt6 에서 QAction 은 QtGui 로 옮겨갔다. 이 플러그인은 Qt5 에서만
# 검증됐고 metadata 에 supportsQt6 를 선언하지 않는다(설계 7-4, D16). Qt6 지원을
# 선언하기 전에 이 import 경로를 재확인한다.
from qgis.PyQt.QtWidgets import QAction

from .backend import (adapter_registry, detect, embedded, keystore, posture,
                      process, skillbundle)
from .backend.logbook import qgis_profile_root
from .ui.dock import UpwiseChatDock

# QgsMessageLog 패널에서 이 플러그인 메시지를 묶는 태그.
LOG_TAG = "UPWISE Chat"

# Plugins 메뉴 하위 그룹 이름. removePluginToMenu 가 같은 문자열로 짝을 찾으므로
# 등록과 제거가 반드시 같은 상수를 써야 한다.
MENU_GROUP = "UPWISE Chat for QGIS"

ACTION_TEXT = "UPWISE Chat"
ACTION_TOOLTIP = "UPWISE Chat 독을 열거나 닫는다"

# 전용 툴바(0.3.1). 공용 플러그인 툴바에 아이콘만 얹으면 "보기 > 툴바" 목록에
# 이 제품 항목이 없어서 사용자가 툴바를 꺼내거나 숨길 수 없다(사용자 실기 보고
# 2026-10-12). 제목은 그 목록에 그대로 보이는 사용자 노출 문구다(U15).
TOOLBAR_TITLE = "UPWISE Chat"
# objectName 이 없으면 QGIS 가 창 상태를 저장할 때 경고를 내고 툴바 위치가
# 다음 실행에 복원되지 않는다. 등록과 제거가 같은 이름을 봐야 하므로 상수다.
TOOLBAR_OBJECT_NAME = "UpwiseChatToolbar"

# metadata.txt 의 icon= 과 같은 상대경로를 가리킨다. 둘이 어긋나면 플러그인
# 관리자 아이콘과 툴바 아이콘이 달라진다.
ICON_RELPATH = "resources/icon.png"

# 플러그인이 소유하는 MCP 설정 파일 위치(QGIS 사용자 프로필 아래).
# 사용자 등록본을 상속하지 않는다 - 버전 불일치 시 세션이 degraded 를 보고한
# 강의 실측이 있다(설계 5-3).
MCP_CONFIG_SUBPATH = ("upwise_chat", "qgis_mcp.json")

# 첫 spawn 에서 인터프리터 프로브 결과를 기다리는 상한(ms). 0.3.0.
#
# 프로브는 `initGui()` 를 블록하지 않게 워커 스레드로 내렸다(설계 함정 15).
# 그런데 `_make_spec` 은 그 값이 **있어야** `qgis` 서버 항목을 쓸 수 있고,
# 없으면 게이트 4 가 하드 FAIL 을 내 입력이 막힌다. 그래서 첫 전송 경로에서만
# 짧게 기다린다. 성공 경로는 밀리초 단위이므로(QGIS 번들 파이썬의 stdlib
# import 하나다) 실제로는 거의 즉시 지나간다.
#
# 적재 시점이 아니라 **전송 시점**에 기다리는 것이 요점이다 - 플러그인
# 적재가 멈춘 것처럼 보이는 경로를 없애는 것이 이 변경의 목적이었다.
PYTHON_PROBE_WAIT_MS = 20000


class PythonProbe(QThread):
    """`-I` 부트 프로브를 UI 스레드 밖에서 돌린다(0.3.0, 설계 함정 15).

    0.2.x 는 `detect.Prerequisites.__init__` 안에서 동기로 돌렸고, 그것은
    `initGui()` -> `subprocess.run(..., timeout=60)` x 후보 수였다. 그때는
    실패해도 수집만 꺼지는 소프트 축이라 비용이 보이지 않았다. 0.3.0 은 같은
    인터프리터를 **지도 제어의 전제**로 올리므로(설계 5-2) 같은 블로킹이
    "플러그인 적재가 멈췄다" 로 보인다.

    `process.py` 의 리더 스레드와 같은 패턴이다. PyQGIS 를 만지지 않으므로
    (해석은 경로 문자열과 `subprocess` 뿐) 스레드에서 안전하다.
    """

    resolved = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        """결과 칸을 비워 둔다."""
        super().__init__(parent)
        # 시그널 **말고도** 결과를 여기 둔다. 첫 전송 경로가 `wait()` 로
        # 블록하면 큐에 쌓인 시그널이 그 동안 배달되지 않으므로(같은 스레드),
        # 그 경로는 이 속성을 직접 읽는다. 둘이 같은 값을 쓰므로 어느 쪽이
        # 먼저 와도 결과가 같다.
        self.result = None

    def run(self):
        """해석 1회. 결과를 속성에 두고 시그널로도 올린다."""
        try:
            status, path, why = detect.resolve_embedded_python()
        except Exception as exc:  # noqa: BLE001 - 프로브 예외가 적재를 깨지 않는다
            status, path, why = detect.MISSING, "", "probe raised %r" % (exc,)
        self.result = (str(status), str(path), str(why))
        self.resolved.emit(str(status), str(path), str(why))


class UpwiseChatPlugin:
    """QGIS 플러그인 객체. QGIS 는 initGui 와 unload 만 호출한다."""

    def __init__(self, iface):
        """참조만 잡아 둔다. 위젯 생성은 initGui 에서 한다.

        Args:
            iface: QgisInterface 인스턴스.
        """
        self.iface = iface
        self.action = None
        # 전용 툴바(0.3.1). initGui 에서 만들고 unload 에서 지운다. 플러그인이
        # 들고 있어야 재적재에서 같은 툴바가 둘 생기는 것을 막을 수 있다.
        self.toolbar = None
        self.dock = None
        # 탐지 결과는 독보다 오래 산다. cwd 가 바뀌면 프리셋 판정을 다시 계산해야
        # 하므로(설계 6-3) 플러그인이 들고 있는다.
        self.prereq = None
        # 내장 QGIS 소켓 서버(0.3.0). 플러그인 수명과 같다 - 적재에서 띄우고
        # unload 에서 내린다. 포트와 토큰이 여기 있고 `_make_spec` 이 그것을
        # 브리지 env 로 넘긴다.
        self.server = None
        # 인터프리터 부트 프로브 스레드(0.3.0). unload 에서 합류시킨다.
        self.probe = None
        # 백엔드 어댑터(0.5.5, docs/7 2-10). 제품 조립 지점이 이 하나를 보고
        # argv·탐지·입력 직렬화·게이트를 전부 가져간다. 어댑터는 상태를 들지
        # 않으므로 레지스트리의 공유 인스턴스를 그대로 쓴다.
        #
        # GPT 모드가 들어오면 `adapter_registry.default_name()` 이 사용자
        # 설정을 읽게 되고, 이 줄은 그대로다(`get(None)` 이 기본 백엔드로
        # 접힌다).
        self.backend_adapter = adapter_registry.get(
            adapter_registry.default_name())

    # ------------------------------------------------------------------
    # QGIS 수명주기
    # ------------------------------------------------------------------

    def initGui(self):  # noqa: N802 - QGIS 가 요구하는 고정 이름
        """툴바/메뉴 액션과 독을 등록한다.

        독을 여기서 만들고 숨겨 둔다. 지연 생성(첫 토글에서 생성)으로 하면
        unload 경로가 "만들어졌는가" 에 따라 갈라져 왕복 테스트의 분기가 늘어난다.
        백엔드 프로세스는 이 시점에 띄우지 않는다(설계 2-1: 첫 메시지 또는
        연결 버튼에서 spawn). 공장만 넘기고 spawn 은 첫 전송에서 일어난다.
        """
        self.action = QAction(self._icon(), ACTION_TEXT, self.iface.mainWindow())
        self.action.setObjectName("UpwiseChatToggleAction")
        self.action.setToolTip(ACTION_TOOLTIP)
        self.action.setCheckable(True)
        self.action.toggled.connect(self._on_action_toggled)

        # 0.3.1: 공용 플러그인 툴바(addToolBarIcon) 대신 전용 툴바에 얹는다.
        # 그래야 "보기 > 툴바" 목록에 "UPWISE Chat" 항목이 생겨 사용자가 켜고
        # 끌 수 있다. 둘 다 쓰면 같은 아이콘이 두 군데 보이므로 공용 툴바는
        # 쓰지 않는다.
        self.toolbar = self.iface.addToolBar(TOOLBAR_TITLE)
        self.toolbar.setObjectName(TOOLBAR_OBJECT_NAME)
        self.toolbar.addAction(self.action)
        self.iface.addPluginToMenu(MENU_GROUP, self.action)

        cwd, cwd_why = process.resolve_cwd()
        profile = qgis_profile_root()
        # 0.3.0: `resolve_python=False` 다. `-I` 부트 프로브를 UI 스레드에서
        # 내리고(설계 함정 15) 결과는 아래 스레드가 올린다.
        self.prereq = detect.Prerequisites(cwd=str(cwd),
                                           profile_root=str(profile),
                                           resolve_python=False,
                                           backend=self.backend_adapter)
        # 상류 플러그인(T1) 공존 판정. in-process 조회라 무비용이고 **비활성
        # 사유로 쓰지 않는다** - 독 머리 안내 1줄의 근거다(설계 2-5 조치 2).
        loaded, why = detect.upstream_plugin_loaded()
        self.prereq.note_upstream_plugin(loaded, why)
        self._log("upstream plugin (T1): loaded=%s (%s)" % (loaded, why))

        # 내장 QGIS 서버를 띄운다(0.3.0). **독보다 먼저** 띄워야 전제조건 바가
        # 첫 그림에서 지도 제어 가능 여부를 말할 수 있다(설계 5-2).
        self.server = embedded.EmbeddedServer(iface=self.iface)
        started = self.server.start()
        self.prereq.note_embedded_server(
            started, self.server.port,
            "listening on %s:%d" % (embedded.HOST, self.server.port) if started
            else (self.server.start_error or "start failed"))
        self._log("embedded server: started=%s port=%s (%s)"
                  % (started, self.server.port, self.server.start_error or "ok"),
                  None if started else Qgis.Critical)

        self.probe = PythonProbe()
        self.probe.resolved.connect(self._on_python_resolved)
        self.probe.start()
        # 자체 스킬 번들을 프로필 아래에 한 번 펼친다(0.2.0, 설계 docs/2 6-1).
        # 멱등이고 사용자 자료 폴더를 건드리지 않는다. 실패해도 기능은 산다
        # (절차가 도구 스키마에 있다 - P-C 안전망).
        status, bundle_path, why = skillbundle.ensure_bundle(profile)
        self.prereq.note_bundle(status, bundle_path, why)
        self._log("skill bundle: %s %s (%s)" % (status, bundle_path, why))
        self._log("cwd=%s (%s) prereq=%s" % (cwd, cwd_why, self.prereq.summary()))

        self.dock = UpwiseChatDock(
            self.iface.mainWindow(), backend_factory=self._make_backend
        )
        # S5-2 꽂는 지점 2, 3.
        self.dock.denial_retry_requested.connect(self._on_denial_retry)
        self.dock.set_denial_retry_enabled(True)
        self.dock.set_cwd(str(cwd))
        # S6 꽂는 지점. 탐지 결과는 플러그인이 소유하고 독은 읽어서 바와
        # 버튼에 반영한다(설계 6-4). 첫 init 뒤의 갱신은 독이 gate_result
        # 슬롯에서 백엔드의 init 원본을 읽어 스스로 한다.
        self.dock.set_prerequisites(self.prereq)
        # 0.3.0 꽂는 지점. [점검] 이 내장 서버 핸들러를 직접 부른다 -
        # 모델 0턴·토큰 0·결정적(설계 5-4 (b)). 독이 서버 객체를 들지 않는
        # 이유는 backend_factory 와 같다(독은 QGIS 자원을 소유하지 않는다).
        self.dock.set_self_check(self.server.self_check)
        # 0.3.x U6 꽂는 지점. 헤더 연결 표시가 쓰는 **소켓** 축이다. [점검]
        # (위)은 핸들러를 직접 부르므로 소켓이 실제로 응답하는지는 못 재고,
        # 그 자리에서 U6 이 요구하는 경고 두 축(무응답·포트 재점유)이 갈린다.
        # 독에 넘기는 것은 기동 함수 하나뿐이고 소켓 작업은 서버 쪽 스레드가
        # 한다 - 독이 UI 스레드에서 connect 하면 교착이다(설계 함정 1).
        self.dock.set_port_probe(self.server.start_probe)
        # 0.2.1 꽂는 지점. 키 설정 상태를 지금 한 번 읽어 (1) 레다크터의 지울
        # 값 목록, (2) 전제조건의 키 축, (3) 패널 행 문구를 맞춘다. 독이
        # 스스로 부르지 않는 이유는 set_prerequisites 가 하네스에서도 불리고,
        # 거기서 QgsSettings 를 읽으면 "키 없음" 으로 프리셋이 꺼져 S9b
        # 하네스의 기준 회차가 바뀌기 때문이다 - 제품에서만 부른다.
        self.dock.refresh_keys_state()
        self._log("api keys: %s" % keystore.summary())
        self.dock.visibilityChanged.connect(self._on_dock_visibility_changed)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        # 프로젝트 전환 감지(설계 8). cleared 와 readProject 양쪽을 듣는다.
        # 새 프로젝트와 기존 프로젝트 열기가 서로 다른 신호로 오기 때문이다.
        project = QgsProject.instance()
        project.cleared.connect(self._on_project_changed)
        project.readProject.connect(self._on_project_read)

        # addDockWidget 은 독을 보이게 만든다. 플러그인 적재만으로 패널이
        # 열리지 않도록 숨긴 상태에서 시작한다. 사용자가 액션으로 연다.
        self.dock.hide()
        self._sync_action_checked(False)

    def unload(self):
        """등록한 것을 역순으로 전부 되돌린다.

        순서가 중요하다. 시그널을 먼저 끊지 않으면 removeDockWidget 이
        visibilityChanged 를 발화해서, 정리 중인 액션을 다시 건드린다.
        """
        self._teardown_project_signals()
        self._teardown_dock()
        self._teardown_action()
        # 액션을 먼저 뗀 뒤 툴바를 지운다(0.3.1). 순서를 뒤집으면 삭제 예약된
        # 툴바에서 액션을 떼게 되고, 재적재에서 빈 툴바가 남을 수 있다.
        self._teardown_toolbar()
        # 내장 서버는 **마지막에** 내린다(0.3.0). 독이 백엔드를 끝내는 동안
        # 브리지 자식이 아직 소켓을 들고 있을 수 있고, 서버를 먼저 닫으면
        # 그쪽이 연결 끊김으로 죽으며 로그에 사유 아닌 잡음을 남긴다.
        self._teardown_server()
        self._teardown_probe()

    def _teardown_project_signals(self):
        """프로젝트 전환 시그널을 끊는다. 독보다 먼저 끊어야 한다.

        QgsProject 는 플러그인보다 오래 살기 때문에, 끊지 않으면 unload 뒤에도
        삭제된 독을 가리키는 슬롯이 남는다.
        """
        project = QgsProject.instance()
        self._safe_disconnect(project.cleared, self._on_project_changed)
        self._safe_disconnect(project.readProject, self._on_project_read)

    def _teardown_server(self):
        """내장 소켓 서버를 내린다(0.3.0).

        `EmbeddedServer.stop()` 이 소켓·타이머·클라이언트·체크포인트 임시폴더를
        정리하고 환경에서 토큰을 지운다. 예외를 삼키는 이유는 unload 가 끝까지
        진행해야 하기 때문이다 - 중간에 터지면 액션이 툴바에 남는다.
        """
        if self.server is None:
            return
        try:
            self.server.stop()
        except Exception as exc:  # noqa: BLE001 - unload 는 끝까지 진행해야 한다
            self._log("embedded server teardown failed: %r" % (exc,), Qgis.Warning)
        self.server = None

    def _teardown_probe(self):
        """프로브 스레드를 합류시킨다(0.3.0).

        합류하지 않으면 플러그인 모듈이 사라진 뒤에도 스레드가 돌아 QGIS 가
        종료 시점에 죽는다. 상한을 두는 이유는 unload 가 멈추지 않게 하려는
        것이다 - 프로브는 `subprocess.run` 타임아웃으로 스스로 끝난다.
        """
        probe = self.probe
        self.probe = None
        if probe is None:
            return
        try:
            self._safe_disconnect(probe.resolved, self._on_python_resolved)
            if probe.isRunning():
                probe.wait(PYTHON_PROBE_WAIT_MS)
        except Exception as exc:  # noqa: BLE001 - unload 는 끝까지 진행해야 한다
            self._log("probe teardown failed: %r" % (exc,), Qgis.Warning)

    # ------------------------------------------------------------------
    # 내부 - 백엔드 공장 (S5-2, S5-6)
    # ------------------------------------------------------------------

    def _mcp_config_path(self):
        """플러그인 소유 MCP 설정 파일 경로. 매 spawn 전에 다시 쓴다.

        사용자가 지운 경우와 툴킷 태그가 올라간 경우를 같은 경로로 흡수한다.
        내용은 posture.mcp_config_obj() 가 정본이다.
        """
        return qgis_profile_root().joinpath(*MCP_CONFIG_SUBPATH)

    def _make_spec(self, resume_session_id=None, posture_name=None, cwd=None):
        """SpawnSpec 하나를 만든다. BackendProcess 가 재시작마다 다시 부른다.

        플래그는 세션에 붙어 다니지 않으므로(설계 2-5, D01 실측) 매번 전량을
        다시 조립한다. 포스처와 cwd 를 인자로 받는 이유가 그것이다 -
        상승(S5-4)과 폴더 변경(S5-3)이 같은 경로를 쓴다.

        Args:
            resume_session_id: 있으면 `--resume`, 없으면 새 `--session-id`.
            posture_name: "R" 또는 "W". None 이면 R.
            cwd: 작업 폴더. None 이면 지금 QGIS 프로젝트 기준으로 다시 정한다.

        Returns:
            process.SpawnSpec
        """
        spec_posture = self.backend_adapter.posture_spec(posture_name or None)
        if cwd:
            work_dir = str(cwd)
        else:
            resolved, _why = process.resolve_cwd()
            work_dir = str(resolved)
        # 인터프리터 프로브가 아직 안 끝났으면 여기서만 짧게 기다린다(0.3.0).
        # 적재 때 기다리지 않는 것이 이 변경의 목적이고(설계 함정 15), 전송
        # 때는 값이 있어야 `qgis` 항목을 쓸 수 있다.
        self._await_python()
        # 두 서버 다 같은 인터프리터로 띄운다(0.3.0, 설계 4-3 공용화).
        # 해석되지 않으면 **두 항목을 다 빼고** 전제조건 바가 사유를 띄운다 -
        # 뜨지 못할 설정을 적으면 init 이 status=failed 로 오고 판정이 그것을
        # "서버가 죽었다" 로 읽어 사유가 흐려진다.
        embedded_python = self.prereq.embedded_python if self.prereq else ""
        # 내장 서버가 안 떴으면 접속 좌표가 빈 dict 다. 그 경우에도 같은
        # 규칙으로 `qgis` 항목이 빠진다 - 브리지는 포트·토큰 없이 뜨면
        # preflight 에서 비정상 종료하므로 적어 둘 이유가 없다.
        server_env = self.server.bridge_env() if self.server else {}
        profile = qgis_profile_root()
        profile_paths = skillbundle.profile_env_paths(profile)
        mcp_path = self.backend_adapter.write_mcp_config(
            self._mcp_config_path(),
            embedded_python=embedded_python,
            server_env=server_env,
            profile_paths=profile_paths,
            collect_python=embedded_python)
        # 수집 산출물 폴더를 미리 만든다. 서버가 `-I` 로 떠서 만들 수도 있지만,
        # 사용자에게 보여 줄 경로가 첫 수집 전에 존재해야 한다.
        try:
            os.makedirs(profile_paths["workspace"], exist_ok=True)
        except OSError as exc:  # noqa: BLE001 - 폴더 생성 실패가 기동을 막지 않는다
            self._log("workspace mkdir failed: %r" % (exc,), Qgis.Warning)
        # 자체 스킬 번들은 `--plugin-dir` 로 공급한다(P-A). 번들이 없으면
        # 플래그를 생략한다 - 없는 폴더를 가리키면 CLI 기동 자체가 흔들린다.
        plugin_dirs = ()
        if self.prereq and skillbundle.bundle_present(profile):
            plugin_dirs = (self.prereq.bundle_dir
                           or str(skillbundle.bundle_dir(profile)),)
        session_id = self.backend_adapter.new_session_id()
        # 모델 선택(0.4.0). **여기서 읽는 것이 "다음 스폰부터 적용" 의 구현
        # 이다** - 이 함수는 재시작마다 다시 불리므로, 독에서 고른 값이
        # 지금 도는 자식이 아니라 다음 자식의 argv 에 들어간다. 기본값이면
        # 어댑터가 None 을 주고 argv 조립이 모델 플래그를 생략한다(F6).
        model = self.backend_adapter.model_arg_from_settings()
        argv = self.backend_adapter.build_spawn_argv(
            (self.prereq.backend_exe if self.prereq
             else self.backend_adapter.executable_fallback_name),
            spec_posture,
            session_id=session_id,
            resume_session_id=resume_session_id,
            mcp_config_path=mcp_path,
            plugin_dirs=plugin_dirs,
            model=model,
        )
        env, stripped, api_key = process.child_env(backend=self.backend_adapter)
        if self.prereq is not None:
            self.prereq.set_cwd(work_dir)
        return process.SpawnSpec(
            argv,
            work_dir,
            resume_session_id or session_id,
            env=env,
            env_stripped=stripped,
            api_key_present=api_key,
        )

    def _on_python_resolved(self, status, path, why):
        """프로브 스레드 결과를 전제조건에 넣고 바를 다시 그린다(0.3.0)."""
        if self.prereq is not None:
            self.prereq.note_embedded_python(status, path, why)
        self._log("embedded python: %s %s (%s)" % (status, path, why))
        if self.dock is not None:
            self.dock.refresh_prerequisites()

    def _await_python(self):
        """프로브 스레드가 끝나기를 상한까지 기다린다(0.3.0).

        첫 전송 경로에서만 부른다. 끝나 있으면 즉시 돌아온다. 상한을 넘기면
        **기다리지 않고 그대로 간다** - 그러면 `qgis` 항목이 빠지고 게이트 4
        가 하드 FAIL 을 내며 전제조건 바가 사유를 띄운다. 무한 대기보다
        나쁜 것은 없다(모달 금지와 같은 축이다).
        """
        probe = self.probe
        if probe is None:
            return
        if probe.isRunning() and not probe.wait(PYTHON_PROBE_WAIT_MS):
            self._log("embedded python probe still running after %d ms"
                      % PYTHON_PROBE_WAIT_MS, Qgis.Warning)
            return
        # `wait()` 로 블록한 동안에는 큐에 쌓인 `resolved` 가 배달되지 않는다
        # (같은 스레드다). 그래서 결과를 직접 읽어 적용한다. 슬롯이 나중에
        # 같은 값을 또 넣어도 멱등이다.
        if probe.result and self.prereq is not None \
                and self.prereq.embedded_python_status != detect.FOUND:
            self.prereq.note_embedded_python(*probe.result)

    def _make_backend(self):
        """독이 첫 전송에서 부르는 공장. 포스처 R 로 시작한다(설계 3-3)."""
        spec_posture = self.backend_adapter.posture_spec()
        backend = process.BackendProcess(
            self._make_spec,
            backend=self.backend_adapter,
            expect_tools=spec_posture.tools,
            expect_disallowed=spec_posture.disallowed_tools,
            # 0.3.1: 게이트 6 이 노출/사전승인 정합을 보려면 같은 spec 의
            # allowlist 를 받아야 한다(장부 V32-A52).
            expect_allowed=spec_posture.allowed_tools,
            posture_name=spec_posture.name,
            # 0.2.0: 서버 2개 + 심각도. qgis 미연결은 하드(입력 차단),
            # 수집 서버 미연결은 소프트(수집 버튼만 비활성).
            expect_mcp_servers=self.backend_adapter.expect_mcp_servers_product,
        )
        backend.gate_result.connect(self._on_gate_result)
        return backend

    def _on_gate_result(self, result):
        """첫 init 으로 전제조건을 채운다(설계 6-4). 판정은 독이 쓴다."""
        if self.prereq is None or not isinstance(result, dict):
            return
        # check_init 이 돌려주는 요약에는 plugins/skills 가 없다. 그래서 탐지
        # 전량은 독이 백엔드의 init 원본(process.last_init_event)으로 돌린다
        # (S6, dock._note_init_detect). 여기서는 MCP 축만 로그로 남긴다 -
        # 같은 값을 쓰므로 충돌하지 않고, 플러그인 로그에 기동 시점 상태가
        # 한 줄 남는 것이 진단에 쓰인다.
        servers = result.get("mcp_servers")
        if servers is not None:
            status, detail, why = self.backend_adapter.mcp_server_status(
                {"mcp_servers": servers}
            )
            self.prereq.mcp_status = status
            self.prereq.mcp_detail = detail
            self.prereq.mcp_why = why
            self._log("mcp detect: %s (%s) %s" % (status, detail, why))
            # 수집 서버 축도 같은 창구로 남긴다(0.2.0). 소프트이므로 경고
            # 수준이고 입력을 막지 않는다.
            c_status, c_detail, c_why = self.backend_adapter.mcp_server_status(
                {"mcp_servers": servers}, posture.COLLECT_MCP_SERVER_NAME)
            self.prereq.collect_status = c_status
            self.prereq.collect_detail = c_detail
            self.prereq.collect_why = c_why
            self._log("collect server detect: %s (%s) %s"
                      % (c_status, c_detail, c_why),
                      None if c_status == detect.FOUND else Qgis.Warning)

    def _on_project_read(self, _doc=None):
        """readProject 는 QDomDocument 를 넘긴다. 인자를 삼키고 공통부로 보낸다."""
        self._on_project_changed()

    def _on_project_changed(self):
        """프로젝트가 바뀌었다(설계 8). 독에 알리고 자동 재시작은 하지 않는다."""
        if self.dock is None:
            return
        project = QgsProject.instance()
        name = project.baseName() or project.fileName() or "(제목 없음)"
        resolved, why = process.resolve_cwd()
        # 여기서 prereq.set_cwd 를 부르지 않는다. 프로젝트가 바뀌어도 백엔드는
        # 아직 이전 폴더를 보고 있고(자동 재시작하지 않는다, 설계 8), 프리셋
        # 폴더 판정은 **백엔드의 cwd** 기준이어야 한다(설계 6-3 마지막 줄).
        # 실제 갱신은 재spawn 경로(dock.set_cwd, _make_spec)가 한다.
        shown = self.dock.note_project_changed(name, str(resolved))
        self._log("project changed: %s cwd=%s (%s) stale_bar=%s"
                  % (name, resolved, why, shown))

    def _on_denial_retry(self):
        """거부 바의 "허용하고 다시 요청"(S5-2 지점 2, S5-4).

        상승은 재spawn 이고 같은 요청을 1회 재전송하는 것까지가 독의 일이다.
        """
        if self.dock is None:
            return
        ok = self.dock.elevate_and_resend()
        self._log("denial retry elevate_and_resend -> %s" % ok,
                  None if ok else Qgis.Warning)

    # ------------------------------------------------------------------
    # 내부 - 정리
    # ------------------------------------------------------------------

    def _teardown_dock(self):
        """독의 백엔드를 끝내고 시그널을 끊은 뒤 QGIS 에서 떼어낸다.

        순서가 중요하다. 백엔드를 먼저 끝낸다. claude 가 MCP 브리지를 자식으로
        띄우므로 독 위젯만 지우면 고아 프로세스가 남는다(설계 7-1, 2-1).
        """
        dock = self.dock
        self.dock = None
        if dock is None:
            return
        try:
            dock.shutdown()
        except Exception as exc:  # noqa: BLE001 - unload 는 끝까지 진행해야 한다
            self._log("dock shutdown failed: %r" % (exc,), Qgis.Warning)
        self._safe_disconnect(dock.visibilityChanged, self._on_dock_visibility_changed)
        self._safe_disconnect(dock.denial_retry_requested, self._on_denial_retry)
        try:
            self.iface.removeDockWidget(dock)
        except Exception as exc:  # noqa: BLE001 - unload 는 끝까지 진행해야 한다
            self._log("removeDockWidget failed: %r" % (exc,), Qgis.Warning)
        # setParent(None) 으로 mainWindow 자식 목록에서 먼저 빼낸다. deleteLater
        # 는 이벤트 루프 한 바퀴 뒤에 실제 삭제되므로, 그 사이 QGIS 가 자식을
        # 훑어도 떼어낸 위젯이 걸리지 않게 하기 위함이다.
        dock.setParent(None)
        dock.deleteLater()

    def _teardown_action(self):
        """액션의 시그널을 끊고 툴바/메뉴에서 제거한 뒤 삭제 예약한다."""
        action = self.action
        self.action = None
        if action is None:
            return
        self._safe_disconnect(action.toggled, self._on_action_toggled)
        try:
            self.iface.removePluginToMenu(MENU_GROUP, action)
            # 0.3.1: 전용 툴바에서 액션을 뗀다. 공용 툴바에 넣지 않으므로
            # removeToolBarIcon 은 부르지 않는다 - 짝이 맞지 않는 제거다.
            if self.toolbar is not None:
                self.toolbar.removeAction(action)
        except Exception as exc:  # noqa: BLE001 - 위와 같은 이유
            self._log("action removal failed: %r" % (exc,), Qgis.Warning)
        action.setParent(None)
        action.deleteLater()

    def _teardown_toolbar(self):
        """전용 툴바를 메인 윈도우에서 떼고 삭제 예약한다.

        removeToolBar 만 부르면 툴바가 숨겨지고 레이아웃에서만 빠지며
        mainWindow 의 자식으로 남는다. 그 상태로 재적재하면 같은 제목의 툴바가
        둘이 되고 "보기 > 툴바" 목록에도 두 줄이 보인다. 그래서 떼어낸 뒤
        부모를 끊고 deleteLater 로 넘긴다(독 정리와 같은 이유).
        """
        toolbar = self.toolbar
        self.toolbar = None
        if toolbar is None:
            return
        try:
            self.iface.mainWindow().removeToolBar(toolbar)
        except Exception as exc:  # noqa: BLE001 - unload 는 끝까지 진행해야 한다
            self._log("removeToolBar failed: %r" % (exc,), Qgis.Warning)
        toolbar.setParent(None)
        toolbar.deleteLater()

    # ------------------------------------------------------------------
    # 내부 - 가시성 동기화
    # ------------------------------------------------------------------

    def _on_action_toggled(self, checked):
        """액션 체크 변화를 독 가시성에 반영한다."""
        if self.dock is not None:
            self.dock.setVisible(bool(checked))

    def _on_dock_visibility_changed(self, visible):
        """독 가시성 변화를 액션 체크 상태에 반영한다.

        사용자가 독의 X 를 눌러 닫은 경우에도 액션 체크가 풀려야 한다.
        """
        self._sync_action_checked(bool(visible))

    def _sync_action_checked(self, checked):
        """시그널을 막은 채 체크 상태만 맞춘다.

        blockSignals 없이 setChecked 를 호출하면 toggled -> setVisible ->
        visibilityChanged -> setChecked 로 되돌아오는 왕복이 생긴다.
        """
        if self.action is None:
            return
        blocked = self.action.blockSignals(True)
        try:
            self.action.setChecked(bool(checked))
        finally:
            self.action.blockSignals(blocked)

    # ------------------------------------------------------------------
    # 내부 - 유틸
    # ------------------------------------------------------------------

    def _icon(self):
        """툴바 아이콘. 파일이 없으면 빈 QIcon 으로 떨어뜨린다.

        아이콘 부재로 플러그인 적재가 실패하면 안 되므로 존재 여부를 확인한다.
        """
        path = Path(__file__).resolve().parent / ICON_RELPATH
        if path.is_file():
            return QIcon(str(path))
        self._log("icon not found: %s" % (path,), Qgis.Warning)
        return QIcon()

    @staticmethod
    def _safe_disconnect(signal, slot):
        """이미 끊긴 시그널에 disconnect 를 불러도 unload 가 깨지지 않게 한다.

        Qt 는 연결이 없을 때 TypeError, 수신 객체가 이미 삭제됐을 때
        RuntimeError 를 던진다. 둘 다 정리 경로에서는 정상 상황이다.
        """
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass

    @staticmethod
    def _log(message, level=None):
        """QgsMessageLog 로만 보고한다. 콘솔 print 는 cp949 에서 깨진다(설계 8)."""
        QgsMessageLog.logMessage(
            message, LOG_TAG, Qgis.Info if level is None else level
        )
