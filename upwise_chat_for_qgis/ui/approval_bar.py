"""거부 재시도 바, 제외 안내 바, stale 바, 내보내기 안내 바 (설계 3-5 항목 3).

0.2.3 이 더한 것: ExportNoticeBar. 전사 내보내기 결과(경로 또는 실패 사유)를
알리는 비차단 바다. QFileDialog 가 금지 목록이라 저장 경로를 묻지 않으므로,
"어디에 썼는가" 를 알릴 자리가 필요하다.

승인 UI 3층 중 (3) 거부 재시도 바가 여기 있고, 그것과 신호가 다른 **제외
안내 바**가 함께 있다. (1) 포스처 토글과 (2) 턴 승인 바는 S5 범위 목록
(설계 10-2 S5-1~S5-6)에 없으므로 만들지 않는다.

**거부와 제외는 다른 신호다**(장부 V28-21, 설계 3-5 표).

    거부  system/permission_denied + tool_result is_error  -> [허용하고 다시 요청]
    제외  "No such tool available" (권한 이벤트 없음)        -> 안내만

제외를 거부로 표시하면 사용자가 "허용" 을 눌러도 아무 일이 없다.
`--disallowedTools` 가 `--allowedTools` 를 이기므로(A14 축3) allowlist 를
넓히는 상승으로는 풀리지 않는다. 그래서 제외 바에는 재시도 버튼이 없다.

이 바가 지키는 것

    * 모달이 아니다. 전사 영역 하단에 끼우는 위젯이고, 떠 있는 동안에도
      스크롤, 타이핑, QGIS 조작이 된다. 모달 팝업은 자동화를 정지시킨다(설계 5).
    * **턴당 하나다.** 한 턴에 거부가 여러 번 난다(A07 실측: B2 는 Bash 거부
      뒤 Write 를 또 시도해 다시 거부됐다, ln120~122 / ln149~151). 거부마다
      바를 쌓지 않고 시도 목록을 한 바에 모은다.
    * **행동 버튼만 맡는다.** 모델이 거부를 산문으로 또 설명하기 때문이다
      (A07 ln91). 그래서 사유 전문을 바에 반복하지 않는다. 도구 이름과 인자
      전문, 거부 사유 원문은 그 턴의 도구 카드가 빨간 테두리로 이미 보여 준다
      (설계 4-2 tool_result 행). 바는 시도 목록 한 줄과 버튼 둘이다.

"허용하고 다시 요청" 은 **포스처를 올려 같은 요청을 1회 재전송**하는 것이고
(개별 도구 호출을 플러그인이 주입할 수는 없다), 그 상승 경로는 S5 가 붙인다.
배선이 없으면 버튼은 비활성이다. 없는 기능을 누를 수 있게 두지 않는다.

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog, 중첩 이벤트 루프.

설계 정본: docs/1.mvp_design_v1.md 3-5
"""

from qgis.PyQt.QtCore import QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme as theme_mod

# 바 안쪽 여백과 간격(px). 0.2.2: 여섯 바가 같은 값을 쓴다 - 바마다 여백이
# 다르면 쌓였을 때 줄이 안 맞는다.
BAR_MARGIN = (10, 7, 10, 7)
BAR_SPACING = 6

# 본문 줄과 버튼 줄 사이 간격(px).
BAR_ROW_SPACING = 6

# 바 버튼 최소 폭(px). 글자 수가 다른 버튼("확인" / "허용하고 다시 요청")이
# 섞여 있어 그대로 두면 크기가 제각각이다. 글꼴 크기는 고정하지 않으므로
# 폭만 하한으로 맞춘다(설계 7-3).
BAR_BUTTON_MIN_W = 76

# 바에 이름을 늘어놓는 시도 수 상한. 넘으면 "외 N건" 으로 줄인다. 한 턴에
# 거부가 여러 번 나는 것이 실측이므로 줄 길이가 독 폭을 넘지 않게 둔다.
NAME_LIST_MAX = 4

RETRY_TEXT = "허용하고 다시 요청"
KEEP_TEXT = "거부 유지"

# 상승 배선이 없을 때 재시도 버튼에 붙이는 설명. 포스처 상승은 재spawn 이라
# 플래그 조립 단계가 붙어야 동작한다.
RETRY_DISABLED_TIP = "지금 포스처에서는 상승할 수 없습니다"

# 제외 바 문구. "권한" 이나 "허용" 이라는 말을 쓰지 않는다 - 그 말을 쓰면
# 사용자가 상승으로 풀 수 있다고 읽는다(설계 3-5).
EXCLUSION_TEXT = ("이 포스처에 없는 도구를 호출해 %d건이 실행되지 않았습니다: %s. "
                  "임의 코드와 SQL 실행 도구는 포스처 전환으로도 열리지 않습니다.")
EXCLUSION_CLOSE_TEXT = "확인"

# stale 바 문구. 자동으로 바꾸지 않는 이유를 문구에 담는다 - 재시작하면 모델이
# 보던 레이어 지식이 사라지므로 시점을 사용자가 고른다(설계 8).
STALE_TEXT = ("프로젝트가 %s 으로 바뀌었습니다. 작업 폴더가 달라졌습니다(%s). "
              "지금 백엔드는 이전 폴더를 보고 있습니다.")
STALE_RESTART_TEXT = "새 폴더로 재시작"
STALE_KEEP_TEXT = "그대로 쓰기"

# 내보내기 안내 바 문구(0.2.3). 저장 위치를 사용자에게 묻지 않으므로(파일
# 대화상자 금지, 설계 3-5) 바 문구가 경로를 알려 주는 유일한 자리다.
#
# U15(0.3.x UI 패스 2차): 사용자에게 보이는 문구에서 "전사" 를 뺐다. 전사는
# 설계 문서의 내부 용어이고, 사용자가 저장하는 것은 자기 눈에 "대화" 다.
# **상수 이름(EXPORT_SAVED_TEXT)과 주석·로그·jsonl 키는 그대로 둔다** -
# 내부 어휘를 바꾸면 설계 문서와 하네스 장부가 서로 다른 말을 쓰게 된다.
EXPORT_SAVED_TEXT = "대화를 저장했습니다: %s"
EXPORT_FAILED_TEXT = "대화를 저장하지 못했습니다: %s"
EXPORT_OPEN_TEXT = "폴더 열기"
EXPORT_CLOSE_TEXT = "확인"
EXPORT_OPEN_DISABLED_TIP = "저장에 실패해 열 폴더가 없습니다"

# 복사 실패 문구(0.2.4). 같은 바에 적지만 문구는 따로 둔다 - 막힌 것이
# 저장이 아니라 복사일 때 "대화를 저장하지 못했습니다" 는 틀린 말이다.
COPY_FAILED_TEXT = "복사하지 못했습니다: %s"
COPY_OPEN_DISABLED_TIP = "복사하지 못해 열 폴더가 없습니다"

# 저장 성공 안내가 저절로 내려가는 시간(ms), 0.4.0 사용자 요청.
#
# 근거: dock.CLEAR_CONFIRM_MS(4000)의 2배다. 그쪽은 "한 번 더" 넉 자를 읽고
# 누를 시간이고, 이 바는 **경로 전문**을 읽은 뒤 [폴더 열기] 로 손을 옮길
# 시간이 더 든다. 그래서 두 배로 잡았다.
#
# **성공에만 건다.** 실패(show_failed, show_copy_failed)는 자동으로 내리지
# 않는다 - 에러가 못 본 사이 사라지면 사용자는 저장된 줄 알고 파일을 찾는다
# (ExportNoticeBar docstring 의 같은 근거).
EXPORT_AUTO_HIDE_MS = 8000

# 우상단 닫기 버튼(0.4.2, 사용자 요청 2026-10-17: "대화 내보내기 알림은 자동
# 종료도 있지만 x 자 종료 버튼도 구현해주세요. 우상단에").
#
# 자동 숨김과 **병존**한다. 자동 숨김은 성공 안내에만 걸리고(위 주석), 실패
# 안내에는 아래 줄의 [확인] 이 이미 있었다 - 이 X 는 그 [확인] 과 같은 일을
# 하되 손이 먼저 가는 자리에 둔다(읽기를 끝낸 사용자의 시선은 글 끝이 아니라
# 바 모서리로 간다).
#
# 아이콘 전용인 이유는 독 헤더의 승격 버튼 넷과 같다 - 글자 버튼은 바의 최소
# 폭을 글자 폭만큼 밀어 올린다. 크기는 표준 닫기 아이콘의 원본 치수다.
EXPORT_X_ICON_PX = 12
EXPORT_X_TIP = "이 안내를 닫습니다."


def build_bar(bar, buttons, danger=False):
    """바 하나를 세운다: 본문 한 줄 + 오른쪽 정렬 버튼 줄(0.2.2).

    왜 세로 두 줄인가 (실측으로 고친 것이다)
        전에는 본문과 버튼이 한 줄이었다. QPushButton 은 sizeHint 아래로 줄지
        않으므로, 폭 435 px 독에서 "허용하고 다시 요청"(약 190 px)과
        "거부 유지"(약 80 px)가 자리를 먼저 가져가고 본문에 약 120 px 만
        남았다. 본문이 한 줄에 한 낱말씩 여섯 줄로 쪼개졌다(0.2.2 전 렌더에서
        실제로 그렇게 나왔다). 본문을 자기 줄에 두면 폭을 다 쓴다.

    Args:
        bar: QFrame 바.
        buttons: (문구, objectName) 튜플 목록. objectName 은 "" 이면 안 건다.
        danger: 위험(거부) 바인가. 본문 글자색 역할이 갈린다.

    Returns:
        tuple: (본문 QLabel, 만든 버튼 리스트)
    """
    outer = QVBoxLayout(bar)
    outer.setContentsMargins(*BAR_MARGIN)
    outer.setSpacing(BAR_ROW_SPACING)

    label = bar_label(bar, danger)
    outer.addWidget(label)

    row = QWidget(bar)
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(BAR_SPACING)
    row_layout.addStretch(1)
    made = []
    for text, object_name in buttons:
        button = bar_button(row, text, object_name)
        row_layout.addWidget(button)
        made.append(button)
    outer.addWidget(row)
    return (label, made)


def bar_label(bar, danger=False):
    """바 본문 라벨 하나. 바 면 색에 맞는 글자색 역할을 붙인다.

    Args:
        bar: 부모 바.
        danger: 위험 바면 True(빨강 면 위 글자색), 아니면 주의 면 글자색.

    Returns:
        QLabel: 만든 라벨.
    """
    label = QLabel("", bar)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    theme_mod.set_role(
        label,
        theme_mod.ROLE_DANGER_TEXT if danger else theme_mod.ROLE_WARN_TEXT)
    return label


def bar_button(bar, text, object_name=""):
    """바 버튼 하나. 최소 폭을 맞춰 크기를 고르게 한다.

    Args:
        bar: 부모 바.
        text: 버튼 문구.
        object_name: 주 버튼이면 qss 가 쓰는 이름.

    Returns:
        QPushButton: 만든 버튼.
    """
    button = QPushButton(text, bar)
    if object_name:
        button.setObjectName(object_name)
    button.setMinimumWidth(BAR_BUTTON_MIN_W)
    return button


class DenialRetryBar(QFrame):
    """거부 관측 시 전사 하단에 끼우는 비차단 바.

    시그널 둘만 낸다.

        retry_requested()  포스처를 올려 같은 요청을 다시 보내 달라
        keep_denied()      거부를 유지하고 바를 닫는다
    """

    retry_requested = pyqtSignal()
    keep_denied = pyqtSignal()

    def __init__(self, parent=None):
        """숨은 상태로 만든다. 거부가 관측될 때 show_attempts() 가 띄운다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatDenialBar")
        self.setFrameShape(QFrame.NoFrame)

        # 주 버튼(설계 7-3 "주 버튼(전송, 허용)" 행). 독 qss 가 이 이름으로
        # 브랜드 오렌지를 건다. 승인 바에서 사용자가 고를 행동이 이것 하나다.
        self._label, (self._retry, self._keep) = build_bar(
            self,
            [(RETRY_TEXT, "UpwiseChatApproveButton"), (KEEP_TEXT, "")],
            danger=True)
        self._retry.setEnabled(False)
        self._retry.setToolTip(RETRY_DISABLED_TIP)
        self._retry.clicked.connect(self._on_retry)
        self._keep.clicked.connect(self._on_keep)

        self._turn_no = None
        self.setVisible(False)

    # ------------------------------------------------------------------
    # 표시
    # ------------------------------------------------------------------

    def show_attempts(self, turn_no, attempts):
        """거부 시도 목록을 한 줄로 요약해 띄운다.

        같은 턴에서 다시 불리면 바를 새로 만들지 않고 줄만 갱신한다. 턴당 하나를
        지키는 자리가 여기다.

        Args:
            turn_no: 턴 번호.
            attempts: machine.DenialAttempt 목록.

        Returns:
            bool: 지금 바가 보이는가.
        """
        attempts = list(attempts or ())
        if not attempts:
            self.hide_bar()
            return False
        self._turn_no = turn_no
        self._label.setText(self._summary(attempts))
        self.setVisible(True)
        return True

    def hide_bar(self):
        """바를 내린다."""
        self._turn_no = None
        self.setVisible(False)

    def set_retry_enabled(self, enabled):
        """재시도 버튼을 쓸 수 있게 한다. 상승 배선이 있을 때만 참이다."""
        enabled = bool(enabled)
        self._retry.setEnabled(enabled)
        self._retry.setToolTip("" if enabled else RETRY_DISABLED_TIP)

    def turn_no(self):
        """지금 바가 붙어 있는 턴 번호. 없으면 None."""
        return self._turn_no

    def label_text(self):
        """바 문구. 검증 하네스가 읽는다."""
        return self._label.text()

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _summary(self, attempts):
        """시도 목록 한 줄. 사유 본문은 반복하지 않는다(모듈 docstring 참조)."""
        names = [a.tool_name or "(이름 없음)" for a in attempts]
        shown = names[:NAME_LIST_MAX]
        tail = len(names) - len(shown)
        joined = ", ".join(shown)
        if tail > 0:
            joined += " 외 %d건" % tail
        return "권한이 거부되어 %d건이 실행되지 않았습니다: %s" % (len(names), joined)

    def _on_retry(self):
        """재시도 버튼. 바를 내리고 신호만 낸다."""
        self.hide_bar()
        self.retry_requested.emit()

    def _on_keep(self):
        """거부 유지 버튼."""
        self.hide_bar()
        self.keep_denied.emit()


class ExclusionNoticeBar(QFrame):
    """제외 관측 시 전사 하단에 끼우는 비차단 안내 바(설계 3-5 표 "제외" 행).

    거부 바와 두 가지가 다르다.

        * 행동 버튼이 없다. 상승으로 풀리지 않는 상태이므로 누를 것이 없다.
          포스처 전환 안내만 문구로 준다.
        * 사유 본문을 반복하지 않는다. 도구 카드가 "포스처에 없음" 으로
          이미 보여 준다.

    시그널 하나만 낸다.

        dismissed()  "확인" 을 눌러 바를 닫았다
    """

    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        """숨은 상태로 만든다. 제외가 관측될 때 show_exclusions() 가 띄운다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatExclusionBar")
        self.setFrameShape(QFrame.NoFrame)

        self._label, (self._close,) = build_bar(
            self, [(EXCLUSION_CLOSE_TEXT, "")])
        self._close.clicked.connect(self._on_close)

        self._turn_no = None
        self.setVisible(False)

    def show_exclusions(self, turn_no, attempts):
        """제외된 시도 목록을 한 줄로 요약해 띄운다. 턴당 하나다.

        Args:
            turn_no: 턴 번호.
            attempts: machine.ExclusionAttempt 목록.

        Returns:
            bool: 지금 바가 보이는가.
        """
        attempts = list(attempts or ())
        if not attempts:
            self.hide_bar()
            return False
        self._turn_no = turn_no
        names = [a.tool_name or "(이름 없음)" for a in attempts]
        shown = names[:NAME_LIST_MAX]
        tail = len(names) - len(shown)
        joined = ", ".join(shown)
        if tail > 0:
            joined += " 외 %d건" % tail
        self._label.setText(EXCLUSION_TEXT % (len(names), joined))
        self.setVisible(True)
        return True

    def hide_bar(self):
        """바를 내린다."""
        self._turn_no = None
        self.setVisible(False)

    def turn_no(self):
        """지금 바가 붙어 있는 턴 번호. 없으면 None."""
        return self._turn_no

    def label_text(self):
        """바 문구. 검증 하네스가 읽는다."""
        return self._label.text()

    def _on_close(self):
        """확인 버튼. 바를 내리고 신호만 낸다."""
        self.hide_bar()
        self.dismissed.emit()


class StaleCwdBar(QFrame):
    """QGIS 프로젝트가 바뀌어 cwd 가 낡았을 때 띄우는 바(설계 8, S5-3).

    **자동 재시작하지 않는다.** 재spawn 은 맥락을 `--resume` 로만 이어 붙이고
    모델이 들고 있던 레이어 지식은 그대로 낡는다. 그 시점을 사용자가 고르게
    한다는 것이 설계 8 의 결정이다. 그래서 버튼을 눌러야 바뀐다.

    시그널 둘.

        restart_requested(str)  새 폴더로 재시작해 달라
        dismissed()             낡은 채로 쓰겠다
    """

    restart_requested = pyqtSignal(str)
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        """숨은 상태로 만든다. 프로젝트 전환이 관측될 때 show_stale() 이 띄운다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatStaleBar")
        self.setFrameShape(QFrame.NoFrame)

        self._label, (self._restart, self._keep) = build_bar(
            self, [(STALE_RESTART_TEXT, ""), (STALE_KEEP_TEXT, "")])
        self._restart.clicked.connect(self._on_restart)
        self._keep.clicked.connect(self._on_keep)

        self._target = ""
        self.setVisible(False)

    def show_stale(self, project_name, new_cwd):
        """낡음을 알린다.

        Args:
            project_name: 바뀐 프로젝트 이름(사람이 읽는 값).
            new_cwd: 새 프로젝트 기준 작업 폴더.

        Returns:
            bool: 지금 바가 보이는가.
        """
        self._target = str(new_cwd or "")
        self._label.setText(STALE_TEXT % (project_name or "(이름 없음)", self._target))
        self.setVisible(True)
        return True

    def hide_bar(self):
        """바를 내린다."""
        self._target = ""
        self.setVisible(False)

    def target(self):
        """버튼이 쓸 새 폴더. 없으면 빈 문자열."""
        return self._target

    def label_text(self):
        """바 문구. 검증 하네스가 읽는다."""
        return self._label.text()

    def _on_restart(self):
        """새 폴더로 재시작. 경로를 신호에 실어 보낸다."""
        target = self._target
        self.hide_bar()
        self.restart_requested.emit(target)

    def _on_keep(self):
        """낡은 채로 쓰겠다."""
        self.hide_bar()
        self.dismissed.emit()


class ExportNoticeBar(QFrame):
    """전사 내보내기 결과를 알리는 비차단 바 (0.2.3).

    왜 바인가
        QFileDialog 가 금지 목록이라(설계 3-5) 저장 경로를 묻지 않고 고정
        경로에 쓴다. 그러면 **어디에 썼는지**를 알릴 자리가 필요하고, 그
        자리는 모달이 아니어야 한다. 바 문구에 경로 전문을 적고 폴더를 여는
        버튼을 하나 둔다.

    실패도 같은 바에 적는다. 실패를 조용히 삼키면 사용자는 저장된 줄 알고
    파일을 찾는다.

    0.2.4: 복사가 레다크션 관문에서 막힌 것도 이 바가 알린다
    (`show_copy_failed`). 조용히 삼키면 사용자는 복사된 줄 알고 붙여 넣는다.

    0.4.0(사용자 요청): **성공 안내만** EXPORT_AUTO_HIDE_MS 뒤에 저절로
    내려간다. 저장은 끝난 일이라 읽고 나면 자리를 비워야 하고, 실패는
    사용자가 읽었는지 알 수 없으므로 그대로 남긴다.

    0.4.2(사용자 요청): 우상단에 닫기(X)를 더했다. 아래 줄의 [확인] 과 같은
    일을 하고(`_on_close`), 성공·실패 양쪽에 똑같이 달린다. 자동 숨김을
    대체하지 않는다 - 성공 안내는 여전히 저절로 내려가고, X 는 그 전에
    치우고 싶을 때와 자동 숨김이 없는 실패 안내에 쓴다.

    시그널 둘.
        open_requested(str)  저장한 파일이 있는 폴더를 열어 달라
        dismissed()          바를 닫았다
    """

    open_requested = pyqtSignal(str)
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        """숨은 상태로 만든다. 내보내기가 끝나면 show_saved/show_failed 가 띄운다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatExportBar")
        self.setFrameShape(QFrame.NoFrame)

        self._label, (self._open, self._close) = build_bar(
            self, [(EXPORT_OPEN_TEXT, ""), (EXPORT_CLOSE_TEXT, "")])
        self._open.clicked.connect(self._on_open)
        self._close.clicked.connect(self._on_close)

        # 우상단 닫기(0.4.2). 본문 라벨을 가로 줄로 감싸 그 줄의 오른쪽
        # **위**에 둔다. 바 맨 위에 자기 줄을 하나 더 얹지 않는 이유는 그러면
        # 바가 한 줄 더 높아지기 때문이다 - 사용자가 줄여 달라고 한 축과
        # 반대로 간다. 라벨은 줄바꿈이라 X 는 첫 줄 오른쪽에 걸린다.
        outer = self.layout()
        head = QWidget(self)
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(BAR_SPACING)
        outer.removeWidget(self._label)
        self._label.setParent(head)
        head_layout.addWidget(self._label, 1)

        self._x = QToolButton(head)
        self._x.setObjectName("UpwiseChatExportClose")
        self._x.setToolTip(EXPORT_X_TIP)
        self._x.setAccessibleName(EXPORT_X_TIP)
        self._x.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._x.setIcon(self.style().standardIcon(QStyle.SP_TitleBarCloseButton))
        self._x.setIconSize(QSize(EXPORT_X_ICON_PX, EXPORT_X_ICON_PX))
        self._x.setAutoRaise(True)
        self._x.setCursor(Qt.PointingHandCursor)
        # clicked 는 bool 을 넘긴다. 기본값 인자를 가진 슬롯에 바로 이으면
        # 그 bool 이 인자로 들어가 조용히 다른 길로 간다(README 5 S4 실측) -
        # 인자를 삼키는 람다로 잇는다.
        self._x.clicked.connect(lambda _checked=False: self._on_close())
        head_layout.addWidget(self._x, 0, Qt.AlignTop)
        outer.insertWidget(0, head)

        # 성공 안내 자동 숨김 타이머(0.4.0). 단발이고, 새 show_* 가 오거나
        # 사용자가 버튼을 누르면 정리된다 - 켜 둔 채로 두면 사용자가 읽는
        # 중인 다음 안내를 이 타이머가 내린다.
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(EXPORT_AUTO_HIDE_MS)
        self._hide_timer.timeout.connect(self._on_auto_hide)

        self._path = ""
        self.setVisible(False)

    def show_saved(self, path):
        """저장 성공을 알린다. 잠시 뒤 저절로 내려간다(0.4.0).

        Args:
            path: 쓴 파일 경로.

        Returns:
            bool: 지금 바가 보이는가.
        """
        self._path = str(path or "")
        self._label.setText(EXPORT_SAVED_TEXT % self._path)
        self._open.setEnabled(True)
        self._open.setToolTip("")
        self.setVisible(True)
        # start() 는 돌고 있던 타이머를 처음부터 다시 돌린다. 연속 저장이면
        # 마지막 안내가 자기 시간을 온전히 받는다.
        self._hide_timer.start()
        return True

    def show_failed(self, reason):
        """저장 실패를 알린다. 열 폴더가 없으므로 열기 버튼을 잠근다.

        Args:
            reason: 사용자에게 보일 사유.

        Returns:
            bool: 지금 바가 보이는가.
        """
        self._path = ""
        self._label.setText(EXPORT_FAILED_TEXT % (reason or "사유 없음"))
        self._open.setEnabled(False)
        self._open.setToolTip(EXPORT_OPEN_DISABLED_TIP)
        self.setVisible(True)
        # 실패는 자동으로 내리지 않는다. 앞선 성공 안내의 타이머가 돌고
        # 있었다면 여기서 끈다 - 안 끄면 그 타이머가 이 실패를 내린다.
        self._hide_timer.stop()
        return True

    def show_copy_failed(self, reason):
        """복사 실패를 알린다 (0.2.4).

        왜 같은 바인가
            사용자가 안내를 찾는 자리가 한 군데여야 한다(독 _build_body 의
            바 배치 주석). 복사용 바를 따로 두면 같은 축의 알림이 두 자리로
            갈라지고, qss 선택자와 대비 쌍도 하나 더 늘어난다.

        Args:
            reason: 사용자에게 보일 사유.

        Returns:
            bool: 지금 바가 보이는가.
        """
        self._path = ""
        self._label.setText(COPY_FAILED_TEXT % (reason or "사유 없음"))
        self._open.setEnabled(False)
        self._open.setToolTip(COPY_OPEN_DISABLED_TIP)
        self.setVisible(True)
        # show_failed 와 같은 근거로 자동 숨김을 끈다.
        self._hide_timer.stop()
        return True

    def hide_bar(self):
        """바를 내린다."""
        self._path = ""
        self._hide_timer.stop()
        self.setVisible(False)

    def target(self):
        """열기 버튼이 쓸 파일 경로. 실패했으면 빈 문자열."""
        return self._path

    def label_text(self):
        """바 문구. 검증 하네스가 읽는다."""
        return self._label.text()

    def open_enabled(self):
        """열기 버튼이 눌리는 상태인가. 검증 하네스가 읽는다."""
        return self._open.isEnabled()

    def auto_hide_active(self):
        """자동 숨김 타이머가 돌고 있는가. 검증 하네스가 읽는다."""
        return self._hide_timer.isActive()

    def auto_hide_ms(self):
        """자동 숨김 간격(ms). 검증 하네스가 읽는다."""
        return int(self._hide_timer.interval())

    def close_button(self):
        """우상단 닫기 버튼(0.4.2). 검증 하네스가 눌러 본다."""
        return self._x

    def close_button_visible(self):
        """우상단 닫기 버튼이 지금 보이는가. 검증 하네스가 읽는다.

        바가 숨어 있으면 False 다 - 자식은 부모가 숨으면 같이 숨는다.
        """
        return bool(self._x.isVisible())

    def fire_auto_hide(self):
        """타이머를 기다리지 않고 자동 숨김을 지금 일으킨다.

        검증 하네스가 8초를 실제로 기다리지 않게 하는 창구다. 제품 경로는
        이 메서드를 부르지 않는다 - 타이머의 timeout 이 같은 슬롯을 친다.

        Returns:
            bool: 호출 뒤 바가 보이는가.
        """
        self._hide_timer.stop()
        self._on_auto_hide()
        return self.isVisible()

    def _on_auto_hide(self):
        """타이머 만료. 바만 내리고 dismissed 는 내지 않는다.

        dismissed 는 "사용자가 닫았다" 는 사실이고 그 신호에 붙은 쪽이
        사용자 행동으로 읽는다. 저절로 내려간 것은 그 사실이 아니다.
        """
        self.hide_bar()

    def _on_open(self):
        """폴더 열기. 경로를 신호에 실어 보낸다(여는 것은 독이 한다)."""
        if not self._path:
            return
        # 사용자가 손을 댔으므로 자동 숨김을 거둔다. 폴더를 열어 놓고
        # 돌아왔을 때 경로 안내가 사라져 있으면 어디를 열었는지 못 찾는다.
        self._hide_timer.stop()
        self.open_requested.emit(self._path)

    def _on_close(self):
        """확인 버튼."""
        self.hide_bar()
        self.dismissed.emit()
