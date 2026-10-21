"""백엔드 CLI 서브프로세스 계층 (설계 2).

0.5.5 부터 이 층은 **어떤 백엔드를 띄우는지 모른다.** argv 플래그 이름,
입력 직렬화 포맷, 개시·종료 이벤트의 판별, 게이트 항목 구성은 전부
`adapter_registry.default()` 가 주는 어댑터에 물어 본다(docs/7 2-10).
기본 어댑터는 Claude Code CLI 이고, 그 아래 동작은 리팩터 전과 같다.

구조는 설계 2-2 가 고른 것 그대로다.

    subprocess.Popen
      + 리더 QThread 2개(stdout, stderr)   줄 단위 readline, stdout 은 여기서 파싱
      + 라이터 QThread 1개                 큐에서 꺼내 한 줄씩 write + flush
      + GUI 쪽 50 ms 드레인 QTimer         큐를 비우고 배치 1개로 신호 1회

왜 QProcess 가 아닌가
    (1) PoC 2종이 이 구조로 전 항목 PASS 했고 한글 왕복도 이 파이프 설정에서 나왔다.
    (2) CREATE_NO_WINDOW 를 QProcess 로 주는 경로는 미측(D13)이다.
    (3) 긴 MCP 도구 실행이 QGIS 메인 스레드를 점유하면 GUI 스레드에서 읽는 설계는
        파이프가 차서 CLI 가 write 에서 멈춘다. 리더 스레드는 그 구간에도 읽는다.

왜 이벤트 1개당 시그널 1개가 아닌가
    긴 응답의 text_delta 는 초당 수백 개가 될 수 있다. 50 ms 드레인은 초당 20회
    갱신이고 사람 눈에는 스트리밍으로 보인다(설계 2-6).

종료는 항상 트리 종료다. claude 가 MCP 브리지(uvx)를 자식으로 띄우므로 부모만
죽이면 고아가 남는다(F11, 강의 실측 고아 5개). Windows 는 taskkill /F /T 다.
macOS/Linux 는 MVP 검증 범위 밖이므로(설계 9) 트리 종료를 구현하지 않고
단일 kill 로 떨어뜨린 뒤 그 사실을 진단에 남긴다.

이 모듈은 이벤트를 해석하지 않는다. 파싱된 dict 를 배치로 올려 보내는 것이 끝이고,
상태머신과 렌더는 S3/S4 범위다. 다만 두 가지는 여기서 본다. 어느 이벤트가 그
둘인지는 어댑터가 판별한다(`is_session_init_event`·`is_turn_end_event`).
    * 세션 개시 이벤트  기동 자기점검 게이트(설계 3-4)를 돌려야 한다.
    * 턴 종료 이벤트    턴 중 입력 차단(설계 2-4)을 푼다.

설계 정본: docs/1.mvp_design_v1.md 2-1 ~ 2-6, 3-4, 8
"""

import collections
import inspect
import json
import os
import queue
import subprocess
import sys
import time
from pathlib import Path

from qgis.PyQt.QtCore import QObject, QThread, QTimer, pyqtSignal

from . import adapter_registry
from .logbook import SessionLogbook, qgis_profile_root

# QGIS 플러그인에서 콘솔 창 깜빡임 방지(설계 2-3 실측 플래그).
CREATE_NO_WINDOW = 0x08000000

# 드레인 주기. 초당 20회 갱신이면 사람 눈에 스트리밍으로 보인다(설계 2-6).
DRAIN_INTERVAL_MS = 50

# 한 틱에 처리할 줄 수 상한. 설계는 "큐를 비울 때까지" 라고 했지만, 거대한
# 버스트가 한 틱에 몰리면 GUI 가 그만큼 멈춘다. 남은 것은 다음 틱에서 처리하므로
# 유실은 없다. 보수적으로 크게 잡았다.
DRAIN_MAX_PER_TICK = 2000

# 자동 재시작 정책(설계 2-5). 미로그인 등에서 무한 spawn 을 막는다.
RESTART_DELAYS_S = (2.0, 8.0, 30.0)
RESTART_WINDOW_S = 300.0
RESTART_MAX = 3

# 취소 복구 후 다음 사용자 메시지에 붙이는 한 줄(설계 2-5). 취소된 턴의 부분
# 상태가 어떻게 보존되는지 모르기 때문에 모델에게 사실을 알려 준다.
CANCEL_NOTICE = "(이전 요청은 사용자가 취소했습니다)"

# 트리 종료 명령의 대기 상한(초). taskkill 이 응답하지 않는 경우를 대비한다.
TASKKILL_TIMEOUT_S = 15.0

# 종료 후 프로세스 수거 대기 상한(초).
REAP_TIMEOUT_S = 10.0

# poll() 로 사망을 본 뒤 stdout EOF 를 기다리는 유예(초).
# 설계 2-5 는 사망 감지를 "stdout EOF 또는 poll() is not None" 으로 적었지만,
# poll() 쪽이 먼저 참이 되는 순간 파이프에는 아직 읽지 않은 줄이 남아 있다.
# 그 상태로 사망 처리를 하면 마지막 result 를 유실한다. 그래서 EOF 를 우선
# 신호로 쓰고, poll() 은 EOF 가 오지 않는 경우의 보조 신호로 유예를 둔다.
DEATH_GRACE_S = 1.0

# 저장된 프로젝트가 없을 때 쓰는 작업 폴더(설계 2-3).
WORKSPACE_SUBDIR = ("upwise_chat", "workspace")

# 게이트 실패 재시작 상한(S5-1). 설계 3-4 는 "어긋나면 그 턴의 결과를 버리고
# 백엔드를 재시작한다" 까지만 적었고 횟수를 정하지 않았다. 무제한으로 두면
# 플래그를 무시하는 환경에서 재시작이 영원히 돈다(한 번에 한 턴씩 과금된다).
# 그래서 1회로 고정했다. 보수적으로 고른 값이고 설계에 없던 결정이다.
GATE_RESTART_MAX = 1

# 게이트 실패 재시작을 다음 이벤트 루프 턴으로 미루는 지연(초).
# 드레인 틱 안에서 동기 재시작을 하면 그 틱이 쓰던 큐가 교체된다. 또 게이트를
# 깨뜨린 그 배치가 UI 로 올라가기 전에 끊기면 사용자가 이유를 못 본다.
GATE_RESTART_DELAY_S = 0.5

# 자식에게 물려주지 않는 상속 PYTHON 환경변수(0.1.2 사전 명세).
#
# QGIS 는 자기 파이썬을 들고 오면서 이 변수들을 자기 프로세스 환경에 박는다
# (이 호스트 실측: PYTHONEXECUTABLE=C:\PROGRA~1\QGIS34~1.14\bin\python3.exe).
# claude 자체는 node 라 영향이 없지만, claude 가 띄우는 MCP 브리지(uvx)의
# 캐시 venv 파이썬까지 같은 값이 그대로 전파된다. 그 venv 는 자기
# pyvenv.cfg 대신 PYTHONEXECUTABLE 이 가리키는 QGIS python 을 기준으로
# 경로를 다시 계산하고, 결과로 **venv 의 site-packages 를 읽지 않는다.**
# 0.1.1 실사용 1회차가 거기서 죽었다
# (ModuleNotFoundError: No module named 'qgis_mcp').
#
# A/B 실측에서 범인은 PYTHONEXECUTABLE 단독이었다. QGIS 환경 132변수 전량
# 주입은 사망, PYTHON 군 7개 제거는 기동, 단일 제거 비교에서
# PYTHONEXECUTABLE 만 빼면 기동했고 PYTHONHOME/PYTHONPATH 는 각각 빼도
# 사망이 유지됐다. 깨끗한 환경에 PYTHONEXECUTABLE 하나만 넣어도 죽었다.
# 그래도 나머지 셋을 같이 제거하는 이유는 같은 축의 예방이다 - 셋 다 임의의
# uv/파이썬 자식의 모듈 탐색 경로를 부모 기준으로 끌어당기고, claude 의
# 자식에게 남겨둘 이유가 없다.
#
# PYTHONUTF8 과 PYTHONIOENCODING 은 건드리지 않는다. 파이프가 utf-8 텍스트
# 모드라 자식 쪽 인코딩 계약이 거기에 걸려 있다(아래 child_env 가
# PYTHONIOENCODING 을 다시 쓴다).
INHERITED_PYTHON_KEYS = (
    "PYTHONEXECUTABLE",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
)

StreamLine = collections.namedtuple("StreamLine", "ts raw event")


def resolve_cwd():
    """백엔드 cwd 를 정한다(설계 2-3).

    저장된 QGIS 프로젝트가 있으면 그 폴더, 없으면
    <QGIS 사용자 프로필>/upwise_chat/workspace 다. cwd 는 모델의 파일 접근
    범위와 CLAUDE.md 자동 탐색 범위를 동시에 정하므로, 사용자가 그 폴더를
    알아야 한다. 독 하단 표시와 변경 UI 는 S4 범위이고 여기서는 값만 정한다.

    Returns:
        tuple: (Path, 근거 문자열)
    """
    path = ""
    try:
        from qgis.core import QgsProject

        path = QgsProject.instance().absolutePath() or ""
    except Exception:  # noqa: BLE001 - 프로젝트 조회 실패가 기동을 막지 않는다
        path = ""
    if path:
        candidate = Path(path)
        if candidate.is_dir():
            return candidate, "qgis_project"
    return qgis_profile_root().joinpath(*WORKSPACE_SUBDIR), "profile_workspace"


def child_env(base=None, backend=None):
    """자식에게 줄 환경변수 사본을 만든다(설계 2-3).

    두 묶음을 제거한다.

    (1) **백엔드 고유 키.** 어댑터의 `env_strip_exact`(정확 일치)와
        `env_strip_prefixes`(접두) 가 정본이다. Claude 백엔드에서 그것은
        `CLAUDECODE` 와 `CLAUDE_CODE_*` 다 - 실제 QGIS 환경에는 없는
        변수이고 개발 중 Claude Code 안에서 테스트할 때만 상속된다.
        제거해야 테스트가 실제 환경과 같아진다. 목록을 어댑터로 옮긴 것이
        0.5.5 리팩터이고(docs/7 2-10 경계 6), 값은 그대로다.
    (2) INHERITED_PYTHON_KEYS(0.1.2). **백엔드 무관**이라 여기 남는다.
        QGIS 가 자기 파이썬 기준으로 박아 둔 변수들이고, 그대로 물려주면
        백엔드가 띄운 자식 파이썬이 자기 site-packages 를 잃는다. 근거는
        그 상수 주석이다.

    제거한 키는 돌려주는 목록에 그대로 담겨 기동 진단의 `env_stripped` 줄로
    나간다. 업그레이드한 사용자의 진단 로그가 "그 환경에 무엇이 있었는가" 를
    증명하는 유일한 근거라 비우지 않는다.

    Args:
        base: 부모 환경 dict. None 이면 os.environ.
        backend: 백엔드 어댑터. None 이면 기본 백엔드다.

    Returns:
        tuple: (env dict, 제거한 키 목록, API 키 환경변수 존재 여부)
    """
    adp = backend or adapter_registry.default()
    env = dict(base if base is not None else os.environ)
    stripped = []
    # 대문자로 비교한다. Windows os.environ 은 키를 올려 주지만, 하네스가
    # 넘기는 base dict 는 소문자일 수 있다.
    python_keys = set(INHERITED_PYTHON_KEYS)
    exact = set(k.upper() for k in adp.env_strip_exact)
    prefixes = tuple(p.upper() for p in adp.env_strip_prefixes)
    for key in list(env):
        upper = key.upper()
        if (upper in exact or upper.startswith(prefixes)
                or upper in python_keys):
            stripped.append(key)
            env.pop(key)
    # 파이프가 utf-8 텍스트 모드라 자식 쪽 인코딩도 맞춘다.
    env["PYTHONIOENCODING"] = "utf-8"
    # 키를 조용히 지우지 않는다. 사용자가 의도한 설정일 수 있다(설계 2-3).
    return env, stripped, bool(adp.api_key_env) and adp.api_key_env in env


def stream_json_user(text, backend=None):
    """stdin 에 쓸 사용자 메시지 한 줄(설계 2-4, PoC 와 동일 포맷).

    직렬화 포맷은 백엔드 고유 지식이라 어댑터로 위임한다
    (docs/7 2-10 경계 6). 함수 이름을 남겨 둔 이유는 앞 회차 하네스가
    이 창구로 포맷을 재기 때문이다.

    Args:
        text: 사용자 입력 원문.
        backend: 백엔드 어댑터. None 이면 기본 백엔드다.
    """
    return (backend or adapter_registry.default()).serialize_user_input(text)


def tree_kill(pid):
    """프로세스와 그 자식 전부를 죽인다(설계 2-1).

    Windows 는 taskkill /F /T /PID 다. 다른 OS 는 MVP 검증 범위 밖이므로
    트리 종료를 구현하지 않고 호출자가 단일 kill 로 떨어뜨리게 False 를 준다.

    Returns:
        tuple: (트리 종료를 시도했는가, 상세 문자열)
    """
    if sys.platform != "win32":
        return False, "tree kill not implemented on %s (design 9)" % sys.platform
    try:
        done = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TASKKILL_TIMEOUT_S,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:  # noqa: BLE001 - 종료 경로는 끝까지 진행해야 한다
        return True, "taskkill raised %r" % (exc,)
    detail = "rc=%s out=%s err=%s" % (
        done.returncode,
        (done.stdout or "").strip()[:200],
        (done.stderr or "").strip()[:200],
    )
    return True, detail


def _callable_arity(fn, cap=3):
    """콜러블이 받을 수 있는 위치 인자 수를 센다(최대 cap).

    S2~S4 하네스의 공장은 `build_spec(resume_session_id=None)` 하나만 받는다.
    S5 는 포스처와 cwd 를 더 넘기고 싶다. 예외를 삼키는 방식(먼저 3개로 부르고
    TypeError 면 1개로)은 공장 **안에서** 난 TypeError 와 구분되지 않는다.
    그래서 서명을 한 번 읽어 결정한다.

    Returns:
        int: 1 이상 cap 이하. 가변 인자(*args/**kwargs)면 cap.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return 1
    n = 0
    for param in sig.parameters.values():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            return cap
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            n += 1
    return max(1, min(cap, n))


class SpawnSpec(object):
    """한 번의 spawn 에 필요한 것 전부.

    argv 조립은 posture 모듈이 하고, 이 클래스는 그 결과를 담아 옮긴다.
    프로세스 계층이 포스처를 모르게 두어야 테스트에서 가짜 자식으로 바꿔 끼울 수 있다.
    """

    def __init__(self, argv, cwd, session_id, env=None, env_stripped=(), api_key_present=False):
        """spawn 1회에 쓸 값들을 담는다.

        Args:
            argv: 띄울 명령 줄.
            cwd: 작업 폴더.
            session_id: 이 spawn 의 세션 id(`--session-id` 또는 `--resume`).
            env: 자식 환경. None 이면 Popen 이 부모 환경을 쓴다.
            env_stripped: child_env 가 제거한 키 목록. 기동 진단에 그대로 나간다.
            api_key_present: 환경에 백엔드의 API 키 변수가 있는가(경고용).
                이름은 어댑터의 `api_key_env` 가 정본이다.
        """
        self.argv = list(argv)
        self.cwd = str(cwd)
        self.session_id = session_id
        self.env = env
        self.env_stripped = list(env_stripped)
        self.api_key_present = bool(api_key_present)


def dev_spec(claude_exe, cwd, model=None, resume_session_id=None, backend=None):
    """S2~S4 개발 구성 SpawnSpec(설계 10-1 조건 1).

    MCP 설정과 사전승인을 주지 않으므로 MCP 도구가 0개이고 개시 이벤트의
    서버 목록이 빈 배열이어야 한다.

    Args:
        claude_exe: 백엔드 실행 파일 경로. 인자 이름은 앞 회차 하네스가
            키워드로 부르는 자리라 바꾸지 않는다.
        cwd: 작업 폴더.
        model: 모델 인자. None 이면 플래그를 생략한다.
        resume_session_id: 있으면 재개 구성.
        backend: 백엔드 어댑터. None 이면 기본 백엔드다.
    """
    adp = backend or adapter_registry.default()
    session_id = adp.new_session_id()
    argv = adp.build_dev_argv(
        claude_exe,
        session_id=session_id,
        resume_session_id=resume_session_id,
        model=model,
    )
    env, stripped, api_key = child_env(backend=adp)
    return SpawnSpec(
        argv,
        cwd,
        resume_session_id or session_id,
        env=env,
        env_stripped=stripped,
        api_key_present=api_key,
    )


class _ReaderThread(QThread):
    """파이프 한쪽을 줄 단위로 빨아들이는 스레드.

    stdout 쪽은 여기서 녹화와 JSON 파싱까지 한다. 큰 tool_result(수 MB) 파싱이
    GUI 를 막지 않게 하려는 것이 설계 2-2 의 이유다.
    """

    def __init__(self, stream, out_queue, tag, logbook=None, parent=None):
        """참조만 잡는다. 읽기는 run() 에서 시작한다.

        Args:
            stream: 읽을 파이프(자식의 stdout 또는 stderr).
            out_queue: 읽은 줄을 올릴 큐.
            tag: "out" 또는 "err". 큐 항목의 종류를 가른다.
            logbook: stdout 원문 녹화 대상. stderr 쪽은 None 이다.
            parent: QObject 부모.
        """
        super().__init__(parent)
        self._stream = stream
        self._queue = out_queue
        self._tag = tag
        self._logbook = logbook

    def run(self):
        """EOF 까지 읽는다. 끝나면 <tag>_eof 를 큐에 넣는다."""
        try:
            for line in iter(self._stream.readline, ""):
                raw = line.rstrip("\r\n")
                ts = time.time()
                if self._tag == "out":
                    # 파싱 전에 원문을 녹화한다(설계 2-6, 7-4).
                    if self._logbook is not None:
                        self._logbook.write_stdout_line(raw)
                    try:
                        event = json.loads(raw) if raw.strip() else None
                    except (ValueError, TypeError):
                        event = None
                    self._queue.put(("out", StreamLine(ts, raw, event)))
                else:
                    self._queue.put(("err", StreamLine(ts, raw, None)))
        except Exception as exc:  # noqa: BLE001 - 리더가 조용히 죽으면 안 된다
            self._queue.put((self._tag + "_err", StreamLine(time.time(), repr(exc), None)))
        finally:
            self._queue.put((self._tag + "_eof", StreamLine(time.time(), "", None)))
            try:
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass


class _WriterThread(QThread):
    """stdin 에 한 줄씩 쓰는 유일한 스레드(설계 2-4).

    라이터를 하나로 두는 이유 둘. (1) 파이프 write 는 블로킹 가능하므로 GUI 에서
    하면 긴 텍스트 붙여넣기에 UI 가 멈춘다. (2) 한 줄 = 한 메시지인 stream-json
    에서 줄이 섞이면 세션이 깨진다.
    """

    def __init__(self, stdin, in_queue, report_queue, parent=None):
        """참조만 잡는다. 쓰기는 run() 에서 시작한다.

        Args:
            stdin: 쓸 파이프(자식의 stdin).
            in_queue: 보낼 줄이 들어오는 큐. None 센티넬이 종료 신호다.
            report_queue: write 예외를 올릴 큐. 드레인이 진단으로 남긴다.
            parent: QObject 부모.
        """
        super().__init__(parent)
        self._stdin = stdin
        self._queue = in_queue
        self._report = report_queue

    def run(self):
        """None 센티넬을 받으면 끝낸다."""
        while True:
            payload = self._queue.get()
            if payload is None:
                break
            try:
                self._stdin.write(payload)
                self._stdin.flush()
            except Exception as exc:  # noqa: BLE001
                self._report.put(
                    ("writer_err", StreamLine(time.time(), repr(exc), None))
                )
                break


class BackendProcess(QObject):
    """독 1개가 소유하는 claude CLI 프로세스 1개(설계 2-1).

    시그널 4개만 쓴다.

        events_drained(list[StreamLine])  50 ms 배치. 파싱된 stdout 이벤트.
        stderr_line(str)                  진단 패널 전용. 전사에 섞지 않는다.
        backend_died(int, str)            종료코드와 stderr 꼬리.
        gate_result(dict)                 기동 자기점검 판정(설계 3-4).
        posture_changed(str)              포스처가 바뀐 재spawn 이 끝났다(S5-4).

    설계 2-6 이 "별도 신호는 2개" 라고 한 것은 이벤트 1개당 시그널을 만들지 말라는
    뜻이다. events_drained 는 그 배치 채널이고, gate_result 는 게이트 결과를
    입력 차단 배선에 넘기기 위한 창구다.

    S5 가 더한 것은 세 가지다.
        gate_blocked   게이트가 깨지면 전송을 막는다(S5-1). 설계 3-4 의
                       "입력 박스를 열지 않는다" 가 여기서 집행된다.
        elevate()      포스처 상승 재spawn + --resume(S5-4). 두 반쪽은 각각
                       실측됐고(D05-a, D01) 조합이 D23 이다.
        restart_with() cwd 변경 재spawn(S5-3).
    """

    events_drained = pyqtSignal(object)
    stderr_line = pyqtSignal(str)
    backend_died = pyqtSignal(int, str)
    gate_result = pyqtSignal(object)
    posture_changed = pyqtSignal(str)

    def __init__(self, spec_builder, log_dir=None, expect_tools=None,
                 expect_mcp_server=None, auto_restart=True,
                 expect_disallowed=(), posture_name=None,
                 expect_mcp_servers=None, expect_allowed=(), parent=None,
                 backend=None):
        """참조만 잡는다. 프로세스는 start() 에서 뜬다.

        Args:
            spec_builder: SpawnSpec 을 만드는 콜러블. 받는 인자 수에 따라
                (resume_session_id), (resume_session_id, posture),
                (resume_session_id, posture, cwd) 중 하나로 불린다. 인자 수는
                inspect 로 한 번 재서 캐시한다 - S2~S4 하네스가 1인자 공장을
                쓰고 있어 그쪽을 깨지 않기 위함이다. 재시작 때 같은 콜러블을
                다시 부른다. 플래그는 세션에 붙어 다니지 않으므로(설계 2-5)
                매번 다시 줘야 한다.
            log_dir: 녹화/진단 폴더. None 이면 설계 7-4 기본 경로.
            expect_tools: 게이트가 기대하는 내장 노출 도구 목록. None 이면
                어댑터의 기본 포스처 노출 목록이다(0.5.5 리팩터 전 기본값
                `posture.BUILTIN_TOOLS_R` 와 같은 값).
            expect_mcp_server: 게이트가 기대하는 MCP 서버 이름. 개발 구성은 None.
            auto_restart: 예기치 않은 사망 시 자동 재시작 여부.
            expect_disallowed: 게이트 3이 쓰는 `--disallowedTools` 이름들.
            posture_name: 지금 포스처. elevate() 가 바꾼다. None 이면
                어댑터의 기본 포스처다(리팩터 전 기본값 `posture.POSTURE_R`
                와 같은 값).
            expect_mcp_servers: 게이트 4 가 볼 ((서버, 심각도), ...) 목록
                (0.2.0). 제품은 posture.EXPECT_MCP_SERVERS_PRODUCT 를 준다.
                주면 expect_mcp_server 를 대신한다.
            expect_allowed: 게이트 6 이 쓰는 `--allowedTools` 이름들(0.3.1).
                포스처 spec 의 allowed_tools 를 그대로 받는다. 빈 값이면 그
                검사를 건너뛴다 - `--allowedTools` 없는 개발 구성이 있다.
            backend: 백엔드 어댑터(0.5.5, docs/7 2-10). None 이면 기본
                백엔드다. 이 층은 백엔드 고유 플래그 이름도 이벤트 스키마도
                모르고, 게이트 판정과 입력 직렬화를 어댑터에 물어 본다.
        """
        super().__init__(parent)
        self._backend = backend or adapter_registry.default()
        self._spec_builder = spec_builder
        self._builder_arity = _callable_arity(spec_builder)
        self._log_dir = log_dir
        self._expect_tools = tuple(self._backend.default_builtin_tools
                                   if expect_tools is None else expect_tools)
        self._expect_mcp_server = expect_mcp_server
        self._expect_mcp_servers = (tuple(expect_mcp_servers)
                                    if expect_mcp_servers else None)
        self._auto_restart = bool(auto_restart)
        self._expect_disallowed = tuple(expect_disallowed)
        # 0.3.1: 게이트 6(노출/사전승인 정합)이 읽는다. elevate() 가 포스처와
        # 함께 바꿔야 한다 - 안 바꾸면 W 로 올린 직후 R 의 allowlist 로
        # 판정해 Write/Edit 가 고아로 잡힌다.
        self._expect_allowed = tuple(expect_allowed)
        self.posture_name = (self._backend.default_posture_name
                             if posture_name is None else posture_name)
        self.cwd_override = None

        # 수집 서버가 지금 붙어 있는가(0.2.0). 소프트 판정이라 입력을 막지
        # 않고, UI 가 수집 버튼만 비활성하는 데 쓴다. 게이트가 돌기 전에는
        # None 이다 - 모른다는 뜻이고 "없다" 가 아니다.
        self.collect_connected = None

        # 게이트 상태(S5-1). 깨지면 전송을 막고 재시작한다.
        self.gate_blocked = False
        self.gate_block_reason = ""
        self.gate_restart_count = 0
        # 재시작을 예약했는가. UI 문구가 "다시 띄웁니다" 와 "멈춥니다" 로
        # 갈라지므로 추측하지 않고 이 값을 읽게 한다.
        self.gate_restart_pending = False

        self._proc = None
        self._spec = None
        self.logbook = None
        # 레다크션(0.2.1, 설계 docs/2 5-4). 독이 소유하는 Redactor 를 붙여 두면
        # spawn 마다 새로 열리는 로그북이 그것을 물려받는다. 로그북은 spawn
        # 마다 교체되므로 레다크터를 로그북이 아니라 여기에 들고 있어야
        # 재spawn(취소, 상승, cwd 변경) 뒤에도 치환이 이어진다.
        self.redactor = None

        self._queue = queue.Queue()
        self._write_queue = None
        self._out_reader = None
        self._err_reader = None
        self._writer = None

        self._timer = QTimer(self)
        self._timer.setInterval(DRAIN_INTERVAL_MS)
        self._timer.timeout.connect(self._on_drain)

        self._stderr_tail = collections.deque(maxlen=200)
        self._out_eof = False
        self._dead_since = None
        self._stopping = False
        self._busy = False
        self._pending_prefix = None

        # 게이트 상태
        self.first_init_summary = None
        self.last_gate = None
        # 마지막 init 원본(S6). 게이트 요약에는 plugins/skills 가 없어서
        # 탐지(설계 6-4)가 원본을 봐야 한다. 시그널을 새로 만들지 않는 이유는
        # init 1건당 gate_result 가 이미 나가기 때문이다(설계 2-6: 이벤트당
        # 시그널을 만들지 않는다). 수신 측은 그 슬롯에서 이 값을 읽는다.
        self.last_init_event = None

        # 재시작 장부. (시각, 사유) 를 윈도우 안에서만 센다.
        self._restart_marks = collections.deque()
        self.session_id = None
        self.restart_count = 0

    # ------------------------------------------------------------------
    # 수명
    # ------------------------------------------------------------------

    def is_running(self):
        """프로세스가 떠 있고 아직 죽지 않았는가."""
        return self._proc is not None and self._proc.poll() is None

    def is_busy(self):
        """턴이 진행 중인가. 설계 2-4 의 입력 차단 판정에 쓴다."""
        return self._busy

    def _make_spec(self, resume_session_id):
        """공장을 불러 SpawnSpec 을 받는다. 인자 수는 생성 시 캐시했다."""
        args = (resume_session_id, self.posture_name, self.cwd_override)
        return self._spec_builder(*args[: self._builder_arity])

    def start(self, resume_session_id=None):
        """프로세스를 띄우고 스레드 3개와 드레인 타이머를 올린다.

        Returns:
            bool: spawn 성공 여부. 실패 사유는 진단 로그에 남는다.
        """
        if self.is_running():
            return True
        spec = self._make_spec(resume_session_id)
        self._spec = spec
        self.session_id = spec.session_id
        self._stopping = False
        self._out_eof = False
        self._dead_since = None
        self._busy = False
        # 새 세션이면 드리프트 기준(게이트 5)도 새로 잡는다. 이전 세션의 요약과
        # 비교하면 session_id 가 달라 매번 깨진다. 재개(--resume)는 같은
        # session_id 가 돌아오므로(D01) 기준을 유지한다. 단 포스처를 올린
        # 재개는 tools_n 이 달라지므로 elevate() 가 따로 비운다.
        if not resume_session_id:
            self.first_init_summary = None
        # 재기동은 게이트에 다시 기회를 준다. 무한 루프는 gate_restart_count 가 막는다.
        self.gate_blocked = False
        self.gate_block_reason = ""
        self._queue = queue.Queue()
        self._write_queue = queue.Queue()
        self._stderr_tail.clear()
        # 재개면 같은 session_id 라 같은 jsonl 에 이어 쌓인다.
        self.logbook = SessionLogbook(self._log_dir, session_id=spec.session_id,
                                      redactor=self.redactor)

        # 재spawn 뒤 "로그가 끊겼다" 로 오독되는 것을 막는 줄이다. 진단 파일은
        # spawn 마다 새로 생기고(파일명이 시각) jsonl 은 재개면 같은 파일에
        # 이어 쌓이므로, 두 경로와 resume 여부를 새 파일의 머리에 적어 둔다.
        self.logbook.diag(
            "logfiles",
            "resume=%s jsonl=%s diag=%s"
            % (bool(resume_session_id), self.logbook.jsonl_path,
               self.logbook.diag_path),
        )
        self.logbook.diag("argv", " ".join(spec.argv))
        self.logbook.diag("posture", str(self.posture_name))
        self.logbook.diag("cwd", spec.cwd)
        self.logbook.diag("env_stripped", ",".join(spec.env_stripped) or "(none)")
        if spec.api_key_present:
            # 설계 2-3: 조용히 지우지 않고 경고만 남긴다. 구독이 아니라 API
            # 과금으로 실행될 수 있다(D11 미측).
            self.logbook.diag(
                "warn_api_key",
                "%s present - may bill API instead of subscription"
                % self._backend.api_key_env,
            )

        t_spawn = time.time()
        try:
            os.makedirs(spec.cwd, exist_ok=True)
            self._proc = subprocess.Popen(
                spec.argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=spec.cwd,
                env=spec.env,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception as exc:  # noqa: BLE001
            self._proc = None
            self.logbook.diag("spawn", "FAIL %r" % (exc,))
            return False
        self.logbook.diag(
            "spawn",
            "PASS pid=%d latency_s=%.3f session_id=%s"
            % (self._proc.pid, time.time() - t_spawn, spec.session_id),
        )

        self._out_reader = _ReaderThread(self._proc.stdout, self._queue, "out", self.logbook, self)
        self._err_reader = _ReaderThread(self._proc.stderr, self._queue, "err", None, self)
        self._writer = _WriterThread(self._proc.stdin, self._write_queue, self._queue, self)
        self._out_reader.start()
        self._err_reader.start()
        self._writer.start()
        self._timer.start()
        return True

    def stop(self, reason="stop"):
        """사용자/플러그인 요청으로 끝낸다. 자동 재시작을 하지 않는다."""
        self._stopping = True
        self._timer.stop()
        self._shutdown_child(reason)
        self._join_threads()
        if self.logbook is not None:
            self.logbook.diag("stopped", reason)
            self.logbook.close()

    def request_cancel(self):
        """취소. 턴 중단이 아니라 백엔드 재시작이다(설계 2-5).

        제어 프로토콜 interrupt 는 미측(V28-A08)이고 stdin 닫기는 현재 턴을
        끝까지 수행한 뒤 종료하므로, 즉시 멈추는 유일한 수단이 트리 종료다.
        사용자가 고른 중단이므로 자동 재시작 백오프 장부에는 세지 않는다.

        Returns:
            bool: 재spawn 성공 여부.
        """
        resume = self.session_id
        if self.logbook is not None:
            self.logbook.diag("cancel", "resume=%s" % resume)
        self._stopping = True
        self._timer.stop()
        self._shutdown_child("cancel")
        self._join_threads()
        if self.logbook is not None:
            self.logbook.close()
        self._pending_prefix = CANCEL_NOTICE
        ok = self.start(resume_session_id=resume)
        return ok

    # ------------------------------------------------------------------
    # 입력
    # ------------------------------------------------------------------

    def queue_notice_prefix(self, text):
        """다음 사용자 메시지 앞에 붙일 한 줄을 예약한다(설계 2-5, 8).

        취소 복구와 프로젝트 전환이 같은 창구를 쓴다. 이미 예약된 줄이 있으면
        덮지 않고 이어 붙인다 - 취소와 프로젝트 전환이 겹칠 수 있고, 둘 중
        하나를 모델에게 숨기면 안 된다.
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
        if self.logbook is not None:
            self.logbook.diag("prefix_queued", self._pending_prefix)

    def pending_prefix(self):
        """예약된 줄. 검증 하네스가 읽는다."""
        return self._pending_prefix or ""

    def send(self, text):
        """사용자 메시지를 라이터 큐에 넣는다.

        큐에 2개를 쌓지 않는다(설계 2-4). 턴이 진행 중이면 거부한다. 동시 요청이
        QGIS MCP 단일 소켓 제약과 겹치면 원인 추적이 불가능해진다.

        Returns:
            bool: 큐에 들어갔는가.
        """
        if not self.is_running() or self._write_queue is None:
            return False
        if self._busy:
            return False
        if self.gate_blocked:
            # 설계 3-4 "하나라도 어긋나면 입력 박스를 열지 않는다" 의 집행 지점.
            # 포스처를 확인할 수 없는 상태에서 또 한 턴을 과금하지 않는다.
            if self.logbook is not None:
                self.logbook.diag("send_blocked", self.gate_block_reason)
            return False
        body = text
        if self._pending_prefix:
            body = self._pending_prefix + "\n" + text
            self._pending_prefix = None
        payload = stream_json_user(body, backend=self._backend) + "\n"
        self._busy = True
        self._write_queue.put(payload)
        if self.logbook is not None:
            self.logbook.diag(
                "sent", "bytes=%d" % len(payload.encode("utf-8"))
            )
        return True

    # ------------------------------------------------------------------
    # 드레인
    # ------------------------------------------------------------------

    def _on_drain(self):
        """50 ms 틱. 큐를 비우고 배치 1개로 신호 1회(설계 2-6)."""
        batch = []
        stderr_lines = []
        died = False
        for _ in range(DRAIN_MAX_PER_TICK):
            try:
                tag, line = self._queue.get_nowait()
            except queue.Empty:
                break
            if tag == "out":
                batch.append(line)
                self._inspect(line)
            elif tag == "err":
                if line.raw.strip():
                    stderr_lines.append(line.raw)
                    self._stderr_tail.append(line.raw)
            elif tag == "out_eof":
                self._out_eof = True
                died = True
            elif tag == "err_eof":
                pass
            else:
                # 리더/라이터 예외. 진단에만 남긴다.
                if self.logbook is not None:
                    self.logbook.diag(tag, line.raw)
                self._stderr_tail.append("%s %s" % (tag, line.raw))

        if batch:
            self.events_drained.emit(batch)
        for raw in stderr_lines:
            self.stderr_line.emit(raw)

        # 사망 감지(설계 2-5). EOF 가 1차 신호다. poll() 은 EOF 가 오지 않는
        # 경우를 위한 보조 신호이고, 남은 줄을 유실하지 않게 유예를 둔다.
        if self._stopping:
            return
        if died:
            self._on_death()
            return
        if self._proc is not None and self._proc.poll() is not None:
            now = time.monotonic()
            if self._dead_since is None:
                self._dead_since = now
            elif now - self._dead_since >= DEATH_GRACE_S:
                self._on_death()
        else:
            self._dead_since = None

    def _inspect(self, line):
        """프로세스 계층이 꼭 봐야 하는 두 이벤트만 본다.

        해석은 S3 상태머신이 한다. 여기서 보는 것은 (1) 기동 자기점검을 돌려야
        하는 세션 개시 이벤트, (2) 턴 중 입력 차단을 풀어야 하는 턴 종료
        이벤트 둘뿐이다.

        어느 이벤트가 그 둘인지는 **백엔드마다 다르다**(docs/7 2-10 경계 3).
        Claude 는 `system/init` 과 최상위 `result` 이고, 그 판별을 어댑터에
        물어 본다 - 여기서 문자열로 비교하면 제2 백엔드가 이 함수를 고치게
        된다.
        """
        ev = line.event
        if not isinstance(ev, dict):
            return
        if self._backend.is_session_init_event(ev):
            # 원본을 먼저 보관한다. gate_result 슬롯이 이것을 읽어 탐지를 돌린다.
            self.last_init_event = ev
            self._run_gate(ev)
        elif self._backend.is_turn_end_event(ev):
            self._busy = False

    def _run_gate(self, init_event):
        """init 게이트를 돌리고 판정을 로그와 시그널로 낸다(설계 3-4)."""
        result = self._backend.check_init(
            init_event,
            expect_tools=self._expect_tools,
            expect_mcp_server=self._expect_mcp_server,
            first_init=self.first_init_summary,
            expect_disallowed=self._expect_disallowed,
            expect_mcp_servers=self._expect_mcp_servers,
            expect_allowed=self._expect_allowed,
        )
        if self.first_init_summary is None:
            self.first_init_summary = result["summary"]
        self.last_gate = result
        # 소프트 축을 따로 들고 있는다. 게이트가 깨지지 않아도 수집 버튼은
        # 꺼질 수 있고, UI 가 그 사실을 추측하지 않고 읽어야 한다.
        if self._expect_mcp_servers:
            self.collect_connected = not self._backend.soft_server_missing(result)
        if self.logbook is not None:
            self.logbook.diag("gate", self._backend.format_gate(result))
            warns = self._backend.warn_checks(result)
            if warns:
                # 경고는 입력을 막지 않는다. 그래서 gate_blocked 와 다른 태그로
                # 남겨야 로그만 보고 "막혔는가" 를 가를 수 있다.
                self.logbook.diag("gate_warn", ",".join(str(w) for w in warns))
            for item in result["items"]:
                self.logbook.diag(
                    "gate_item",
                    "%s %s expected=%s observed=%s"
                    % (item["check"], item["status"], item["expected"], item["observed"]),
                )
        # 차단 상태를 먼저 세우고 그 뒤에 알린다. 순서를 뒤집으면 UI 가
        # "막혔다" 를 보기 전에 판정을 받아 버튼 상태가 한 틱 어긋난다.
        if not result["ok"]:
            self._on_gate_failure(result)
        self.gate_result.emit(result)

    def _on_gate_failure(self, result):
        """게이트가 깨졌다. 전송을 막고 한 번만 재시작한다(S5-1).

        즉시 재시작하지 않는 이유 둘.
            (1) 이 함수는 드레인 틱 안에서 불린다. 거기서 자식을 교체하면 그 틱이
                쓰던 큐가 바뀐다.
            (2) 게이트를 깨뜨린 그 배치가 UI 로 올라가기 전에 끊으면 사용자가
                이유를 볼 수 없다.
        그래서 차단만 즉시 걸고 재시작은 다음 이벤트 루프 턴으로 넘긴다.
        """
        failed = self._backend.failed_checks(result)
        self.gate_blocked = True
        self.gate_block_reason = "gate failed: " + ",".join(str(f) for f in failed)
        if self.logbook is not None:
            self.logbook.diag("gate_blocked", self.gate_block_reason)
        if self.gate_restart_count >= GATE_RESTART_MAX:
            # 한 번 다시 띄워도 같은 판정이면 환경이 플래그를 무시하는 것이다.
            # 더 재시작하면 턴마다 과금만 쌓인다. 수동 조치에 맡긴다.
            self.gate_restart_pending = False
            if self.logbook is not None:
                self.logbook.diag(
                    "gate_restart_giveup",
                    "%d restart(s) already used - input stays blocked"
                    % self.gate_restart_count,
                )
            return
        self.gate_restart_count += 1
        self.gate_restart_pending = True
        if self.logbook is not None:
            self.logbook.diag(
                "gate_restart_scheduled",
                "n=%d delay_s=%.1f discard_turn=True"
                % (self.gate_restart_count, GATE_RESTART_DELAY_S),
            )
        QTimer.singleShot(int(GATE_RESTART_DELAY_S * 1000), self._do_gate_restart)

    def _do_gate_restart(self):
        """게이트 실패 재시작. 새 세션으로 띄운다.

        `--resume` 를 쓰지 않는다. 설계 3-4 가 "그 턴의 결과를 버리고" 라고 적었고,
        포스처가 확인되지 않은 세션의 맥락을 이어받으면 버린 것이 아니다.
        맥락을 잃는 대신 상태를 확실히 한다 - 보수적으로 고른 쪽이다.
        """
        if self._stopping:
            return
        if self.logbook is not None:
            self.logbook.diag("gate_restart", "fresh session (no --resume)")
        self.gate_restart_pending = False
        self._hard_cycle("gate_restart")
        ok = self.start()
        if self.logbook is not None:
            self.logbook.diag("gate_restarted", "ok=%s" % ok)

    # ------------------------------------------------------------------
    # 포스처 상승과 cwd 변경 (S5-3, S5-4)
    # ------------------------------------------------------------------

    def _hard_cycle(self, reason):
        """지금 자식을 트리 종료하고 스레드를 정리한다. 재spawn 직전 공통부."""
        self._stopping = True
        self._timer.stop()
        self._shutdown_child(reason)
        self._join_threads()
        if self.logbook is not None:
            self.logbook.diag("cycled", reason)
            self.logbook.close()
        self._stopping = False

    def elevate(self, posture_name, expect_tools, expect_disallowed=None,
                expect_allowed=None):
        """포스처를 올려 재spawn 한다. 맥락은 `--resume` 로 가져온다(S5-4).

        두 반쪽이 각각 실측됐다. allowlist 상승이 거부를 뒤집는 것(D05-a)과
        `--resume` 가 같은 session_id 와 직전 턴 맥락을 돌려주는 것(D01).
        **조합은 D23 이고 이 메서드가 그 측정 대상이다.**

        플래그는 세션에 붙어 다니지 않는다(D01 실측: 재개 세션의 init 도
        permissionMode 를 새로 받았다). 그래서 상승이 재spawn 으로 성립한다.

        0.2.0: 포스처가 셋이 되어 R -> C 도 이 경로를 쓴다. C 의 내장 노출은
        R 과 같으므로 게이트 2 의 기대값이 바뀌지 않는다 - 그래서 C 전환의
        성공은 게이트로 단정되지 않고 **첫 수집 도구 호출의 성패로만** 드러
        난다(설계 docs/2 3-2 항목 1, 장부 G5 와 같은 축).

        Args:
            posture_name: 올릴 포스처 이름.
            expect_tools: 그 포스처의 내장 노출 목록. 게이트 기대값을 같이
                바꿔야 한다 - 안 바꾸면 올린 직후 게이트 2가 깨져 입력이 막힌다.
            expect_disallowed: 그 포스처의 제외 목록. None 이면 그대로 둔다.
            expect_allowed: 그 포스처의 사전승인 목록(0.3.1). None 이면 그대로
                둔다. R -> W 에서 이것을 안 바꾸면 게이트 6 이 R 의 allowlist
                로 W 의 노출을 재어 Write/Edit 를 고아로 FAIL 한다.

        Returns:
            bool: 재spawn 성공 여부.
        """
        resume = self.session_id
        if self.logbook is not None:
            self.logbook.diag(
                "elevate",
                "from=%s to=%s resume=%s" % (self.posture_name, posture_name, resume),
            )
        self._hard_cycle("elevate")
        self.posture_name = posture_name
        self._expect_tools = tuple(expect_tools)
        if expect_disallowed is not None:
            self._expect_disallowed = tuple(expect_disallowed)
        if expect_allowed is not None:
            self._expect_allowed = tuple(expect_allowed)
        # 노출 도구 수가 바뀌므로 드리프트 기준을 다시 잡는다. 안 비우면
        # 올린 뒤 첫 init 이 tools_n 차이로 게이트 5를 깨뜨린다.
        self.first_init_summary = None
        ok = self.start(resume_session_id=resume)
        if self.logbook is not None:
            self.logbook.diag("elevated", "ok=%s posture=%s" % (ok, posture_name))
        if ok:
            self.posture_changed.emit(posture_name)
        return ok

    def new_session(self, posture_name, expect_tools, expect_disallowed=None,
                    expect_allowed=None):
        """맥락을 잇지 않고 **새 세션**으로 다시 띄운다 (U16 [새 대화]).

        `elevate()` 와 기전이 같고 두 가지가 다르다.

            1. `--resume` 을 **쓰지 않는다.** 그것이 이 메서드의 존재 이유다 -
               사용자가 "처음부터 다시" 를 요청했고, 재개하면 모델이 이전
               대화를 그대로 들고 온다. `start()` 가 resume 없이 불리면 새
               session_id 가 나고 드리프트 기준(게이트 5)도 새로 잡힌다.
            2. 포스처가 **내려갈 수도 있다.** elevate 는 올리는 경로였고 이쪽은
               기본값(R)으로 되돌리는 호출이 정상이다. 세션을 버리므로 상승을
               받아 두었던 사용자 승인도 그 세션과 함께 사라진다.

        이미 쓴 세션 jsonl 은 **지우지 않는다.** 감사 경로이고, 새 세션은 새
        파일에 쌓인다(`SessionLogbook` 이 session_id 로 파일을 가른다).

        Args:
            posture_name: 새 세션의 포스처. 보통 `posture.POSTURE_R`.
            expect_tools: 그 포스처의 내장 노출 목록. 게이트 2 의 기대값이다.
            expect_disallowed: 그 포스처의 제외 목록. None 이면 그대로 둔다.
            expect_allowed: 그 포스처의 사전승인 목록. None 이면 그대로 둔다.
                R 로 내려오면서 이것을 안 바꾸면 게이트 6 이 W 의 allowlist 로
                R 의 노출을 재어 어긋난다(elevate 의 거울상 함정).

        Returns:
            bool: 재spawn 성공 여부.
        """
        previous = self.posture_name
        if self.logbook is not None:
            self.logbook.diag(
                "new_session",
                "from=%s to=%s resume=None" % (previous, posture_name))
        self._hard_cycle("new_session")
        self.posture_name = posture_name
        self._expect_tools = tuple(expect_tools)
        if expect_disallowed is not None:
            self._expect_disallowed = tuple(expect_disallowed)
        if expect_allowed is not None:
            self._expect_allowed = tuple(expect_allowed)
        # 노출 도구 수가 바뀔 수 있으므로 드리프트 기준을 다시 잡는다.
        # start() 도 새 세션이면 같은 일을 하지만, 실패해서 start 까지 못 가는
        # 경우에도 옛 세션의 요약이 남아 있지 않게 여기서 먼저 비운다.
        self.first_init_summary = None
        ok = self.start()
        if self.logbook is not None:
            self.logbook.diag(
                "new_session_started",
                "ok=%s posture=%s session=%s" % (ok, posture_name,
                                                 self.session_id))
        if ok and previous != posture_name:
            self.posture_changed.emit(posture_name)
        return ok

    def restart_with_cwd(self, cwd):
        """cwd 를 바꿔 재spawn 한다(S5-3).

        cwd 는 모델의 파일 접근 범위와 CLAUDE.md 자동 탐색 범위를 동시에 정하므로
        프로세스를 다시 띄우는 수밖에 없다. 맥락은 `--resume` 로 가져온다.

        Returns:
            bool: 재spawn 성공 여부.
        """
        resume = self.session_id
        if self.logbook is not None:
            self.logbook.diag("cwd_change", "to=%s resume=%s" % (cwd, resume))
        self._hard_cycle("cwd_change")
        self.cwd_override = str(cwd)
        ok = self.start(resume_session_id=resume)
        if self.logbook is not None:
            self.logbook.diag("cwd_changed", "ok=%s cwd=%s" % (ok, cwd))
        return ok

    # ------------------------------------------------------------------
    # 사망과 재시작
    # ------------------------------------------------------------------

    def _on_death(self):
        """사망 처리. 종료코드와 stderr 꼬리를 남기고 재시작 여부를 정한다."""
        self._timer.stop()
        rc = self._reap()
        tail = "\n".join(list(self._stderr_tail)[-20:])
        if self.logbook is not None:
            self.logbook.diag("died", "rc=%s out_eof=%s" % (rc, self._out_eof))
            self.logbook.diag_stderr_tail(self._stderr_tail)
        self._join_threads()
        self._busy = False
        self.backend_died.emit(rc if rc is not None else -1, tail)

        if not self._auto_restart:
            if self.logbook is not None:
                self.logbook.close()
            return
        delay = self._next_restart_delay()
        if delay is None:
            if self.logbook is not None:
                self.logbook.diag(
                    "restart_giveup",
                    "%d restarts within %.0fs - manual restart only"
                    % (RESTART_MAX, RESTART_WINDOW_S),
                )
                self.logbook.close()
            return
        if self.logbook is not None:
            self.logbook.diag("restart_scheduled", "delay_s=%.1f" % delay)
            self.logbook.close()
        resume = self.session_id
        QTimer.singleShot(int(delay * 1000), lambda: self._do_restart(resume))

    def _next_restart_delay(self):
        """백오프 2s/8s/30s, 5분 내 3회까지(설계 2-5).

        Returns:
            float or None: 대기 시간. None 이면 자동 재시작을 포기한다.
        """
        now = time.monotonic()
        while self._restart_marks and now - self._restart_marks[0] > RESTART_WINDOW_S:
            self._restart_marks.popleft()
        if len(self._restart_marks) >= RESTART_MAX:
            return None
        delay = RESTART_DELAYS_S[min(len(self._restart_marks), len(RESTART_DELAYS_S) - 1)]
        self._restart_marks.append(now)
        return delay

    def _do_restart(self, resume_session_id):
        """지연 뒤 실제 재spawn. 맥락은 --resume 으로 살린다(D01 PASS)."""
        if self._stopping:
            return
        self.restart_count += 1
        ok = self.start(resume_session_id=resume_session_id)
        if self.logbook is not None:
            self.logbook.diag("restarted", "ok=%s n=%d" % (ok, self.restart_count))

    # ------------------------------------------------------------------
    # 내부 - 자식 정리
    # ------------------------------------------------------------------

    def _shutdown_child(self, reason):
        """트리 종료. 고아 MCP 브리지를 남기지 않는 유일한 경로다(설계 2-1)."""
        proc = self._proc
        if proc is None:
            return
        pid = proc.pid
        if proc.poll() is None:
            tried, detail = tree_kill(pid)
            if self.logbook is not None:
                self.logbook.diag("tree_kill", "%s pid=%d %s" % (reason, pid, detail))
            if not tried:
                try:
                    proc.kill()
                except Exception as exc:  # noqa: BLE001
                    if self.logbook is not None:
                        self.logbook.diag("kill", "FAIL %r" % (exc,))
        rc = self._reap()
        if self.logbook is not None:
            self.logbook.diag("exit_code", str(rc))

    def _reap(self):
        """종료코드를 수거한다. 파이프와 라이터 큐도 여기서 닫는다."""
        proc = self._proc
        if proc is None:
            return None
        try:
            if proc.stdin is not None and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        if self._write_queue is not None:
            self._write_queue.put(None)
        try:
            return proc.wait(timeout=REAP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                return proc.wait(timeout=REAP_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                return None
        except Exception:  # noqa: BLE001
            return None

    def _join_threads(self):
        """스레드 3개를 정리한다. QThread.wait 은 ms 단위다."""
        if self._write_queue is not None:
            self._write_queue.put(None)
        for th in (self._out_reader, self._err_reader, self._writer):
            if th is None:
                continue
            try:
                th.wait(int(REAP_TIMEOUT_S * 1000))
            except Exception:  # noqa: BLE001
                pass
        self._out_reader = None
        self._err_reader = None
        self._writer = None
