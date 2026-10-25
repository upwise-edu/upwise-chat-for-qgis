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
import uuid as uuid_mod
from pathlib import Path

from qgis.PyQt.QtCore import QObject, QThread, QTimer, pyqtSignal

from . import adapter_registry, protocol
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

# ----- 고아 미결 uuid 백스톱 상한 (0.6.1, V47-A03) -----
#
# 왜 상한이 필요한가
#     미결 집합은 lifecycle 의 `completed`/`cancelled` 로만 빈다. 번들
#     스키마에 `detachedToolCall: true` 경로가 있어 **큐에 쌓인 메시지가
#     한 턴에 접힐(coalesce) 수 있고** `[스키마]`, 접힌 uuid 에 종결
#     이벤트가 오지 않으면 그 uuid 는 영구히 남는다. 그러면 `is_busy()` 가
#     영구 True 가 되고 UI 가 입력을 영구히 게이트한다 - 사용자 원 불만
#     ("분석 진행 중에 채팅을 넣을 수 없다") 과 같은 증상이다.
#     주 처방은 `result.user_message_uuids` 기준 정산이고(`_settle_by_result`)
#     이 두 상한은 그것도 비껴간 경우만 받는 백스톱이다.
#
# 왜 턴 수를 시계로 쓰는가 (2)
#     `result` 는 "CLI 가 턴 하나를 끝냈다" 는 증거다. 그래서 이 시계는
#     **CLI 가 도는 동안에는 전진하지 않는다** - 반대 방향 위험(CLI 가
#     실행 중인데 한가하다고 믿는 것)을 구조적으로 못 만든다. 1 로 두면
#     정상 인계(앞 턴 result 시점에 다음 메시지가 `queued`)를 오판하므로
#     2 다. 즉 자기 앞 턴과 자기 턴이 둘 다 닫혔는데도 전이가 없었던
#     uuid 만 걸린다.
ORPHAN_PENDING_TURNS_MAX = 2

# 왜 침묵을 두 번째 시계로 쓰는가 (180초)
#     result 가 더 오지 않으면 위 턴 시계는 멈춘다. 그 경우의 유계 시간이
#     필요하고, 기준은 경과가 아니라 **침묵**이다(설계 4-5 워치독과 같은
#     판별). 상태머신의 침묵 경고 임계가 120초이므로(machine.SILENCE_WARN_S)
#     그 1.5배로 둔다 - 사용자가 침묵 경고를 먼저 보고, 그 뒤에 백스톱이
#     돈다. 이 시계는 `started` 가 하나도 없을 때만 쓴다(아래 sweep 참조).
ORPHAN_PENDING_SILENCE_S = 180.0

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


def stream_json_user(text, backend=None, uuid=None):
    """stdin 에 쓸 사용자 메시지 한 줄(설계 2-4, PoC 와 동일 포맷).

    직렬화 포맷은 백엔드 고유 지식이라 어댑터로 위임한다
    (docs/7 2-10 경계 6). 함수 이름을 남겨 둔 이유는 앞 회차 하네스가
    이 창구로 포맷을 재기 때문이다.

    Args:
        text: 사용자 입력 원문.
        backend: 백엔드 어댑터. None 이면 기본 백엔드다.
        uuid: 이 메시지에 붙일 클라이언트 식별자(0.6.1). None 이면 0.6.0
            과 바이트 동일한 줄이 나온다 - 하네스 07 이 그 바이트를 잰다.
    """
    adp = backend or adapter_registry.default()
    if uuid is None:
        # 인자를 아예 넘기지 않는다. 구 어댑터(1인자 서명)와도 호환된다.
        return adp.serialize_user_input(text)
    return adp.serialize_user_input(text, uuid=uuid)


def stream_json_control(request_id, subtype, backend=None, **fields):
    """stdin 에 쓸 제어 요청 한 줄(0.6.1).

    `stream_json_user` 와 같은 이유로 모듈 수준 함수로 둔다 - 하네스가
    프로세스를 띄우지 않고 바이트만 재는 창구가 필요하다.

    Args:
        request_id: 이 요청의 식별자. 응답이 반향한다.
        subtype: 요청 종류. 이름은 어댑터가 쥔다.
        backend: 백엔드 어댑터. None 이면 기본 백엔드다.
        **fields: 요청별 인자. None 인 것은 어댑터가 버린다.
    """
    adp = backend or adapter_registry.default()
    return adp.serialize_control_request(request_id, subtype, **fields)


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

        # ----- 0.6.1 큐·제어 배선 -----
        #
        # 이 블록은 전부 "CLI 가 지금 무엇을 들고 있는가" 를 추적한다.
        # UI 는 없고(다음 단계), 여기서는 창구만 만든다.

        # 세션 개시 이벤트가 광고한 런타임 능력 이름 집합. 게이트가 돌기
        # 전에는 빈 집합이다 - **빈 집합은 "모른다" 가 아니라 "광고된 것이
        # 없다"** 로 쓰므로, 구 CLI 판본에서 이 필드가 없으면 그냥 비어
        # 있고 `has_cli_capability` 가 전부 False 를 돌려준다. 열린 집합이라
        # 모르는 이름은 무시한다.
        self.cli_capabilities = frozenset()

        # 세션 개시 이벤트를 **한 번이라도 봤는가**(0.6.1, V47-A07).
        #
        # `cli_capabilities` 의 빈 집합만으로는 "아직 init 전" 과 "init 이
        # 아무것도 광고하지 않았다(구 CLI)" 를 가를 수 없다. 두 상태의 처분이
        # 반대이므로(전자는 선언 플래그로 시도, 후자는 하향 조정) 깃발을
        # 따로 든다. **init 은 첫 전송 뒤에만 온다**(이 저장소 D06 실측)는
        # 것이 이 설계의 제약이다 - 첫 메시지는 런타임으로 게이트할 수 없다.
        self._caps_seen = False

        # 미결 메시지. command_uuid -> 마지막 state.
        # `queued`/`started` 만 남고 `completed`/`cancelled` 에서 지운다.
        # **대기 건수의 유일한 원천이다.** `result.queued_turn_count` 는
        # 쓰지 않는다 - 네 result 전부 0 이었고 B 가 대기 중인 시점의
        # result 도 0 이었다(실관측). 그 필드로 그리면 영구 0 이다.
        self._pending_queue = {}

        # 미결 uuid 별 진행 표식(0.6.1 백스톱, V47-A03).
        # command_uuid -> (집합에 들어온/상태가 움직인 시점의 턴 종료 누적수,
        # 그 시점의 monotonic 초). 백스톱이 "이 uuid 는 그 뒤로 아무 전이도
        # 없었다" 를 재는 기준이고, 상태가 움직이면 갱신한다(진전이 있었다).
        self._pending_marks = {}

        # 턴 종료 이벤트 누적수. 백스톱의 시계다 - CLI 가 도는 동안에는
        # 전진하지 않으므로 "실행 중인데 한가하다고 믿는" 방향을 못 만든다.
        self._turn_end_count = 0

        # 마지막으로 stdout 줄을 본 시점(monotonic). 침묵 시계의 기준이다.
        # None 이면 아직 한 줄도 못 본 것이고, 그때 침묵 백스톱은 돌지 않는다.
        self._last_line_mono = None

        # 백스톱이 비운 uuid 누적수. 진단과 하네스가 읽는다. 조용히 지우지
        # 않는다는 규칙의 관측 창구다.
        self.orphan_pending_cleared = 0

        # 우리가 보낸 제어 요청. request_id -> subtype. 응답이 오면 지운다.
        self._pending_control = {}

        # 짝이 없는 control_response. **버리지 않는다** - CLI 가 originate
        # 하는 요청(권한 질의 등)의 응답이 섞여 올 수 있고, 이 단계에서는
        # 답하지 않되 관측은 남긴다.
        self.unmatched_control_responses = []

        # 마지막으로 발급한 메시지 uuid. `send()` 의 반환 계약(bool)을
        # 바꾸지 않으려고 둔 창구다.
        self.last_sent_uuid = ""

        # 이 spawn 에서 우리가 발급한 메시지 uuid 전부(발급 순서).
        # 재방출 user 줄이 우리 것인지 가르는 집합이다.
        self.sent_uuids = []

        # control_response 를 받은 호출자 콜백. callable(request_id, subtype,
        # payload, matched_subtype). UI 단계가 붙인다. 시그널을 새로 만들지
        # 않는 이유는 설계 2-6 과 같다(이벤트당 시그널 금지).
        self.on_control_response = None

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
        """CLI 가 지금 일하고 있는가. 설계 2-4 의 입력 차단 판정에 쓴다.

        0.6.1 보정 - 왜 `_busy` 단독으로는 틀리는가
            `_busy` 는 턴 종료 이벤트를 보는 즉시 False 가 된다. 그런데
            CLI 큐에 다음 메시지가 있으면 그 자리에서 **곧바로 다음 턴을
            시작**한다(실관측: completed A -> started B -> 새 세션 개시
            이벤트). 그 구간에서 `_busy` 는 False 인데 CLI 는 실행 중이다.
            그래서 미결 집합이 비어 있지 않으면 바쁜 것으로 본다.

        폴백 - 두 축을 다 본다(0.6.1, V47-A07)
            `lifecycle_live()` 가 False 면 이 함수는 **0.6.0 과 똑같이**
            `_busy` 단독이 된다. 그 함수가 보는 것은 두 축이다 - 어댑터
            선언 플래그(`capabilities.queue_lifecycle`)와 init 이 광고한
            런타임 능력(`msg_lifecycle_v1`). 능력 판정을 미결 집합보다
            먼저 보는 이유는, 능력이 없는 백엔드에서 어떤 경로로든 집합에
            값이 들어가더라도 판정이 바뀌지 않게 못박기 위함이다.

        관측하지 않은 state 로 입력을 막지 않는다
            세는 것은 **실측된 미결 state 두 개**(`queued`·`started`)뿐이다.
            번들 스키마에는 `discarded`·`refused` 도 있지만 관측되지
            않았고, 그 값을 "아직 실행 중" 으로 읽으면 그 state 가 종료
            신호였을 때 입력이 영구히 막힌다. 모르는 state 는 집합에 남겨
            기록하되(`lifecycle_unknown_state`) 바쁨 판정에는 쓰지 않는다 -
            모르는 것으로 단정하지 않는 쪽이다.

        Returns:
            bool
        """
        if self._busy:
            return True
        if not self.lifecycle_live():
            return False
        return bool(self.open_queue_uuids())

    def _runtime_cap_live(self, cap_name):
        """런타임 능력 1종이 지금 쓸 수 있는가(0.6.1, V47-A07).

        하향 조정만 한다 - **상향은 없다.** 세 상태를 가른다.

            어댑터가 이름을 모른다(`cap_name` 이 빈 문자열)
                판정할 축이 없다. True 를 돌려 선언 플래그 단독 판정으로
                되돌린다. 제2 백엔드가 이 이름을 모른다고 기능이 꺼지면
                안 된다.
            아직 init 을 못 봤다(`_caps_seen` False)
                True 다. **init 은 첫 전송 뒤에만 온다**(D06 실측)이므로
                첫 메시지를 런타임으로 게이트하면 아무도 아무것도 못
                보낸다. 그래서 "선언 플래그로 시도하고, init 을 본 뒤
                광고에 없으면 의존을 내린다" 가 유일하게 가능한 모양이다.
            init 을 봤다
                광고 집합의 포함 여부 그대로다. 열린 집합이므로 모르는
                이름은 무시하고, 쓰는 능력만 이름으로 확인한다(번들 지시:
                "check each capability for exactly the behavior you use").

        Args:
            cap_name: 런타임 능력 이름. 빈 문자열이면 판정하지 않는다.

        Returns:
            bool
        """
        if not cap_name:
            return True
        if not self._caps_seen:
            return True
        return cap_name in self.cli_capabilities

    def lifecycle_live(self):
        """큐 수명 축(대기 건수·미결 집합)을 지금 믿어도 되는가(0.6.1).

        선언 플래그와 런타임 광고를 **둘 다** 본다. 선언은 "이 어댑터가
        말할 줄 안다" 이고 런타임은 "지금 붙은 CLI 판본이 실제로 가졌다"
        로 다른 축이다 - 섞으면 구 CLI 에서 조용히 깨진다.

        Returns:
            bool
        """
        if not self._backend.capabilities.queue_lifecycle:
            return False
        return self._runtime_cap_live(
            getattr(self._backend, "runtime_cap_queue_lifecycle", ""))

    def interrupt_live(self):
        """턴 중단 요청을 지금 보내도 되는가(0.6.1).

        Returns:
            bool
        """
        if not self._backend.capabilities.control_interrupt:
            return False
        return self._runtime_cap_live(
            getattr(self._backend, "runtime_cap_interrupt", ""))

    def cancel_queued_live(self):
        """대기 메시지 취소 요청을 지금 보내도 되는가(0.6.1).

        Returns:
            bool
        """
        if not self._backend.capabilities.control_interrupt:
            return False
        return self._runtime_cap_live(
            getattr(self._backend, "runtime_cap_cancel_queued", ""))

    def interrupt_send_now_live(self):
        """대기 메시지 1건을 지금 보내는 요청을 보내도 되는가(0.6.1).

        `interrupt_live()` 와 **다른 축이다.** 선언 플래그는 같은
        `control_interrupt` 를 쓰지만 런타임 광고 이름이 다르다
        (`interrupt_send_now_v1` 대 `interrupt_receipt_v1`) - 영수증은
        광고하면서 sendNow 는 광고하지 않는 판본이 있을 수 있고, 그때
        호출자는 plain interrupt 뒤 전송 폴백으로 내려가야 한다.

        Returns:
            bool
        """
        if not self._backend.capabilities.control_interrupt:
            return False
        return self._runtime_cap_live(
            getattr(self._backend, "runtime_cap_interrupt_send_now", ""))

    def has_cli_capability(self, name):
        """세션 개시 이벤트가 이 런타임 능력을 광고했는가(0.6.1).

        선언 플래그(`capabilities.*`)와 **다른 축**이다. 선언은 "이 어댑터가
        이 기능을 말할 줄 안다" 이고 이쪽은 "지금 붙어 있는 CLI 판본이
        실제로 광고한다" 다. 구 판본은 이 목록 자체가 없을 수 있으므로
        그때는 전부 False 다.

        Args:
            name: 능력 이름.

        Returns:
            bool
        """
        return name in self.cli_capabilities

    def pending_queue_uuids(self):
        """종료 신호를 받지 못한 메시지 uuid 전부.

        실측된 미결 state 두 개 외에 모르는 state 로 남은 것까지 포함한다 -
        관측 기록용이다. 바쁨 판정은 `open_queue_uuids()` 를 쓴다.

        Returns:
            tuple: 수신 순서. 빈 튜플이면 미결 없음.
        """
        return tuple(self._pending_queue)

    def open_queue_uuids(self):
        """실측된 미결 state(`queued`·`started`)에 있는 메시지 uuid 들.

        `is_busy()` 의 원천이다. `pending_queue_uuids()` 의 부분집합이고,
        차집합은 관측 밖의 state 로 남은 것들이다.

        Returns:
            tuple
        """
        return tuple(k for k, v in self._pending_queue.items()
                     if v in protocol.LIFECYCLE_OPEN_STATES)

    def queued_queue_uuids(self):
        """아직 시작되지 않은(대기 중인) 메시지 uuid 들.

        UI 의 "대기 N건" 이 읽을 값이다. `pending_queue_uuids()` 에서
        실행 중인 것을 뺀 부분집합이다.

        Returns:
            tuple
        """
        return tuple(k for k, v in self._pending_queue.items()
                     if v == protocol.LIFECYCLE_QUEUED)

    def pending_control_ids(self):
        """응답을 기다리는 제어 요청 id 들.

        Returns:
            tuple
        """
        return tuple(self._pending_control)

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
        # 새 자식은 큐도 제어 요청도 물려받지 않는다. 비우지 않으면
        # is_busy() 가 죽은 자식의 미결 집합 때문에 영구히 True 가 된다.
        self._pending_queue = {}
        self._pending_control = {}
        self._pending_marks = {}
        self._turn_end_count = 0
        self._last_line_mono = None
        # 새 자식의 init 을 아직 못 봤다. 하향 조정을 물려받지 않는다 -
        # 판본이 바뀐 CLI 로 재spawn 될 수 있다(사용자가 그 사이에 업데이트).
        self.cli_capabilities = frozenset()
        self._caps_seen = False
        self.sent_uuids = []
        self.last_sent_uuid = ""
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

    def send(self, text, allow_queue=False):
        """사용자 메시지를 라이터 큐에 넣는다.

        0.6.1 이 바꾼 것과 바꾸지 않은 것
            바꾼 것 둘이다. (1) 보내는 줄에 uuid 를 붙인다 - 그래야 CLI 가 큐
            수명 이벤트와 result 짝짓기를 돌려준다. (2) `allow_queue` 로 턴 중
            전송을 **선택적으로** 허용한다.

            바꾸지 않은 것은 **기본 동작**이다. 인자를 주지 않으면 0.6.0 과
            똑같이 `_busy` 에서 거부한다 - bool 로 받는 기존 호출자
            (`plugin.py`, 하네스 07·09·12·14)의 동작이 그대로다.

        왜 턴 중 전송을 열 수 있는가 (설계 2-4 의 정정)
            "큐에 2개를 쌓지 않는다" 는 **우리가 큐를 든다**는 가정에서 나온
            제약이었다. 실측은 반대다 - CLI 가 자기 큐를 들고 있고, 턴 중
            stdin 에 쓰면 쌓아 두고 턴이 끝나면 스스로 다음 턴으로 실행한다.
            그 큐가 우리에게 보이는 조건이 `queue_lifecycle` 능력이고,
            **능력이 없으면 허용하지 않는다** - 보이지 않는 큐에 쌓으면 대기
            건수도 취소도 말할 수 없고, 그때 동작은 0.6.0 과 같아야 한다.
            0.6.1 V47-A07 이 여기에 런타임 축을 더했다. 선언 플래그만 보면
            능력을 광고하지 않는 구 CLI 판본에서 조용히 깨지므로, init 을
            본 뒤에는 광고 목록까지 보고 내린다(`lifecycle_live`).

        반환 계약을 바꾸지 않은 이유
            발급한 uuid 를 돌려주려면 반환형을 바꿔야 하고, 그러면 bool 로
            받는 호출자가 전부 깨진다. 그래서 bool 을 유지하고 발급값은
            `last_sent_uuid`·`sent_uuids` 로 노출한다.

        Args:
            text: 보낼 원문.
            allow_queue: 턴이 진행 중이어도 보낼 것인가(0.6.1). 기본 False 는
                0.6.0 동작이다. True 여도 `lifecycle_live()` 가 False 면
                거부한다 - 어댑터 선언 플래그가 없거나, init 광고에 큐 수명
                능력이 없는 CLI 판본일 때다(V47-A07).

        Returns:
            bool: 큐에 들어갔는가.
        """
        if not self.is_running() or self._write_queue is None:
            return False
        # 턴 중 전송을 여는 조건은 두 축이다(0.6.1 V47-A07). 선언 플래그
        # `capabilities.queue_lifecycle` 는 "이 어댑터가 큐를 말할 줄 안다"
        # 이고, `lifecycle_live()` 는 그 선언에 더해 init 광고까지 본다.
        # 광고에 없으면 큐가 우리에게 보이지 않으므로 대기 건수도 취소도
        # 말할 수 없고, 그때 동작은 0.6.0 과 같아야 한다.
        can_queue = (allow_queue
                     and self._backend.capabilities.queue_lifecycle
                     and self.lifecycle_live())
        if self._busy and not can_queue:
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
        # uuid 는 **선언 플래그만** 본다. 런타임으로 게이트하지 않는 이유는
        # init 이 첫 전송 뒤에만 오기 때문이다(D06 실측) - 첫 메시지에 uuid 를
        # 안 붙이면 그 메시지의 lifecycle 이 아예 오지 않고(uuid 없으면 CLI 가
        # 내보내지 않는다, 실관측) 광고를 볼 기회조차 못 만든다. 광고에 없을
        # 때는 붙은 uuid 를 **쓰지 않는 쪽**으로 내린다(lifecycle_live).
        # 능력이 없으면 0.6.0 과 바이트 동일하다.
        msg_uuid = (str(uuid_mod.uuid4())
                    if self._backend.capabilities.queue_lifecycle else None)
        payload = stream_json_user(body, backend=self._backend,
                                   uuid=msg_uuid) + "\n"
        self._busy = True
        if msg_uuid is not None:
            self.last_sent_uuid = msg_uuid
            self.sent_uuids.append(msg_uuid)
        self._write_queue.put(payload)
        if self.logbook is not None:
            self.logbook.diag(
                "sent", "bytes=%d uuid=%s"
                % (len(payload.encode("utf-8")), msg_uuid or "(none)")
            )
        return True

    def send_control(self, subtype, **fields):
        """제어 요청 한 줄을 라이터 큐에 넣는다(0.6.1).

        사용자 메시지와 같은 라이터 스레드를 탄다 - 한 줄 = 한 메시지인
        프로토콜에서 두 스레드가 쓰면 줄이 섞인다(설계 2-4).

        `_busy` 를 보지 않는다. 턴 중단은 턴이 진행 중일 때만 뜻이 있고,
        `_busy` 로 막으면 쓸 수 있는 순간에 못 보낸다.

        Args:
            subtype: 요청 종류. 이름은 어댑터가 쥔다.
            **fields: 요청별 인자. None 인 것은 어댑터가 버린다.

        Returns:
            str: 발급한 request_id. 보내지 못했으면 빈 문자열.
        """
        if not self.is_running() or self._write_queue is None:
            return ""
        if not self._backend.capabilities.control_interrupt:
            # 능력이 없는 백엔드에 제어 줄을 쓰면 그 줄이 사용자 메시지로
            # 해석될 수 있다. 조용히 아무것도 하지 않는다.
            if self.logbook is not None:
                self.logbook.diag("control_unsupported", str(subtype))
            return ""
        request_id = str(uuid_mod.uuid4())
        payload = stream_json_control(request_id, subtype,
                                      backend=self._backend, **fields) + "\n"
        self._pending_control[request_id] = subtype
        self._write_queue.put(payload)
        if self.logbook is not None:
            self.logbook.diag(
                "control_sent", "subtype=%s request_id=%s bytes=%d"
                % (subtype, request_id, len(payload.encode("utf-8"))))
        return request_id

    def interrupt_turn(self, reason=None):
        """진행 중인 턴을 제어 요청 1발로 중단한다(0.6.1).

        `request_cancel()` 과 **다른 경로다. 그쪽을 대체하지 않는다.**
        어느 것을 쓸지는 UI 단계의 결정이라 여기서는 창구만 만든다.

            request_cancel()  트리 종료 + 재개 재spawn. 맥락은 `--resume`
                              으로 살리지만 프로세스가 바뀐다
            interrupt_turn()  같은 프로세스가 유지된다(실관측: 중단된 턴의
                              result 뒤에 새 spawn 없이 다음 메시지가 정상
                              처리됐다)

        대기 메시지가 남는지는 **조건부다**(V47-04 정정)
            우리 녹화 구간에서는 남았다 - 턴이 이미 스트리밍 중인 시점에
            plain interrupt 를 보냈고, 영수증이 대기 uuid 를 `still_queued`
            로 명시했으며 그 메시지는 뒤에 정상 실행됐다 `[실측]`.

            그러나 그것을 **무조건 불변식으로 쓰면 안 된다.** 번들
            `still_queued` describe 에 FIRST-command prewait window 가 있다
            `[스키마]` - 세션 첫 턴이 컨트롤러를 arm 하기 전에 interrupt 가
            들어오면 LATCH 되고, 그 doomed 작업을 들고 arm 하는 첫 턴은
            이미 중단된 상태로 시작한다. **실사용에서 첫 메시지 직후 Stop 이
            바로 그 창이다.** 또 `still_queued` 는 이름보다 넓어서
            "임박한 턴을 위해 이미 dequeue 된 배치" 까지 싣는다 `[스키마]`.

            조건·등급·재도출 경로는 `docs/10.cli_control_protocol_v1.md`
            2 절(특히 "함정 - plain interrupt 도 대기 작업을 죽일 수 있다")
            이 정본이다. 그 창의 거동 자체는 아직 `[미측]`(V47-A02)이므로
            호출자는 "대기가 남는다" 를 전제로 UI 를 확정하지 않는다.

        Args:
            reason: 중단 사유 문자열. None 이면 키를 넣지 않는다 - 측정된
                왕복이 인자 없는 형태였다.

        Returns:
            str: 발급한 request_id. 보내지 못했으면 빈 문자열.
        """
        # 런타임 하향(0.6.1 V47-A07). init 을 봤는데 영수증 능력이 광고에
        # 없으면 보내지 않는다 - 그 판본에서 이 줄이 어떻게 읽히는지 모른다.
        # init 전에는 선언 플래그로 시도한다(첫 턴을 막을 수 없다).
        if not self.interrupt_live():
            if self.logbook is not None:
                self.logbook.diag("control_runtime_absent",
                                  getattr(self._backend,
                                          "runtime_cap_interrupt", ""))
            return ""
        return self.send_control(self._backend.control_interrupt_subtype,
                                 reason=reason)

    def interrupt_turn_send_now(self, message_uuid, reason=None):
        """대기 메시지 1건을 **지금 보내 달라고** 요청한다(0.6.1).

        `interrupt_turn()` 과 같은 subtype(`interrupt`)에 불리언 플래그
        `send_now` 와 대상 `message_uuid` 를 더한 것이다. 요청 꼴은 하네스
        107 r1 이 실제로 보낸 바이트와 **필드 집합이 같다** `[실측]`
        (`{"subtype":"interrupt","send_now":true,"message_uuid":"..."}`;
        녹화 outputs/queue_probe2_20261025_090338/r1/stdin.jsonl 3행).
        `cancel_queued` 는 넣지 않는다 - 함께 주면 Stop 으로 처리된다
        `[스키마]`(docs/10 2 절).

        무엇을 지어내지 않았는가
            `reason` 은 기본값 None 이고 그때 **키 자체가 안 들어간다.**
            107 이 보낸 요청에 `reason` 이 없었고, 있을 때의 거동은
            측정되지 않았다.

        영수증 값의 뜻 (docs/10 2 절, CLI 번들 describe 발췌 r7.txt 9행)
            `stopped`     돌던 턴을 중단했고 그 result 가 뒤따른다 `[실측]`
                          (V50-02, 글만 쓰던 턴)
            `delivering`  턴을 멈추지 않았다 - 돌던 턴이 없거나, 턴이 그
                          메시지를 받아들이는 중이거나, CLI 가 턴이 기다리는
                          작업을 백그라운드로 옮기는 중이거나, 이미 멈추는
                          중이거나, 프로세스가 끝나는 중이다 `[스키마]`
            `nothing_waiting`  보낼 대기 메시지가 없었다 `[스키마]`

            **어느 분기를 타는지는 CLI 가 정한다.** 우리는 요청만 하고
            영수증 값으로 안다 - 분기 조건을 우리가 판정하지 않는다.

        Args:
            message_uuid: 지금 보낼 대기 메시지의 uuid(우리가 발급한 값).
            reason: 중단 사유 문자열. None 이면 키를 넣지 않는다.

        Returns:
            str: 발급한 request_id. 보내지 못했으면 빈 문자열.
        """
        if not message_uuid:
            return ""
        # 런타임 하향. 광고에 sendNow 이름이 없으면 보내지 않는다 - 그 판본이
        # 모르는 플래그를 어떻게 읽는지 측정하지 않았다. 호출자는 이 빈
        # 문자열을 보고 plain interrupt 폴백으로 내려간다.
        if not self.interrupt_send_now_live():
            if self.logbook is not None:
                self.logbook.diag(
                    "control_runtime_absent",
                    getattr(self._backend, "runtime_cap_interrupt_send_now",
                            ""))
            return ""
        return self.send_control(self._backend.control_interrupt_subtype,
                                 send_now=True, message_uuid=message_uuid,
                                 reason=reason)

    def cancel_queued_message(self, message_uuid):
        """대기 중인 메시지 1건을 취소한다(0.6.1).

        `interrupt_turn()` 과 **다른 요청이다.** 그쪽은 도는 턴을 멈추는
        요청이고(대기 메시지가 남는지는 창에 따라 갈린다 - 그쪽 docstring
        과 `docs/10.cli_control_protocol_v1.md` 2 절), 이쪽은 아직 시작하지
        않은 메시지 1건만 지운다(영수증이 `cancelled`).

        번들 describe 는 "already dequeued for execution" 이면 **no-op** 이라
        적는다 `[스키마]`. 즉 응답 `cancelled` 가 False 로 오는 것은 실패가
        아니라 "그 메시지는 이미 큐에 없었다" 일 수 있다.

        한 발에 메시지 하나다. 여럿을 한 요청으로 묶는 형태는 측정되지
        않았으므로 지어내지 않는다 - 호출자가 uuid 마다 부른다.

        Args:
            message_uuid: 취소할 메시지의 uuid(우리가 발급한 값).

        Returns:
            str: 발급한 request_id. 보내지 못했으면 빈 문자열.
        """
        if not message_uuid:
            return ""
        # 런타임 하향(0.6.1 V47-A07). 매핑 근거와 `[미측]` 표기는 어댑터의
        # `CLAUDE_CAP_CANCEL_QUEUED` 주석에 있다.
        if not self.cancel_queued_live():
            if self.logbook is not None:
                self.logbook.diag("control_runtime_absent",
                                  getattr(self._backend,
                                          "runtime_cap_cancel_queued", ""))
            return ""
        return self.send_control(self._backend.control_cancel_queued_subtype,
                                 message_uuid=message_uuid)

    @property
    def interrupt_subtype(self):
        """턴 중단 요청의 subtype 이름. 없으면 "".

        호출자가 `_backend` 를 들여다보지 않게 열어 둔 창구다(docs/7 2-10
        경계 6: 백엔드 리터럴은 어댑터가 쥔다). 상태머신에 우리 요청을
        등록할 때 이 이름이 필요하다.
        """
        return getattr(self._backend, "control_interrupt_subtype", "")

    @property
    def cancel_queued_subtype(self):
        """대기 메시지 취소 요청의 subtype 이름. 없으면 ""."""
        return getattr(self._backend, "control_cancel_queued_subtype", "")

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
            # 침묵 시계의 기준. stdout 줄만 센다 - stderr 는 턴 진행의
            # 신호가 아니다(경고가 혼자 흐를 수 있다).
            self._last_line_mono = time.monotonic()
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

        # 고아 미결 uuid 백스톱(0.6.1 V47-A03). 매 틱 조건만 보고, 모순
        # 상태가 유계를 넘겼을 때만 비운다. 조건은 함수 docstring 에 있다.
        # 종료·사망 경로 **뒤에** 둔다 - 그 두 경로는 집합을 통째로 비우므로
        # 백스톱이 끼어들 일이 없고, 끼어들면 사유가 사망인지 고아인지 로그
        # 에서 갈리지 않는다.
        self._sweep_orphan_pending()

    def _inspect(self, line):
        """프로세스 계층이 꼭 봐야 하는 네 이벤트만 본다.

        해석은 S3 상태머신이 한다. 여기서 보는 것은 (1) 기동 자기점검을 돌려야
        하는 세션 개시 이벤트, (2) 턴 중 입력 차단을 풀어야 하는 턴 종료
        이벤트 둘뿐이다.

        어느 이벤트가 그 둘인지는 **백엔드마다 다르다**(docs/7 2-10 경계 3).
        Claude 는 `system/init` 과 최상위 `result` 이고, 그 판별을 어댑터에
        물어 본다 - 여기서 문자열로 비교하면 제2 백엔드가 이 함수를 고치게
        된다.

        0.6.1 이 더한 둘은 공통 모델 쪽이다(`protocol.KIND_*`).
            * 큐 수명 이벤트  미결 집합을 갱신한다. `is_busy()` 의 원천이다
            * 제어 응답       우리 요청과 request_id 로 짝짓는다
        """
        ev = line.event
        if not isinstance(ev, dict):
            return
        if self._backend.is_session_init_event(ev):
            # 원본을 먼저 보관한다. gate_result 슬롯이 이것을 읽어 탐지를 돌린다.
            self.last_init_event = ev
            self._capture_cli_capabilities(ev)
            self._run_gate(ev)
        elif self._backend.is_turn_end_event(ev):
            self._busy = False
            self._turn_end_count += 1
            # 주 처방(V47-A03). 턴이 닫힐 때 그 턴이 실어 온 입력 uuid 를
            # 미결 집합에서 정산한다. lifecycle 종결이 오지 않아도 지운다.
            self._settle_by_result(ev)
        elif ev.get("type") == protocol.KIND_LIFECYCLE:
            self._on_lifecycle(ev)
        elif ev.get("type") == protocol.KIND_CONTROL_RESPONSE:
            self._on_control_response(ev)

    def _capture_cli_capabilities(self, init_event):
        """세션 개시 이벤트가 광고한 런타임 능력 목록을 보관한다(0.6.1).

        필드가 없으면 **빈 집합**이다. 구 CLI 판본에는 이 필드가 없을 수
        있고, 그때 "없다" 를 결함으로 읽으면 안 된다. 열린 집합이라 모르는
        이름은 그대로 담아 두고 판정에는 쓰지 않는다.
        """
        names = init_event.get("capabilities")
        # 깃발을 먼저 세운다. 필드가 없는 init 도 "init 을 봤다" 이고, 그
        # 상태가 하향 조정의 조건이다(V47-A07).
        self._caps_seen = True
        if not isinstance(names, (list, tuple)):
            self.cli_capabilities = frozenset()
        else:
            self.cli_capabilities = frozenset(
                str(n) for n in names if isinstance(n, str))
        if self.logbook is not None:
            self.logbook.diag("cli_capabilities",
                              "n=%d %s" % (len(self.cli_capabilities),
                                           ",".join(sorted(self.cli_capabilities))))
            # 하향된 축을 이름으로 적는다. 조용히 끄면 "왜 대기 표시가 없나"
            # 를 나중에 되짚을 수 없다.
            # 0.6.1: sendNow 축이 넷째로 들어왔다. 축 이름이 곧
            # `runtime_cap_<축>` 속성 이름이어야 아래 getattr 가 원하는 능력
            # 이름을 찾는다(그래서 축 이름이 `interrupt_send_now` 다).
            for axis, live in (("queue_lifecycle", self.lifecycle_live()),
                               ("interrupt", self.interrupt_live()),
                               ("cancel_queued", self.cancel_queued_live()),
                               ("interrupt_send_now",
                                self.interrupt_send_now_live())):
                if not live:
                    self.logbook.diag(
                        "runtime_capability_downgraded",
                        "axis=%s wanted=%s" % (
                            axis,
                            getattr(self._backend,
                                    "runtime_cap_" + axis, "") or "(none)"))

    def _settle_by_result(self, result_event):
        """턴이 닫힐 때 그 턴이 실어 온 입력 uuid 를 정산한다(0.6.1 V47-A03).

        왜 이것이 주 처방인가
            미결 집합은 lifecycle 의 `completed`/`cancelled` 로만 비는데,
            번들에 `detachedToolCall: true` 와 "the turn can take them in as
            any turn does" 가 있어 **큐에 쌓인 메시지가 한 턴에 접힐
            (coalesce) 수 있다** `[스키마]`. 접힌 uuid 에 종결 이벤트가
            오지 않으면 그 uuid 는 영구히 남고 `is_busy()` 가 영구 True 가
            된다 - 입력이 잠긴다.

            `result.user_message_uuids` 는 "이 result 가 어느 입력
            메시지의 것인가" 를 짚는 필드이고 우리 녹화 네 회차 모두
            **1:1 이었다** `[실측]`(docs/10 6 절). 접힘이 일어나면 흡수한
            턴의 그 필드에 여러 uuid 가 실릴 자리이므로, 이 정산이 접힘을
            구조적으로 흡수한다.

        반대 방향 위험을 만들지 않는 이유
            지우는 것은 **result 가 이름을 부른 uuid 뿐이다.** result 는
            "그 입력에 대한 턴이 끝났다" 는 CLI 자신의 선언이므로, 그
            uuid 가 아직 실행 중일 수 없다. 이름이 없는 uuid 는 손대지
            않는다 - 그쪽은 백스톱(`_sweep_orphan_pending`)의 일이다.

        Args:
            result_event: 턴 종료 이벤트 dict.
        """
        got = result_event.get("user_message_uuids")
        if not isinstance(got, (list, tuple)):
            one = result_event.get("user_message_uuid")
            got = [one] if isinstance(one, str) and one else []
        settled = []
        for msg_uuid in got:
            if not isinstance(msg_uuid, str) or not msg_uuid:
                continue
            if self._pending_queue.pop(msg_uuid, None) is not None:
                self._pending_marks.pop(msg_uuid, None)
                settled.append(msg_uuid)
        if settled and self.logbook is not None:
            self.logbook.diag(
                "settled_by_result",
                "n=%d uuids=%s pending=%d"
                % (len(settled), ",".join(u[:12] for u in settled),
                   len(self._pending_queue)))

    def _sweep_orphan_pending(self):
        """진행 턴이 없는데 남은 미결 uuid 를 유계 안에서 비운다(백스톱).

        `_settle_by_result` 와 **다른 조건이다.** 그쪽은 result 가 이름을
        부른 uuid 를 지우고(끝났다는 CLI 의 선언), 이쪽은 **아무도 이름을
        부르지 않은 채 모순 상태로 남은** uuid 를 지운다. 그래서 두 함수가
        같은 uuid 를 두고 다투지 않는다.

        모순의 정의와 두 시계
            전제는 `_busy` 가 False 라는 것이다 - 우리가 보낸 턴의 result 를
            아직 못 받았다면(`_busy` True) 아무것도 건드리지 않는다.

                턴 시계   그 uuid 가 집합에 들어오거나 상태가 움직인 뒤로
                          턴 종료가 `ORPHAN_PENDING_TURNS_MAX` 번 지났다.
                          result 는 CLI 가 도는 동안 오지 않으므로 이 시계는
                          **실행 중에 전진하지 않는다.**
                침묵 시계 `started` 가 **하나도 없고** stdout 이
                          `ORPHAN_PENDING_SILENCE_S` 동안 완전히 조용했다.
                          `started` 가 있으면 CLI 가 "그것을 턴으로
                          드레인했다" 고 말한 것이므로 침묵만으로 지우지
                          않는다 - 긴 도구 실행이 조용할 수 있다.

        조용히 지우지 않는다
            비운 uuid 와 발화한 시계를 진단 로그에 남기고
            `orphan_pending_cleared` 를 올린다.

        Returns:
            int: 비운 uuid 수.
        """
        if self._busy or not self._pending_queue:
            return 0
        if not self.lifecycle_live():
            # 축이 꺼져 있으면 집합은 판정에 쓰이지 않는다. 손대지 않는다.
            return 0
        now = time.monotonic()
        any_started = any(v == protocol.LIFECYCLE_STARTED
                          for v in self._pending_queue.values())
        silent = (self._last_line_mono is not None
                  and not any_started
                  and (now - self._last_line_mono) >= ORPHAN_PENDING_SILENCE_S)
        cleared = []
        for msg_uuid in list(self._pending_queue):
            turn_mark, _mono = self._pending_marks.get(
                msg_uuid, (self._turn_end_count, now))
            turns_since = self._turn_end_count - turn_mark
            if turns_since >= ORPHAN_PENDING_TURNS_MAX:
                cleared.append((msg_uuid, "turns=%d" % turns_since))
            elif silent:
                cleared.append((msg_uuid, "silence_s=%.0f"
                                % (now - self._last_line_mono)))
        for msg_uuid, _why in cleared:
            self._pending_queue.pop(msg_uuid, None)
            self._pending_marks.pop(msg_uuid, None)
        if cleared:
            self.orphan_pending_cleared += len(cleared)
            if self.logbook is not None:
                self.logbook.diag(
                    "orphan_pending_cleared",
                    "n=%d %s pending=%d total=%d"
                    % (len(cleared),
                       " ".join("%s(%s)" % (u[:12], why) for u, why in cleared),
                       len(self._pending_queue), self.orphan_pending_cleared))
        return len(cleared)

    def _on_lifecycle(self, ev):
        """큐 수명 이벤트 1건으로 미결 집합을 갱신한다(0.6.1).

        제거 키는 `command_uuid` 다. 줄 자신의 `uuid` 로 지우면 들어온 적
        없는 키를 지우는 것이라 집합이 영원히 비지 않는다.

        `completed`/`cancelled` 만 제거다. 번들 스키마에 적힌
        `discarded`·`refused` 는 관측되지 않았으므로 **제거 조건에 넣지
        않고** 그대로 들고 간다 - 관측 없이 제거 조건을 넓히면 아직 살아
        있는 메시지를 끝난 것으로 지울 수 있다. 모르는 state 는 집합에
        남고 진단에 기록된다.
        """
        info = protocol.lifecycle_info(ev)
        if not info.command_uuid:
            return
        if info.state in (protocol.LIFECYCLE_COMPLETED,
                          protocol.LIFECYCLE_CANCELLED):
            self._pending_queue.pop(info.command_uuid, None)
            self._pending_marks.pop(info.command_uuid, None)
        else:
            # 상태가 움직였으면 진전이 있었다. 백스톱 표식을 지금으로
            # 갱신해 두면 전이가 계속되는 메시지는 백스톱에 걸리지 않는다.
            if self._pending_queue.get(info.command_uuid) != info.state:
                self._pending_marks[info.command_uuid] = (
                    self._turn_end_count, time.monotonic())
            self._pending_queue[info.command_uuid] = info.state
            if info.state not in protocol.KNOWN_LIFECYCLE_STATES:
                # 관측 밖의 state. 집합에 남겨 두고 사실만 적는다.
                if self.logbook is not None:
                    self.logbook.diag("lifecycle_unknown_state", str(info.state))
        if self.logbook is not None:
            self.logbook.diag(
                "lifecycle",
                "state=%s cmd=%s pending=%d queued=%d"
                % (info.state, info.command_uuid[:12], len(self._pending_queue),
                   len(self.queued_queue_uuids())))

    def _on_control_response(self, ev):
        """제어 응답을 우리 요청과 짝짓는다(0.6.1).

        짝짓기 키는 `request_id` 하나다(실관측: 응답이 보낸 값을 반향한다).
        짝이 없는 응답은 **버리지 않는다** - CLI 가 originate 하는 요청의
        응답이 섞여 올 수 있고, 이 단계에서는 답하지 않되 관측은 남긴다.
        """
        info = protocol.control_response_info(ev)
        matched = self._pending_control.pop(info.request_id, "")
        if not matched:
            self.unmatched_control_responses.append(ev)
        if self.logbook is not None:
            self.logbook.diag(
                "control_response",
                "request_id=%s subtype=%s matched=%s payload_keys=%s"
                % (info.request_id or "(none)", info.subtype or "(none)",
                   matched or "(unmatched)", ",".join(sorted(info.payload))))
        if self.on_control_response is not None:
            try:
                self.on_control_response(info.request_id, info.subtype,
                                         info.payload, matched)
            except Exception as exc:  # noqa: BLE001 - 콜백 실패가 드레인을 멈추지 않는다
                if self.logbook is not None:
                    self.logbook.diag("control_callback_err", "%r" % (exc,))

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
        # 죽은 자식의 큐는 사라졌다. 비우지 않으면 is_busy() 가 재spawn 전까지
        # 영구 True 가 되어 입력이 막힌다.
        self._pending_queue = {}
        self._pending_control = {}
        self._pending_marks = {}
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
