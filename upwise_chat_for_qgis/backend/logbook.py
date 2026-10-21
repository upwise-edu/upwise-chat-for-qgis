"""세션 녹화와 진단 로그 (설계 7-4).

두 파일을 쓴다.

    session_<uuid>.jsonl  백엔드 stdout 의 전 줄 원문. 파싱 전에 append 한다.
    diag_<시각>.txt       spawn argv, 제거한 env, 게이트 판정, 종료코드, stderr 꼬리.

jsonl 을 왜 전 줄 원문으로 남기는가
    (1) 감사 경로다. 화면은 cat -n 접두를 떼고 그리지만(설계 4-3) 원문은 남아야 한다.
    (2) S3 이후의 개발 입력이다(설계 10 보조 원칙). 녹화본을 재생하면 UI 와
        상태머신을 과금 없이 개발하고 회귀 테스트로 쓸 수 있다.

쓰기 경로가 둘(리더 스레드의 stdout 줄, 다른 스레드의 진단 줄)이므로 락을
둔다. 파일은 둘로 나뉘어 있지만 같은 객체의 상태를 만지므로 하나로 묶는다.

cp949 주의: 모든 파일 I/O 는 encoding="utf-8" 을 명시한다(설계 8).

0.2.1 이 더한 것: 레다크션 적용 지점 2개 (설계 docs/2 5-4)
    `write_stdout_line` 이 **jsonl 기록 전**, `diag` 가 **진단 번들 전**에
    키 값을 지운다. 세 번째 지점(전사 위젯)은 ui/chat_view 가 맡는다.
    치환은 되돌릴 수 없으므로(설계 5-4) 감사 경로는 "레다크션 n건" 카운터
    한 줄뿐이고, 그 줄에도 값은 들어가지 않는다.

설계 정본: docs/1.mvp_design_v1.md 2-6, 7-4 / docs/2 5-4
"""

import datetime as dt
import threading
from pathlib import Path

# 로그 폴더 이름. 설계 7-4 의 <QGIS 프로필>/upwise_chat/logs/ 를 따른다.
LOG_SUBDIR = ("upwise_chat", "logs")

# 진단 로그에 남기는 stderr 꼬리 줄 수(설계 2-5).
STDERR_TAIL_LINES = 20


def qgis_profile_root():
    """QGIS 사용자 프로필 폴더를 돌려준다.

    QGIS 밖(검증 하네스 등)에서 import 될 수 있으므로 qgis.core 를 함수 안에서
    import 하고, 실패하면 홈 폴더로 떨어뜨린다. 경로를 못 구해서 백엔드가
    안 뜨는 일은 없어야 한다.
    """
    try:
        from qgis.core import QgsApplication

        path = QgsApplication.qgisSettingsDirPath()
        if path:
            return Path(path)
    except Exception:  # noqa: BLE001 - 경로 해석 실패가 기동을 막지 않는다
        pass
    return Path.home()


def default_log_dir():
    """<QGIS 프로필>/upwise_chat/logs (설계 7-4)."""
    return qgis_profile_root().joinpath(*LOG_SUBDIR)


class SessionLogbook:
    """한 백엔드 세션의 녹화본과 진단 로그.

    session_id 가 spawn 마다 바뀌므로 jsonl 도 spawn 마다 새로 열린다.
    진단 로그는 하네스/플러그인 한 번 실행에 하나이므로 생성 시각으로 이름을 짓는다.
    """

    def __init__(self, log_dir=None, session_id="unknown", diag_stamp=None,
                 redactor=None):
        """로그 파일 둘을 열고 즉시 flush 모드로 둔다.

        Args:
            log_dir: 로그 폴더. None 이면 default_log_dir().
            session_id: `--session-id` 로 준 값. 파일명에 들어간다.
            diag_stamp: 진단 파일명 시각 문자열. None 이면 지금 시각.
            redactor: callable(str) -> str (0.2.1). 보통
                backend.redact.Redactor. None 이면 치환하지 않는다 -
                키를 저장하지 않은 사용자에게 오버헤드를 주지 않는다.
        """
        self.log_dir = Path(log_dir) if log_dir else default_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = diag_stamp or dt.datetime.now().strftime("%y%m%d_%H%M%S")
        self.session_id = session_id
        self.jsonl_path = self.log_dir / ("session_%s.jsonl" % session_id)
        self.diag_path = self.log_dir / ("diag_%s.txt" % stamp)
        self._lock = threading.Lock()
        self._lines = 0
        self._closed = False
        self._redactor = redactor
        # 마지막으로 진단에 적은 레다크션 누적 건수. 값이 늘었을 때만 한 줄을
        # 더한다 - 줄마다 적으면 진단 로그가 카운터로 덮인다.
        self._redact_noted = 0
        # 카운터 줄을 쓰는 동안 다시 카운터 줄을 쓰지 않게 하는 가드.
        self._noting = False
        # append 모드다. 같은 session_id 로 재개(--resume)하면 한 파일에 이어 쌓인다.
        self._jsonl = open(self.jsonl_path, "a", encoding="utf-8", newline="")
        self._diag = open(self.diag_path, "a", encoding="utf-8", newline="")

    # ------------------------------------------------------------------
    # 녹화
    # ------------------------------------------------------------------

    def set_redactor(self, redactor):
        """레다크터를 붙이거나 바꾼다(0.2.1).

        키 저장/삭제가 세션 중에 일어날 수 있고, 그때 지울 값 목록이 바뀐다.
        목록은 레다크터 객체가 들고 있으므로 보통은 이 메서드를 다시 부를
        필요가 없다 - 교체 경로를 남겨 두는 것이다.
        """
        self._redactor = redactor

    def _redact(self, text):
        """레다크터가 있으면 치환한다. 없으면 원문이다."""
        if self._redactor is None:
            return text
        try:
            return self._redactor(text)
        except Exception:  # noqa: BLE001 - 치환 실패가 녹화를 멈추게 하지 않는다
            return text

    def write_stdout_line(self, raw):
        """stdout 한 줄을 **레다크션 후** append 한다.

        파싱 성공 여부와 무관하게 쓴다. 비 JSON 줄도 감사 대상이다(설계 4-2).

        0.2.1: 설계 docs/2 5-4 의 적용 지점 1("jsonl 기록 전")이다. 치환은
        값 완전 일치 부분문자열만 바꾸므로 JSON 구조를 깨지 않는다 - 토큰이
        ASCII 이고 따옴표나 역슬래시를 넣지 않는다.
        """
        if self._closed:
            return
        body = self._redact(raw)
        with self._lock:
            self._jsonl.write(body + "\n")
            self._jsonl.flush()
            self._lines += 1
        self._note_redaction()

    @property
    def jsonl_lines(self):
        """녹화한 줄 수."""
        return self._lines

    # ------------------------------------------------------------------
    # 진단
    # ------------------------------------------------------------------

    def diag(self, tag, detail=""):
        """진단 한 줄. 중단되더라도 여기까지는 파일에 남는다.

        0.2.1: 설계 docs/2 5-4 의 적용 지점 3("진단 번들 전")이다. 진단 줄에
        키가 실릴 경로는 `ui_*` 전달분(상태머신 요약)과 argv 뿐이고 둘 다
        지금은 키를 담지 않지만, 적용 지점을 빼 두면 다음 회차에 담기는 줄이
        생겨도 아무 신호가 없다.
        """
        if self._closed:
            return
        line = "%s\t%s\t%s" % (
            dt.datetime.now().isoformat(timespec="milliseconds"),
            tag,
            self._redact(str(detail)).replace("\r", " ").replace("\n", " | "),
        )
        with self._lock:
            self._diag.write(line + "\n")
            self._diag.flush()
        self._note_redaction()

    def _note_redaction(self):
        """레다크션 누적 건수가 늘었으면 진단에 한 줄 남긴다(설계 5-4).

        치환은 비가역이므로 원본을 보존하지 않는다. 남는 감사 흔적은 이
        **건수** 하나이고, 값은 들어가지 않는다. 락 밖에서 부른다 - diag 가
        같은 락을 잡으므로 안에서 부르면 교착이다.
        """
        if self._redactor is None or self._closed or self._noting:
            return
        try:
            total = int(self._redactor.count)
        except Exception:  # noqa: BLE001 - 콜러블만 넘긴 경우(카운터 없음)
            return
        if total == self._redact_noted:
            return
        self._noting = True
        try:
            self._redact_noted = total
            self.diag("redaction", "레다크션 %d건" % total)
        finally:
            self._noting = False

    def diag_stderr_tail(self, lines):
        """stderr 꼬리를 진단에 남긴다. 종료 원인 추적용이다."""
        tail = list(lines)[-STDERR_TAIL_LINES:]
        self.diag("stderr_tail", "n=%d" % len(tail))
        for i, line in enumerate(tail):
            self.diag("stderr_tail_%02d" % i, line)

    def close(self):
        """두 파일을 닫는다. 두 번 불려도 안전하다."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._jsonl.close()
            finally:
                self._diag.close()
