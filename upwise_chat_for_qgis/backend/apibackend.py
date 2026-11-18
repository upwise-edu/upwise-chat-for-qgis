"""HTTP 직결 전송 계층 - `BackendProcess` 의 형제 클래스 (docs/13 1-3, 2-4).

왜 형제 클래스인가 (기각안 둘의 요지)
    spawn 전제는 어댑터가 아니라 **프로세스 계층**에 모여 있다.
    `BackendProcess.start()` 가 `Popen(spec.argv)` 한 줄로 전송을 확정하고
    그 아래 전부(리더 2 + 라이터 1 스레드, EOF 처리, tree_kill, 재시작
    백오프, 고아 미결 백스톱)가 "자식 프로세스가 있다" 를 전제한다.

    그래서 (a) 어댑터 계약에 맞추는 안은 **중계 자식 프로세스**가 필요하고
    (stream-json 을 우리 프로세스 둘 사이의 와이어 포맷으로 재구현하게
    된다), (c) `BackendProcess` 에 `if self._is_http:` 를 넣는 안은
    1,957줄짜리 최고 하중 클래스에 미검증 분기를 14개 메서드에 걸쳐
    꽂는다. 둘 다 기각하고 **같은 호출면을 가진 형제 클래스**를 쓴다.

    성립 근거는 독의 백엔드 접속면이 작고 이미 느슨하다는 실측이다 -
    독이 쓰는 멤버는 18개 + 시그널 4개이고, 속성은 전부
    `getattr(..., 기본값)` 으로 읽으며, 독은 `BackendProcess` 를 import
    하지 않는다(`backend_factory` 콜러블만 받는다).

`process.py` 와 같게 둔 것
    * 워커가 `queue.Queue` 에 올리고 **UI 스레드의 QTimer 가 50 ms 마다
      드레인**한다. 상수는 `process` 에서 **읽어 쓴다**(사본 금지).
    * 드레인 1회가 `events_drained` 1회를 쏜다. 이벤트당 시그널을 만들지
      않는다.
    * 올리는 항목이 `process.StreamLine(ts, raw, event)` 다.
    * 원문 녹화를 파싱 **전**에 한다. 로그북 창구가 같다.
    * `QThread` 서브클래스를 쓴다. Qt 가 스레드 수명을 안다.

다르게 둔 것(의도)
    * **스레드는 턴마다 뜨고 턴이 끝나면 죽는다.** 요청 1회가 턴 1개다.
    * **라이터 스레드가 없다.** 보낼 것이 stdin 줄이 아니라 HTTP 본문이고,
      그것은 워커가 자기 요청으로 쓴다.
    * **세대 카운터**를 둔다. 취소된 턴의 워커가 늦게 올리는 줄이 다음 턴
      전사에 섞이는 경로를 이것으로 끊는다. `process.py` 는 같은 문제를
      "자식을 죽이고 EOF 를 받는" 방식으로 풀지만 우리는 소켓을 버린다.
    * **재시작 백오프가 없다.** 재시작할 프로세스가 없다.

단일 불변식: 턴은 반드시 닫힌다 (docs/13 I-2, 6-1)
    턴 워커는 `finally` 에서 `translator.finish()` 를 부른다. 어떤 예외,
    어떤 취소, 어떤 조기 반환에서도 `result` 줄 1개가 큐에 올라간다.
    이것이 없으면 `is_busy()` 가 영구 True 가 되고 입력이 영구 잠긴다 -
    이 제품에 **이미 있었던 사고의 모양**이다(하네스 105 모듈 docstring).
    같은 처방을 처음부터 넣는다. `finish()` 는 멱등이고 락으로 지켜진다.

설계 정본: docs/13.api_key_backend_design_v1.md 1-3, 2-4, 6
"""

import json
import queue
import threading
import time
import uuid as uuid_mod

from qgis.PyQt.QtCore import QObject, QThread, QTimer, pyqtSignal

from . import apiclient, process
from .logbook import SessionLogbook

# 드레인 주기와 1틱 상한. **`process` 에서 읽어 쓴다**(docs/13 2-4-1, A9).
# 사본을 만들면 두 모드의 렌더 리듬이 갈라지고, 그때 전사 동기화 비용을
# 재던 앞 회차 측정이 한쪽에만 맞는다.
DRAIN_INTERVAL_MS = process.DRAIN_INTERVAL_MS
DRAIN_MAX_PER_TICK = process.DRAIN_MAX_PER_TICK

#: 취소 복구 접두 1줄. `process.CANCEL_NOTICE` 와 같은 값을 읽어 쓴다.
CANCEL_NOTICE = process.CANCEL_NOTICE

#: `stop()` 이 워커 합류를 기다리는 상한(ms). 넘기면 진단 1줄을 남기고
#: 버린다 - `unload` 가 멈추지 않는 것이 더 중요하다(플러그인의 프로브
#: 정리와 같은 판단).
JOIN_TIMEOUT_MS = 5000

#: 치명 상태에서 `backend_died` 에 싣는 종료코드. 프로세스가 없으므로
#: 실제 rc 가 아니고 "키가 사라졌다" 를 뜻하는 자리표시다.
DEAD_RC_NO_KEY = -1

#: 그 사유 문구.
DEAD_REASON_NO_KEY = "API 키가 설정되지 않았습니다."

# 세션 수명 줄(synthetic init)에 붙이는 세대 번호.
#
# **왜 따로 두는가**: `start()` 가 init 을 큐에 올린 직후 사용자가 보내면
# (독의 `send_message` 가 `_ensure_backend` -> `send` 를 같은 호출 스택에서
# 한다) 세대가 올라가 init 이 드레인에서 버려진다. 그러면 상태머신이 init
# 을 못 받아 READY 로 올라가지 않고 상태 칩이 영구히 빈다. 세션 줄은 어느
# 턴에도 속하지 않으므로 세대로 거를 대상이 아니다.
GEN_SESSION = -1


class _TurnWorker(QThread):
    """턴 1개의 HTTP 교환을 도는 워커 (docs/13 I-4 의 집행 지점).

    **소켓 연산은 이 클래스 안에서만 일어난다.** UI 스레드에서 블로킹
    `readline()` 을 돌면 독이 얼어붙는다. 하네스 110 A7 이 소스를 tokenize
    해서 이 성질을 판정한다.

    스레드는 턴 1개와 함께 죽는다. 그래서 상태를 길게 들지 않고, 들고 있는
    것은 이 턴의 재료(번역기, 요청 재료, 취소 Event, 세대)뿐이다.
    """

    def __init__(self, translator, material, out_queue, gen,
                 cancel, logbook=None, opener=None, clock=None,
                 resume_reads=True, parent=None):
        """턴 재료를 받아 둔다. 요청은 `run()` 에서 조립한다.

        Args:
            translator: 이 턴의 번역기 1개.
            material: `apiclient.build_request` 에 넘길 kwargs.
            out_queue: `(세대, StreamLine)` 을 올릴 큐.
            gen: 이 턴의 세대 번호.
            cancel: `threading.Event`. UI 스레드가 세운다.
            logbook: 원문 녹화 창구. None 이면 녹화하지 않는다.
            opener: HTTP 주입점. None 이면 실제 `urlopen`.
            clock: 단조 시각 함수. 하네스가 바꿔 끼운다.
            resume_reads: 깨우기 타임아웃 뒤 이어 읽을 것인가(docs/13 4-3).
            parent: QObject 부모.
        """
        super().__init__(parent)
        self._translator = translator
        self._material = dict(material)
        self._queue = out_queue
        self._gen = int(gen)
        self._cancel = cancel
        self._logbook = logbook
        self._opener = opener
        self._clock = clock
        self._resume_reads = bool(resume_reads)
        #: 번역기가 닫힌 뒤에는 아무 줄도 올리지 않는다. 올리면 닫힌 턴
        #: 뒤에 스트림 줄이 붙어 상태머신이 **새 턴을 연다**.
        self._closed = False
        #: 진단용 사유. 턴이 끝난 뒤 백엔드가 읽어 `stderr_line` 으로 낸다.
        self.notice = ""

    def run(self):
        """HTTP 교환 1회를 돌고 `finally` 에서 턴을 닫는다.

        `while True:` 로 쓰고 1차는 **항상 break** 한다. 2차(도구 루프)가
        `stop_reason == "tool_use"` 일 때 도구를 실행하고 `tool_result` 를
        이력에 붙여 다음 교환으로 가는 자리이고, 그때도 **`result` 줄은
        루프 밖에서 1회**만 만들어야 한다(docs/13 8-2 자리 1). I-2 는
        그때도 참이어야 하므로 루프를 지금 모양으로 둔다.
        """
        notice = ""
        reason = apiclient.FINISH_NORMAL
        resp = None
        try:
            while True:
                url, headers, body = apiclient.build_request(**self._material)
                resp = apiclient.open_stream(url, headers, body,
                                             opener=self._opener)
                ctype = apiclient.content_type_of(resp)
                if ctype != apiclient.SSE_CONTENT_TYPE:
                    # 기관망 프록시가 HTML 로그인 페이지를 돌려주는 경로다.
                    # 이 검사 없이는 "아무 글자도 안 나오는" 증상이 된다.
                    _ok, why = apiclient.check_sse_content_type(
                        resp, apiclient.peek_body(resp))
                    notice = why
                    break
                for payload in apiclient.iter_sse(
                        resp, cancel=self._cancel, clock=self._clock,
                        resume_reads=self._resume_reads):
                    if self._cancel.is_set():
                        break
                    for line in self._translator.feed(payload):
                        self._emit(line)
                    if self._translator.finished():
                        # 스트림 중 `error` 이벤트가 턴을 닫았다.
                        break
                break
        except apiclient.ApiHttpError as exc:
            notice = apiclient.http_notice(exc)
        except apiclient.ApiTransportError as exc:
            notice = apiclient.transport_notice(exc)
        except Exception as exc:  # noqa: BLE001 - 어떤 예외에서도 턴은 닫힌다
            notice = apiclient.NOTICE_TRANSPORT % (
                "%s: %s" % (type(exc).__name__, exc))
        finally:
            if self._cancel.is_set():
                reason = apiclient.FINISH_INTERRUPT
            if resp is not None:
                try:
                    resp.close()
                except Exception:  # noqa: BLE001 - 닫기 실패가 턴을 막지 않는다
                    pass
            self.notice = notice
            for line in self._translator.finish(reason=reason,
                                                error=notice or None):
                self._emit(line, final=True)

    def _emit(self, event, final=False):
        """내부 줄 1개를 녹화하고 큐에 올린다.

        원문 녹화를 파싱 **전**에 한다(`process._ReaderThread` 와 같은
        순서). 녹화가 실패해도 큐에는 올린다 - 로그가 없는 것이 턴을 막을
        이유는 아니다.

        Args:
            event: 내부 줄 dict.
            final: 턴을 닫는 줄인가. 올린 뒤 더 올리지 않는다.
        """
        if self._closed:
            return
        raw = json.dumps(event, ensure_ascii=False)
        if self._logbook is not None:
            try:
                self._logbook.write_stdout_line(raw)
            except Exception:  # noqa: BLE001 - 녹화 실패가 턴을 막지 않는다
                pass
        self._queue.put((self._gen, process.StreamLine(time.time(), raw,
                                                       event)))
        if final:
            self._closed = True


class ApiBackend(QObject):
    """HTTP 직결 백엔드. `BackendProcess` 와 같은 호출면을 갖는다.

    시그널 5개는 형제 클래스와 같다.

        events_drained(list[StreamLine])  50 ms 배치.
        stderr_line(str)                  진단 전용. HTTP 사유가 여기로 간다.
        backend_died(int, str)            치명 상태에서만(docs/13 6-5).
        gate_result(dict)                 전송 전 점검(docs/13 3-4).
        posture_changed(str)              쓰이지 않는다. 배선 동형성 유지용.

    `is_running()` 이 **모드**를 뜻하는 이유
        프로세스가 없으므로 "떠 있는가" 를 물을 대상이 없다. 그래서
        `start()` 했고 `stop()` 하지 않았는가를 돌려준다. 독은 이 값으로
        입력 placeholder 와 전송 가능 여부를 가르므로, "모드가 살아 있다"
        가 맞는 뜻이다.
    """

    events_drained = pyqtSignal(object)
    stderr_line = pyqtSignal(str)
    backend_died = pyqtSignal(int, str)
    gate_result = pyqtSignal(object)
    posture_changed = pyqtSignal(str)

    def __init__(self, backend, log_dir=None, opener=None, settings=None,
                 parent=None, clock=None, resume_reads=True):
        """참조만 잡는다. 세션은 `start()` 에서 열린다.

        Args:
            backend: `adapter_api.ApiAdapterBase` 인스턴스. 제공자, 번역기,
                요청 재료가 여기서 온다.
            log_dir: 녹화/진단 폴더. None 이면 로그북 기본 경로.
            opener: HTTP 주입점. None 이면 실제 `urlopen`. 하네스가 가짜를
                꽂아 **네트워크 없이** 전 경로를 잰다.
            settings: QSettings 호환 객체. None 이면 QgsSettings.
            parent: QObject 부모.
            clock: 단조 시각 함수. 하네스가 바꿔 끼운다.
            resume_reads: 깨우기 타임아웃 뒤 이어 읽을 것인가(docs/13 4-3).
        """
        super().__init__(parent)
        self._backend = backend
        self._log_dir = log_dir
        self._opener = opener
        self._settings = settings
        self._clock = clock
        self._resume_reads = bool(resume_reads)

        # ----- 독이 getattr 로 읽는 속성 -----
        self.session_id = ""
        self.posture_name = backend.default_posture_name
        self.gate_blocked = False
        self.gate_block_reason = ""
        # 재시작할 프로세스가 없으므로 **항상 False** 다. 독이 이 값으로
        # "다시 띄웁니다" 와 "멈춥니다" 문면을 가르는데, API 모드는 둘 다
        # 아니라서 `gate_block_reason` 을 쓰는 쪽으로 간다(docs/13 3-4).
        self.gate_restart_pending = False
        #: 수집 서버와 무관하다. 독은 이 값으로 수집 버튼만 가린다.
        self.collect_connected = False
        #: synthetic init 원본. 독의 탐지 갱신이 읽는다.
        self.last_init_event = None
        self.logbook = None
        self.redactor = None
        self.on_control_response = None
        self.last_sent_uuid = ""
        self.sent_uuids = []
        #: 런타임 능력 광고가 없다. 빈 집합은 "광고된 것이 없다" 다.
        self.cli_capabilities = frozenset()
        self.restart_count = 0
        self.orphan_pending_cleared = 0
        self.unmatched_control_responses = []
        #: 마지막 턴이 남긴 사용자 대면 한 줄(docs/13 5-6). 독이 읽어
        #: 공지 1줄로 띄우고 비운다. **키 값이 들어가지 않는다.**
        self.last_turn_notice = ""

        # ----- 내부 상태 -----
        self._queue = queue.Queue()
        self._timer = QTimer(self)
        self._timer.setInterval(DRAIN_INTERVAL_MS)
        self._timer.timeout.connect(self._on_drain)
        self._started = False
        self._busy = False
        self._worker = None
        self._translator = None
        self._cancel = None
        self._pending_prefix = None
        # 세대 카운터. `send()` 와 취소가 올린다(docs/13 2-4-1).
        self._gen = 0
        # 우리가 만든 제어 요청. request_id -> subtype.
        self._pending_control = {}
        # 세대 갱신과 번역기 닫기를 한 덩이로 묶는 락. UI 스레드와 워커가
        # 같은 번역기를 만지는 자리가 취소 하나뿐이고, 그 하나를 지킨다.
        self._lock = threading.Lock()

        # ----- 이력 (이 클래스가 정본으로 든다. docs/13 2-4-2) -----
        #
        # `TurnMachine.turns` 에서 역산하지 않는 이유 둘. (1) `Turn` 은 렌더
        # 지향 객체이고 전송용 평면 이력이 아니다. (2) 머신은 **독**이
        # 소유한다 - 백엔드가 독의 상태를 읽으면 의존이 거꾸로 선다.
        self._history = []
        self._turns = 0
        self._input_tokens = 0
        self._output_tokens = 0

    # ------------------------------------------------------------------
    # 수명
    # ------------------------------------------------------------------

    def is_running(self):
        """`start()` 했고 `stop()` 하지 않았는가. 프로세스가 아니라 모드다."""
        return bool(self._started)

    def is_busy(self):
        """지금 턴이 도는가.

        턴 종료 이벤트를 보는 즉시 False 가 된다(`process.is_busy` 의
        `_busy` 축과 같다). 큐 수명 축은 보지 않는다 - 1차는 우리 큐를
        만들지 않으므로 `capabilities.queue_lifecycle` 이 False 다.

        Returns:
            bool
        """
        return bool(self._busy)

    def lifecycle_live(self):
        """큐 수명 축이 없다. 독의 전송 버튼 판정이 이 값을 읽는다."""
        return False

    def interrupt_live(self):
        """턴 중단은 우리가 한다(소켓을 닫는다). 항상 쓸 수 있다."""
        return True

    def cancel_queued_live(self):
        """대기 메시지가 없다. 취소할 것이 없다."""
        return False

    def interrupt_send_now_live(self):
        """대기 메시지를 지금 보내는 기능이 없다(큐가 없다)."""
        return False

    def has_cli_capability(self, name):
        """런타임 광고가 없다. 항상 False 다."""
        del name
        return False

    @property
    def interrupt_subtype(self):
        """턴 중단 요청의 subtype 이름. 어댑터가 쥔다."""
        return getattr(self._backend, "control_interrupt_subtype", "")

    @property
    def cancel_queued_subtype(self):
        """대기 메시지 취소 subtype. 없으므로 빈 문자열이다."""
        return ""

    def start(self, resume_session_id=None):
        """세션을 연다. **HTTP 를 치지 않는다.**

        네 가지를 한다. (1) 세션 id 발급, (2) 로그북 열기, (3) synthetic
        init 1줄 방출, (4) 전송 전 점검 1회.

        `resume_session_id` 를 받고 **쓰지 않는다**. API 는 무상태라 서버에
        세션이 없고, 이력은 이 객체가 메모리에 든다. 인자를 받는 이유는
        호출면 동형성뿐이다(`capabilities.resume` 이 False 로 그 사실을
        말한다).

        Returns:
            bool: 세션을 열었는가.
        """
        if self._started:
            return True
        del resume_session_id
        self.session_id = self._backend.new_session_id()
        self._started = True
        self._busy = False
        self._queue = queue.Queue()
        self.logbook = SessionLogbook(self._log_dir,
                                      session_id=self.session_id,
                                      redactor=self.redactor)
        self._diag("logfiles", "resume=False jsonl=%s diag=%s"
                   % (self.logbook.jsonl_path, self.logbook.diag_path))
        self._diag("transport", "api provider=%s" % self._backend.name)
        self._diag("posture", str(self.posture_name))
        # 모델명은 비밀이 아니다. 키는 **적지 않는다**(설정 여부만 적는다).
        self._diag("model", str(self._backend.model_arg_from_settings(
            settings=self._settings) or "(none)"))
        self._emit_init()
        self._run_gate()
        self._timer.start()
        return True

    def stop(self, reason="stop"):
        """워커를 취소하고 합류한 뒤 로그북을 닫는다.

        합류에 상한을 두는 이유는 `unload` 가 멈추지 않게 하려는 것이다.
        상한을 넘기면 진단 1줄을 남기고 워커를 버린다 - 소켓에 매인 스레드
        하나가 QGIS 종료를 막는 것이 더 나쁘다.

        Args:
            reason: 진단에 적을 사유.
        """
        self._started = False
        self._timer.stop()
        self._cancel_worker()
        worker = self._worker
        self._worker = None
        if worker is not None and worker.isRunning():
            if not worker.wait(JOIN_TIMEOUT_MS):
                self._diag("worker_abandoned", "timeout_ms=%d"
                           % JOIN_TIMEOUT_MS)
        self._busy = False
        if self.logbook is not None:
            self._diag("stopped", reason)
            self.logbook.close()

    def request_cancel(self):
        """사용자 취소. 턴을 끊고 **이력과 세션 id 를 유지한다.**

        `BackendProcess.request_cancel()` 과 뜻이 다르다. 그쪽은 트리 종료
        + 재개 재spawn 이고, 이쪽은 재spawn 이 아니다 - 다시 띄울 프로세스가
        없다. 다음 메시지 앞에 붙일 접두 1줄만 예약한다.

        Returns:
            bool: 끊을 턴이 있었는가.
        """
        had = bool(self._busy)
        self._close_turn_as_interrupt(receipt_request_id="")
        self.queue_notice_prefix(CANCEL_NOTICE)
        self._diag("cancel", "had_turn=%s session=%s" % (had, self.session_id))
        return had

    # ------------------------------------------------------------------
    # 입력
    # ------------------------------------------------------------------

    def queue_notice_prefix(self, text):
        """다음 사용자 메시지 앞에 붙일 한 줄을 예약한다.

        이미 예약된 줄이 있으면 덮지 않고 이어 붙인다(`process` 의 같은
        함수와 같은 규칙) - 둘 중 하나를 모델에게 숨기면 안 된다.
        """
        text = str(text or "").strip()
        if not text:
            return
        if self._pending_prefix:
            if text in self._pending_prefix:
                return
            self._pending_prefix = self._pending_prefix + "\n" + text
        else:
            self._pending_prefix = text
        self._diag("prefix_queued", self._pending_prefix)

    def pending_prefix(self):
        """예약된 줄. 검증 하네스가 읽는다."""
        return self._pending_prefix or ""

    def send(self, text, allow_queue=False):
        """턴 1개를 시작한다.

        **도는 턴이 있으면 False 다.** 1차는 우리 큐를 만들지 않는다 -
        큐를 만들면 대기 건수와 취소와 회수를 전부 자작해야 하고, 그 UI 는
        CLI 큐에 위임한 0.6.1 의 산물이다. `allow_queue` 를 받고 쓰지 않는
        이유는 호출면 동형성이다(독이 턴 중에 그 인자로 부른다).

        Args:
            text: 보낼 원문.
            allow_queue: 받고 무시한다.

        Returns:
            bool: 턴을 시작했는가.
        """
        del allow_queue
        if not self._started:
            return False
        if self.gate_blocked:
            # 전송 전 점검이 어긋난 상태다. 과금 경로에 들어가지 않는다.
            self._diag("send_blocked", self.gate_block_reason)
            return False
        if self._busy:
            return False
        ready, why = self._backend.send_ready(settings=self._settings)
        if not ready:
            # 게이트를 통과한 뒤 사용자가 키를 지운 경로다(docs/13 6-5).
            self.gate_blocked = True
            self.gate_block_reason = why
            self._diag("send_blocked", why)
            self.backend_died.emit(DEAD_RC_NO_KEY, DEAD_REASON_NO_KEY)
            return False
        body = text
        if self._pending_prefix:
            body = self._pending_prefix + "\n" + text
            self._pending_prefix = None
        msg_uuid = str(uuid_mod.uuid4())
        self._history.append({"role": "user", "content": body})
        self.last_sent_uuid = msg_uuid
        self.sent_uuids.append(msg_uuid)
        # 입력 녹화. 전송에는 쓰이지 않는 줄이고(stdin 이 없다) 녹화본
        # 포맷을 두 모드에서 한 가지로 두기 위한 것이다.
        if self.logbook is not None:
            try:
                self.logbook.write_stdout_line(
                    self._backend.serialize_user_input(body, uuid=msg_uuid))
            except Exception:  # noqa: BLE001 - 녹화 실패가 전송을 막지 않는다
                pass
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._translator = self._backend.translator(self.session_id,
                                                        msg_uuid)
        self._cancel = threading.Event()
        material = self._backend.request_material(
            "", self._history, settings=self._settings)
        self._worker = _TurnWorker(
            self._translator, material, self._queue, gen, self._cancel, logbook=self.logbook, opener=self._opener,
            clock=self._clock, resume_reads=self._resume_reads, parent=self)
        self._busy = True
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        self._diag("sent", "bytes=%d uuid=%s gen=%d turns=%d"
                   % (len(body.encode("utf-8")), msg_uuid, gen,
                      len(self._history)))
        return True

    # ------------------------------------------------------------------
    # 중단 (0.6.1 UI 를 그대로 쓰기 위한 동형면. docs/13 6-3)
    # ------------------------------------------------------------------

    def send_control(self, subtype, **fields):
        """제어 요청을 **우리가 처리한다.**

        영수증을 우리가 만드는 것이 의미상 정직한 이유: API 모드에서 턴을
        멈추는 주체가 실제로 우리다(소켓을 닫는다).

        중단 요청이면 네 가지를 큐에 올린다 - `control_response` 1줄과
        중단형 `result` 1줄이다. 상태머신의 중단 판정 네 조건
        (우리 요청의 응답 수신, 중단 subtype, `is_error` 참, `result` 키
        부재)이 그것으로 성립하고, 그래서 **독 수정 0줄**로 기존
        "턴을 중단했습니다" 문구가 발화한다.

        Args:
            subtype: 요청 종류. 어댑터가 이름을 쥔다.
            **fields: 요청별 인자. None 인 것은 어댑터가 버린다.

        Returns:
            str: 발급한 request_id. 처리하지 못했으면 빈 문자열.
        """
        if not self._started:
            return ""
        if subtype != self.interrupt_subtype or not subtype:
            # 아는 제어 요청이 중단 하나뿐이다. 모르는 것을 처리한 척하지
            # 않는다 - 호출자가 빈 문자열을 보고 폴백으로 내려간다.
            self._diag("control_unsupported", str(subtype))
            return ""
        request_id = str(uuid_mod.uuid4())
        self._pending_control[request_id] = subtype
        if self.logbook is not None:
            try:
                self.logbook.write_stdout_line(
                    self._backend.serialize_control_request(
                        request_id, subtype, **fields))
            except Exception:  # noqa: BLE001 - 녹화 실패가 중단을 막지 않는다
                pass
        self._diag("control_sent", "subtype=%s request_id=%s"
                   % (subtype, request_id))
        self._close_turn_as_interrupt(receipt_request_id=request_id)
        return request_id

    def interrupt_turn(self, reason=None):
        """진행 중인 턴을 끊는다.

        Args:
            reason: 중단 사유. None 이면 어댑터가 키 자체를 넣지 않는다.

        Returns:
            str: 발급한 request_id. 끊을 턴이 없으면 빈 문자열.
        """
        if not self._busy:
            return ""
        return self.send_control(self.interrupt_subtype, reason=reason)

    def interrupt_turn_send_now(self, message_uuid, reason=None):
        """대기 메시지가 없으므로 할 일이 없다.

        Returns:
            bool: 항상 False. 독이 이 값을 보고 폴백으로 내려간다.
        """
        del message_uuid, reason
        return False

    def cancel_queued_message(self, message_uuid):
        """대기 메시지가 없으므로 할 일이 없다.

        Returns:
            bool: 항상 False.
        """
        del message_uuid
        return False

    # ------------------------------------------------------------------
    # 세션
    # ------------------------------------------------------------------

    def new_session(self, posture_name=None, expect_tools=None,
                    expect_disallowed=None, expect_allowed=None, **kwargs):
        """이력을 비우고 세션 id 를 새로 받는다.

        **여기가 비용 리셋 지점이다**(docs/13 6-5). 매 턴 이력 전량을
        재전송하므로 턴이 늘면 입력 토큰이 누적 비례로 늘어나고, 1차는
        자동 잘라내기를 넣지 않았다(사용자 결정 D-4). 그래서 "새 대화" 가
        **유일한 리셋**이다.

        Args:
            posture_name: 받고 무시한다(포스처가 하나다).
            expect_tools: 받고 무시한다(도구가 0개다).
            expect_disallowed: 받고 무시한다.
            expect_allowed: 받고 무시한다.
            **kwargs: 받고 무시한다.

        Returns:
            bool: 새 세션을 열었는가.
        """
        del posture_name, expect_tools, expect_disallowed, expect_allowed
        del kwargs
        self._cancel_worker()
        self._busy = False
        self._history = []
        self._turns = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self.sent_uuids = []
        self.last_sent_uuid = ""
        self.last_turn_notice = ""
        self._pending_prefix = None
        if self.logbook is not None:
            self._diag("new_session", "old=%s" % self.session_id)
            self.logbook.close()
        self.session_id = self._backend.new_session_id()
        self.logbook = SessionLogbook(self._log_dir,
                                      session_id=self.session_id,
                                      redactor=self.redactor)
        self._diag("logfiles", "resume=False jsonl=%s diag=%s"
                   % (self.logbook.jsonl_path, self.logbook.diag_path))
        self._emit_init()
        self._run_gate()
        if not self._timer.isActive():
            self._timer.start()
        self._started = True
        return True

    def elevate(self, posture_name, expect_tools, expect_disallowed=None,
                expect_allowed=None):
        """올릴 권한이 없다. 도구가 0개이므로 포스처가 하나다.

        Returns:
            bool: 항상 False.
        """
        del expect_tools, expect_disallowed, expect_allowed
        self._diag("elevate_unsupported", "to=%s" % posture_name)
        return False

    def restart_with_cwd(self, cwd):
        """cwd 가 의미 없다. 파일 접근이 없다.

        **True 를 돌려준다.** False 를 돌려주면 독이 "작업 폴더 변경 실패"
        공지를 띄우는데, 실패한 것이 아니라 바꿀 것이 없다. 독의 폴더 변경
        흐름을 막지 않는 쪽이 사용자에게 맞다.

        Returns:
            bool: 항상 True.
        """
        self._diag("cwd_noop", "to=%s" % cwd)
        return True

    # ------------------------------------------------------------------
    # 이력과 요약
    # ------------------------------------------------------------------

    def history_summary(self):
        """이력 규모와 누적 토큰. **본문이 들어가지 않는다.**

        Returns:
            dict: turns, messages, input_tokens, output_tokens.
        """
        return {"turns": self._turns, "messages": len(self._history),
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens}

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _diag(self, tag, detail=""):
        """진단 한 줄. 로그북이 없으면 버린다. **키 값이 들어가지 않는다.**"""
        book = self.logbook
        if book is None:
            return
        try:
            book.diag(tag, detail)
        except Exception:  # noqa: BLE001 - 로깅 실패가 턴을 막지 않는다
            pass

    def _emit_init(self):
        """synthetic `system`/`init` 1줄을 큐에 올린다(docs/13 4-1 첫 행).

        **턴마다 쏘지 않는다.** 턴 중 init 재출현은 상태머신이 "재spawn
        으로 끊긴 턴" 으로 읽어 그 턴을 버린다. 그래서 세션을 열 때
        한 번뿐이다(`start()` 와 `new_session()`).
        """
        event = {
            "type": "system", "subtype": "init",
            "model": str(self._backend.model_arg_from_settings(
                settings=self._settings) or ""),
            "permissionMode": "",
            "tools": [], "mcp_servers": [],
            "session_id": self.session_id,
            "cwd": "", "claude_code_version": "",
        }
        self.last_init_event = event
        raw = json.dumps(event, ensure_ascii=False)
        if self.logbook is not None:
            try:
                self.logbook.write_stdout_line(raw)
            except Exception:  # noqa: BLE001 - 녹화 실패가 기동을 막지 않는다
                pass
        self._queue.put((GEN_SESSION, process.StreamLine(time.time(), raw,
                                                         event)))

    def _run_gate(self):
        """전송 전 점검 1회. `gate_result` 를 1번 쏜다(docs/13 3-4).

        Claude 모드의 기동 자기점검 게이트(init 1-6)는 이식 불가다 -
        점검할 플래그가 없다. 대신 **같은 배선**을 쓴다: 키와 모델이
        갖춰졌는가를 보고 `gate_blocked` 와 `gate_block_reason` 을 세운다.
        독은 이미 `gate_blocked` 로 입력을 막는다.

        Returns:
            dict: 쏜 판정.
        """
        ready, why = self._backend.send_ready(settings=self._settings)
        self.gate_blocked = not ready
        self.gate_block_reason = "" if ready else why
        items = []
        if not ready:
            items.append({"check": "llm_credentials", "status": "FAIL",
                          "detail": why})
        result = {"ok": bool(ready), "items": items, "mcp_servers": []}
        self._diag("gate", self._backend.format_gate(result)
                   + (" reason=%s" % why if why else ""))
        self.gate_result.emit(result)
        return result

    def _cancel_worker(self):
        """워커에 취소를 알린다. 합류는 하지 않는다(UI 를 막지 않는다)."""
        cancel = self._cancel
        if cancel is not None:
            cancel.set()

    def _close_turn_as_interrupt(self, receipt_request_id=""):
        """도는 턴을 중단형으로 닫는다. 영수증과 `result` 를 우리가 만든다.

        세대를 올리는 이유 (docs/13 2-4-1)
            워커가 소켓에 매여 있는 동안 늦은 스트림 줄을 올릴 수 있고, 그
            줄이 닫힌 턴 뒤에 붙으면 상태머신이 **새 턴을 연다.** 세대를
            올려 그 줄들을 드레인에서 버린다.

        워커가 먼저 닫은 경우
            `finish()` 가 빈 목록을 돌려준다. 그때는 세대를 올리지 않는다 -
            워커가 올린 `result` 가 현 세대에 있고, 올리면 그것까지 버려져
            턴이 영구히 열린 채 남는다.

        Args:
            receipt_request_id: 영수증에 반향할 request_id. 빈 값이면
                영수증을 만들지 않는다(워치독 [취소] 경로다).
        """
        self._cancel_worker()
        translator = self._translator
        if translator is None:
            self._busy = False
            return
        with self._lock:
            lines = translator.finish(reason=apiclient.FINISH_INTERRUPT)
            if lines:
                self._gen += 1
            gen = self._gen
        if lines and receipt_request_id:
            # **영수증이 `result` 보다 먼저 가야 한다.** 상태머신은 우리
            # 요청의 응답을 받은 사실로만 중단을 판정한다(추측하지 않는다).
            self._put_event(self._receipt_event(receipt_request_id), gen)
        for event in lines:
            self._put_event(event, gen)
        self._busy = False

    def _receipt_event(self, request_id):
        """우리가 만드는 `control_response` 1줄.

        축자 형태는 이중 중첩이다(`protocol.control_response_info` 가 그
        모양을 읽는다). `still_queued` 가 빈 목록인 이유: 우리 큐가 없다.
        """
        return {"type": "control_response",
                "response": {"subtype": "success", "request_id": request_id,
                             "response": {"still_queued": []}}}

    def _put_event(self, event, gen):
        """내부 줄 1개를 녹화하고 큐에 올린다(UI 스레드 경로)."""
        raw = json.dumps(event, ensure_ascii=False)
        if self.logbook is not None:
            try:
                self.logbook.write_stdout_line(raw)
            except Exception:  # noqa: BLE001 - 녹화 실패가 턴을 막지 않는다
                pass
        self._queue.put((int(gen), process.StreamLine(time.time(), raw,
                                                      event)))

    def _on_worker_finished(self):
        """워커 스레드가 끝났다. 진단 사유 한 줄을 올린다.

        `_busy` 를 여기서 내리지 않는다 - 그 판정의 원천은 **턴 종료
        이벤트**이고(`_inspect`), 스레드 수명과 턴 수명을 한 값으로 섞으면
        드레인이 아직 안 돈 상태에서 입력이 열린다.
        """
        worker = self.sender()
        notice = getattr(worker, "notice", "") if worker is not None else ""
        if notice:
            self.stderr_line.emit(notice)
            self._diag("turn_error", notice)
        if worker is not None:
            # 턴마다 스레드가 뜨므로 끝난 것을 놓아 준다. 안 놓으면 이
            # 객체의 자식 목록에 QThread 가 턴 수만큼 쌓인다.
            if self._worker is worker:
                self._worker = None
            worker.deleteLater()

    def _on_drain(self):
        """50 ms 틱. 큐를 비우고 배치 1개로 신호 1회.

        **현 세대가 아닌 항목은 버린다**(docs/13 2-4-1). 버린 수를 세어
        진단에 남긴다 - 조용히 지우지 않는다는 규칙의 관측 창구다.
        """
        batch = []
        dropped = 0
        for _ in range(DRAIN_MAX_PER_TICK):
            try:
                gen, line = self._queue.get_nowait()
            except queue.Empty:
                break
            if int(gen) != self._gen and int(gen) != GEN_SESSION:
                dropped += 1
                continue
            batch.append(line)
            self._inspect(line)
        if dropped:
            self._diag("stale_lines_dropped", "n=%d gen=%d"
                       % (dropped, self._gen))
        if batch:
            self.events_drained.emit(batch)

    def _inspect(self, line):
        """프로세스 계층이 꼭 봐야 하는 것만 본다 - 턴 종료 1건이다.

        해석은 상태머신이 한다. 여기서 보는 것은 (1) 입력 차단을 풀어야
        하는 턴 종료, (2) 사용량 카드가 읽을 토큰 누계, (3) 사용자 대면
        한 줄이다.
        """
        event = getattr(line, "event", None)
        if not isinstance(event, dict):
            return
        if event.get("type") == "control_response":
            self._settle_control(event)
            return
        if not self._backend.is_turn_end_event(event):
            return
        self._busy = False
        self._turns += 1
        usage = event.get("usage")
        if isinstance(usage, dict):
            self._input_tokens += int(usage.get("input_tokens") or 0)
            self._output_tokens += int(usage.get("output_tokens") or 0)
        # 정상 종료면 조립된 텍스트를 이력에 붙인다. 취소/오류로 끝났으면
        # **부분 텍스트가 비어 있지 않을 때만** 붙인다 - 빈 것을 붙이면 빈
        # assistant 메시지가 생기고(그 다음 전송이 400 이다), 안 붙이면
        # 모델이 자기가 하던 말을 모른다(docs/13 2-4-2).
        translator = self._translator
        text = translator.assistant_text() if translator is not None else ""
        if text:
            self._history.append({"role": "assistant", "content": text})
        notice = event.get("upwise_notice")
        self.last_turn_notice = str(notice or "")
        self._diag("turn_closed",
                   "subtype=%s is_error=%s in=%d out=%d history=%d"
                   % (event.get("subtype"), event.get("is_error"),
                      self._input_tokens, self._output_tokens,
                      len(self._history)))

    def _settle_control(self, event):
        """우리가 만든 영수증을 호출자 콜백에 넘긴다(독의 끼어들기 배선).

        `process._on_control_response` 와 같은 창구다. 시그널을 새로 만들지
        않는 이유는 이벤트당 시그널 금지 규약이다.
        """
        from . import protocol

        info = protocol.control_response_info(event)
        matched = self._pending_control.pop(info.request_id, "")
        if not matched:
            self.unmatched_control_responses.append((info.request_id,
                                                     info.subtype))
        callback = self.on_control_response
        if callback is None:
            return
        try:
            callback(info.request_id, info.subtype, dict(info.payload),
                     matched)
        except Exception as exc:  # noqa: BLE001 - 콜백 실패가 드레인을 막지 않는다
            self._diag("control_callback_error", repr(exc))
