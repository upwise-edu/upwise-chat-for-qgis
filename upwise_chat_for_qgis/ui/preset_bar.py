"""전제조건 바, 프리셋 행, 스킬 마커 안내 바 (S6).

설계 7-1 의 레이아웃 중 이 모듈이 맡는 것

    [2] 전제조건 바  PrereqBar. 미충족 항목만 적는다. 다 충족이면 숨는다
    [3] 프리셋 행    PresetRow. 버튼 5개, 비활성 시 이유를 툴팁으로 붙인다

그리고 설계 6-2 의 사후 판정 안내가 하나 더 있다.

    SkillMarkerBar  마커가 안 보인 프리셋 턴에 "스킬이 호출되지 않았습니다" 와
                    [자연어로 다시 요청] 버튼을 띄운다

0.2.0 이 더한 것 하나(설계 docs/2 3-3)

    PostureConfirmBar  읽기 전용 상태에서 수집 버튼을 누르면 "수집 모드로
                       바꾸고 백엔드를 재시작합니다" 를 비모달 바로 묻는다

왜 버튼이 입력 박스에 넣기만 하는가
    프리셋 5개 중 4개가 대상(어느 pN, 어느 레이어)을 암묵 인자로 받는다(F10).
    자동 전송하면 범위가 틀린 실행이 된다. 그래서 주입 + 포커스가 기본이고
    자동 전송은 전제조건이 없는 connect-check 하나뿐이다(설계 6-1). 어느 것을
    자동 전송하는지는 이 모듈이 정하지 않는다 - detect.PRESET_AUTOSEND 가 정본이고
    독이 읽는다.

왜 비활성 이유를 툴팁으로 두는가
    모달을 쓸 수 없다(설계 3-5: 모달 팝업이 자동화를 정지시킨다). 눌렀을 때
    대화상자로 알리는 경로가 막혀 있으므로, 누르기 전에 읽을 수 있는 자리에
    이유를 둔다. 버튼이 왜 꺼져 있는지 모른 채로 두지 않는 것이 요구사항이다
    (설계 7-1 [3] "비활성 시 이유 툴팁").

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog, QFileDialog,
중첩 이벤트 루프. Qt import 는 전부 qgis.PyQt 셰임 경로로 한다(설계 7-4).

설계 정본: docs/1.mvp_design_v1.md 6-1, 6-2, 6-3, 7-1
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
)

from ..backend import detect
from . import theme as theme_mod
from .approval_bar import bar_button, bar_label, build_bar

# 전제조건 바 머리말. 항목이 여러 개면 줄로 나눈다.
PREREQ_HEADER = "준비되지 않은 항목"

# 전제조건 항목 심각도 태그(0.2.2). 색만으로 가르지 않는다 - 색각 이상과
# 흑백 캡처에서 사라지기 때문이다. 태그는 detect 의 상태 상수에서 온다.
PREREQ_TAG = {
    theme_mod.LEVEL_UNMET: "미충족",
    theme_mod.LEVEL_UNKNOWN: "확인 중",
}

# 전제조건 바에 펼쳐 적는 항목 수 상한(0.2.2 과밀 완화). 넘으면 접고 전문은
# 툴팁에 남긴다 - 바가 전사 영역을 먹지 않아야 한다.
PREREQ_ITEM_MAX = 3
PREREQ_MORE_TEXT = "외 %d건 (마우스를 올리면 전부 보입니다)"

# 심각도 태그 열 최소 폭(px). 태그 글자 수가 달라도 본문 왼쪽 끝이 맞아야
# 여러 줄이 표로 읽힌다. 글꼴 크기는 고정하지 않는다(설계 7-3).
PREREQ_TAG_MIN_W = 54

# 프리셋 행 머리말. 버튼만 있으면 무엇을 누르는 것인지 알기 어렵다.
PRESET_HEADER = "프리셋"

# 프리셋 버튼 격자 열 수.
#
# 0.2.2 는 3이었다 - "5개를 한 줄에 늘어놓으면 좁은 독에서 독의 최소 폭을
# 밀어 올린다" 가 그때의 근거였고, 그 시점 버튼은 열 늘림을 받아 80 px 면
# 이었다(5개면 400 px 이 넘는다).
#
# 0.5.1(사용자 실기 피드백 2026-10-17: "프리셋 잘 줄었어요. 그리고 한 줄로
# 만들어도 될 것 같아요"): 3 -> 5. 0.4.2 가 열 늘림을 걷어내고 최소 폭을
# 48 로 내린 뒤 버튼은 글자 폭에 머문다 - 다섯을 한 줄에 놓아도 카드 최소
# 폭은 글자 폭의 합뿐이고, 그 값은 하네스 47 W1·51 D4 가 재는 임계(480)
# 안이다. 실측값은 로그가 정본이다(여기 숫자를 추정으로 적지 않는다).
# 버튼 수는 5다 - 프리셋 4 + [점검] 1 이라 5열이면 1행이다.
PRESET_COLUMNS = 5

# 프리셋 버튼 최소 폭(px).
#
# 0.4.2(사용자 실기 피드백 2026-10-17: "텍스트 길이에 비해 버튼 영역이 너무
# 넓습니다"): 92 -> 48. 92 는 0.2.2 에서 "격자 열이 고르게 늘어나도 글자가
# 잘리지 않게" 둔 값인데, 열 늘림(setColumnStretch)을 걷어낸 지금은 짧은
# 버튼("수집" 실측 48 px)을 두 배로 부풀리는 값이 된다. 48 은 두 글자 버튼의
# 실측 폭이라 이 값이 폭을 정하지 않는다 - 바닥만 남긴다.
PRESET_BUTTON_MIN_W = 48

# U7 카드 안쪽 여백(px). 독 루트 여백(dock.LAYOUT_MARGIN=8)보다 작게 둔다 -
# 카드 안에서 같은 크기를 다시 주면 좁은 독에서 버튼이 받는 폭이 줄어든다.
PRESET_CARD_PADDING = 6

# 활성 프리셋 버튼의 툴팁. 슬래시 명령 원문을 보여 준다 - 수강생이 터미널에서
# 같은 것을 쓸 수 있어야 하고, 주입된 문자열과 보이는 것이 같아야 한다.
PRESET_TIP_READY = "%s\n입력 박스에 넣습니다. 대상을 적고 보내세요."
PRESET_TIP_AUTOSEND = "%s\n바로 보냅니다."

# 마커 안내 바 문구(설계 6-2). detect 의 상수를 그대로 쓴다.
MARKER_MISS_TEXT = "%s: " + detect.MARKER_FAIL_TEXT

# 자체 점검 버튼(0.3.0, 설계 5-4 (b)). 라벨을 "연결 점검" 으로 두는 이유는
# 사용자가 0.2.x 에서 같은 자리의 같은 말을 눌렀기 때문이다 - 안쪽 기전만
# 바뀌었고(유료 1턴 -> 0턴) 사용자가 묻는 질문은 같다.
CHECK_LABEL = "연결 점검"
CHECK_TIP = ("내장 QGIS 서버에 바로 물어 포트·버전·레이어 수를 확인합니다.\n"
             "모델을 호출하지 않으므로 토큰이 들지 않습니다.")


class PrereqBar(QFrame):
    """[2] 전제조건 바. 미충족 항목만 적고, 없으면 숨는다(설계 7-1).

    시그널을 내지 않는다. 안내 전용이고 행동 버튼은 프리셋 행과 입력 영역이
    가지고 있다.
    """

    def __init__(self, parent=None):
        """숨은 상태로 만든다. show_items() 가 띄운다.

        0.2.2: 한 라벨에 "\\n- " 로 이어 붙이던 것을 **항목마다 한 행**으로
        바꿨다. 줄바꿈이 일어나면 이어지는 줄이 "- " 아래로 흘러 어느 항목의
        연장인지 안 읽혔다. 행은 [심각도 태그][본문] 두 칸이다.
        """
        super().__init__(parent)
        self.setObjectName("UpwiseChatPrereqBar")
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(3)

        self._head = QLabel(PREREQ_HEADER, self)
        self._head.setObjectName("UpwiseChatPrereqHeader")
        theme_mod.set_role(self._head, theme_mod.ROLE_CAPTION)
        layout.addWidget(self._head)

        # 항목 행이 들어가는 격자. 태그 열은 폭을 고정해 본문 왼쪽을 맞춘다.
        self._grid_holder = QFrame(self)
        self._grid_holder.setFrameShape(QFrame.NoFrame)
        self._grid = QGridLayout(self._grid_holder)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(3)
        self._grid.setColumnStretch(1, 1)
        layout.addWidget(self._grid_holder)

        # 접힌 나머지 항목 한 줄. 전문은 툴팁에 있다.
        self._more = bar_label(self)
        self._more.setObjectName("UpwiseChatPrereqMore")
        self._more.setVisible(False)
        layout.addWidget(self._more)

        # 하위 호환 조회 창구. label_text() 가 돌려주는 한 덩어리 글이다.
        self._label = QLabel("", self)
        self._label.setObjectName("UpwiseChatPrereqText")
        self._label.setVisible(False)

        self._codes = ()
        self._rows = []
        self.setVisible(False)

    def _clear_rows(self):
        """격자의 행 위젯을 전부 걷어낸다."""
        for widgets in self._rows:
            for widget in widgets:
                self._grid.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()
        self._rows = []

    def show_items(self, items):
        """미충족 항목을 적는다. 빈 목록이면 바를 내린다.

        Args:
            items: (코드, 한 줄) 또는 (코드, 한 줄, 심각도) 튜플 목록.
                앞 둘은 detect.Prerequisites.unmet_items() 의 반환형이고,
                독이 백엔드 기동 실패 항목을 앞에 더해 넘긴다. 심각도는
                theme.LEVEL_* 이고 없으면 LEVEL_UNMET 으로 본다 - 이 바는
                원래 "미충족만" 적는 자리다.

        Returns:
            bool: 지금 바가 보이는가.
        """
        rows = []
        for item in (items or ()):
            if not item:
                continue
            code = str(item[0])
            text = str(item[1])
            level = str(item[2]) if len(item) > 2 else theme_mod.LEVEL_UNMET
            if level not in PREREQ_TAG:
                level = theme_mod.LEVEL_UNMET
            rows.append((code, text, level))

        self._clear_rows()
        if not rows:
            self._codes = ()
            self._label.setText("")
            self._more.setVisible(False)
            self.setVisible(False)
            return False

        self._codes = tuple(code for code, _t, _l in rows)
        shown = rows[:PREREQ_ITEM_MAX]
        hidden = rows[PREREQ_ITEM_MAX:]
        for i, (_code, text, level) in enumerate(shown):
            tag = QLabel(PREREQ_TAG[level], self._grid_holder)
            tag.setMinimumWidth(PREREQ_TAG_MIN_W)
            tag.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            theme_mod.set_level(tag, level)
            body = QLabel(text, self._grid_holder)
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            theme_mod.set_role(body, theme_mod.ROLE_WARN_TEXT)
            self._grid.addWidget(tag, i, 0)
            self._grid.addWidget(body, i, 1)
            self._rows.append((tag, body))

        if hidden:
            self._more.setText(PREREQ_MORE_TEXT % len(hidden))
            self._more.setToolTip("\n".join(
                "%s: %s" % (PREREQ_TAG[l], t) for _c, t, l in hidden))
            self._more.setVisible(True)
        else:
            self._more.setToolTip("")
            self._more.setVisible(False)

        self._label.setText("\n".join(
            [PREREQ_HEADER] + ["- " + t for _c, t, _l in rows]))
        self.setVisible(True)
        return True

    def codes(self):
        """지금 적혀 있는 항목 코드들. 검증 하네스가 읽는다."""
        return tuple(self._codes)

    def levels(self):
        """지금 적혀 있는 항목 심각도들(0.2.2). 검증 하네스가 읽는다."""
        return tuple(
            str(tag.property(theme_mod.LEVEL_PROPERTY)) for tag, _body in self._rows)

    def label_text(self):
        """바에 적힌 글. 검증 하네스가 읽는다.

        행 위젯으로 나뉘기 전과 같은 한 덩어리 문자열을 돌려준다. 접어 둔
        항목도 포함한다 - 이 창구는 "무엇을 적기로 했는가" 를 묻는 자리다.
        """
        return self._label.text()

    def more_visible(self):
        """접힌 항목 안내 줄을 띄우기로 했는가."""
        return not self._more.isHidden()


class PresetRow(theme_mod.GradientBorderFrame):
    """[3] 프리셋 행. 프리셋 버튼 4개 + 자체 점검 버튼 1개.

    U7·U4(0.3.x): 면 없는 행에서 **카드**로 바뀌었다. 면과 모서리는 qss
    (`#UpwiseChatPresetRow`)가, 테두리는 베이스 클래스의 QPainter 가 로고 색
    그라데이션으로 그린다. 베이스를 갈아 끼운 것뿐이라 바깥 계약(시그널,
    `states()`, `button()`, 격자)은 그대로다 - GradientBorderFrame 도
    QFrame 이다.

    시그널 둘을 낸다.

        preset_clicked(str)  눌린 프리셋 이름(스킬 front matter name)
        check_requested()    [점검] - 0.3.0. **프리셋이 아니다**

    0.3.0(설계 5-4 결정 D-B6 (b)): 맨 앞 `qgis-connect-check` 프리셋이
    사라지고 그 자리에 [점검] 버튼이 온다. 둘의 차이가 이 클래스의 구조를
    정한다 - 프리셋은 모델에게 보내는 **입력**이고(슬래시 명령 주입), 점검은
    플러그인이 내장 서버 핸들러를 직접 불러 답하는 **지역 동작**이다. 모델 턴
    0·유료 토큰 0·결정적이다. 그래서 `_buttons` 표에 넣지 않고 따로 둔다 -
    넣으면 `set_states()` 가 전제조건으로 그것을 꺼 버린다.
    """

    preset_clicked = pyqtSignal(str)
    check_requested = pyqtSignal()

    def __init__(self, parent=None):
        """버튼을 만든다. 프리셋은 전부 비활성에서 시작한다.

        전제조건을 모르는 상태에서 활성으로 두면 누를 수 있는 것이 되고, 그때
        눌리면 claude 경로도 없이 전송을 시도한다. set_states() 가 켠다.
        [점검] 은 **처음부터 활성**이다 - claude 도 init 도 필요 없고, 서버가
        꺼져 있으면 그 사실을 답하는 것이 그 버튼의 일이다.
        """
        super().__init__(parent)
        self.setObjectName("UpwiseChatPresetRow")
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        # U7: 카드 안쪽 여백. 0 으로 두면 그라데이션 테두리가 버튼에 붙어
        # 카드가 아니라 버튼에 선을 그은 것처럼 보인다. 다른 카드(전제조건
        # 바·키 패널)의 여백과 같은 크기다.
        layout.setContentsMargins(PRESET_CARD_PADDING, PRESET_CARD_PADDING,
                                  PRESET_CARD_PADDING, PRESET_CARD_PADDING)
        layout.setSpacing(2)

        head = QLabel(PRESET_HEADER, self)
        head.setObjectName("UpwiseChatPresetHeader")
        theme_mod.set_role(head, theme_mod.ROLE_CAPTION)
        layout.addWidget(head)

        # 격자를 쓴다. 0.2.2 가 한 줄 QHBoxLayout 에서 3열 격자로 옮겼고,
        # 0.5.1 이 그 격자의 열 수를 5로 올려 다시 한 줄이 됐다(사용자 실기
        # 피드백 2026-10-17). QHBoxLayout 으로 되돌리지 않는 이유는 칸 위치가
        # 판정 대상이기 때문이다 - 하네스 27 L2 가 격자 칸으로 1줄을 단정한다.
        row = QFrame(self)
        row.setFrameShape(QFrame.NoFrame)
        grid = QGridLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)
        # 0.4.2: 버튼 열에 늘림을 주지 않는다(사용자 실기 피드백 2026-10-17).
        # 전에는 세 열이 1:1:1 로 늘어나 버튼이 독 폭을 가득 채웠고, 두 글자
        # 버튼이 200 px 면이 되는 일이 있었다. 남는 폭은 **버튼 뒤의 빈 열**
        # 하나가 받는다 - 그래야 버튼은 글자 폭에 머물면서 왼쪽에 모인다.
        # 이 빈 열에는 위젯이 없으므로 하네스 27 L2 의 셀 판정은 버튼 칸만
        # 센다(0.5.1 에서 그 기대값이 1행 4열로 갱신됐다).
        grid.setColumnStretch(PRESET_COLUMNS, 1)

        # [점검] 이 0번 칸이다. 0.2.x 에서 `qgis-connect-check` 가 있던 자리고,
        # 사용자가 "먼저 누르는 것" 의 위치를 바꾸지 않는다.
        self.check_button = bar_button(row, CHECK_LABEL, "UpwiseChatSelfCheck")
        self.check_button.setMinimumWidth(PRESET_BUTTON_MIN_W)
        # 0.4.2: 여백 축소 역할(theme.ROLE_PRESET). 프리셋 버튼과 같은 모양을
        # 받아야 격자 두 줄이 한 덩이로 읽힌다.
        theme_mod.set_role(self.check_button, theme_mod.ROLE_PRESET)
        self.check_button.setToolTip(CHECK_TIP)
        self.check_button.clicked.connect(
            lambda _checked=False: self.check_requested.emit())
        grid.addWidget(self.check_button, 0, 0)

        self._buttons = {}
        for i, preset in enumerate(detect.PRESET_ORDER):
            button = bar_button(row, detect.PRESET_LABELS.get(preset, preset),
                                "UpwiseChatPreset_" + preset)
            button.setMinimumWidth(PRESET_BUTTON_MIN_W)
            theme_mod.set_role(button, theme_mod.ROLE_PRESET)
            button.setEnabled(False)
            # 눌린 프리셋 이름을 그대로 올린다. clicked 의 bool 인자를 삼키려고
            # 기본값으로 묶어 둔다(늦은 바인딩을 피한다).
            button.clicked.connect(
                lambda _checked=False, name=preset: self.preset_clicked.emit(name)
            )
            # 0.3.0: [점검] 이 0번 칸을 쓰므로 프리셋은 1번부터 놓는다.
            slot = i + 1
            grid.addWidget(button, slot // PRESET_COLUMNS, slot % PRESET_COLUMNS)
            self._buttons[preset] = button
        layout.addWidget(row)

        self._reasons = {}

    def set_states(self, states):
        """프리셋별 활성 여부와 이유를 반영한다(설계 7-1 [3]).

        Args:
            states: (프리셋, 활성 여부, 이유) 목록.
                detect.Prerequisites.preset_states() 의 반환형이다.

        Returns:
            int: 활성인 버튼 수.
        """
        enabled_n = 0
        for preset, enabled, reason in states or ():
            button = self._buttons.get(preset)
            if button is None:
                continue
            button.setEnabled(bool(enabled))
            self._reasons[preset] = str(reason or "")
            command = detect.slash_command(preset)
            if enabled:
                enabled_n += 1
                tip_fmt = (PRESET_TIP_AUTOSEND if preset in detect.PRESET_AUTOSEND
                           else PRESET_TIP_READY)
                tip = tip_fmt % command
                # 활성이지만 "확인 중" 같은 단서가 있으면 함께 적는다.
                if reason:
                    tip += "\n" + str(reason)
            else:
                tip = str(reason or "지금은 쓸 수 없습니다")
            button.setToolTip(tip)
        return enabled_n

    def button(self, preset):
        """버튼 하나. 검증 하네스가 눌러 본다."""
        return self._buttons.get(preset)

    def states(self):
        """프리셋별 (활성, 툴팁) 요약. 검증 하네스가 읽는다."""
        return {
            preset: (button.isEnabled(), button.toolTip())
            for preset, button in self._buttons.items()
        }

    def reason(self, preset):
        """마지막으로 반영한 비활성 이유."""
        return self._reasons.get(preset, "")


class PostureConfirmBar(QFrame):
    """포스처 상승 확인 바 (0.2.0, 설계 docs/2 3-3).

    수집 버튼을 읽기 전용 상태에서 누르면 이 바가 뜬다. 모달을 쓸 수 없으므로
    (설계 3-5) 확인을 비모달 바로 받는다. 바가 떠 있는 동안에도 QGIS 조작이
    되고 자동화가 멈추지 않는다.

    시그널 둘을 낸다.

        confirmed(str)  전환 승인. 인자는 누른 프리셋 이름
        cancelled()     취소

    거부 바(approval_bar.DenialRetryBar)와 다른 축이다. 거부 바는 **이미 거부
    된 뒤** 올리는 것이고, 이 바는 **올리기 전에** 묻는다.
    """

    confirmed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        """숨은 상태로 만든다. ask() 가 띄운다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatPostureConfirmBar")
        self.setFrameShape(QFrame.NoFrame)

        self._label, (self._ok, self._no) = build_bar(
            self, [("전환", "UpwiseChatPostureConfirmOk"), ("취소", "")])
        self._ok.clicked.connect(self._on_ok)
        self._no.clicked.connect(self._on_cancel)

        self._preset = ""
        self._posture = ""
        self.setVisible(False)

    def ask(self, preset, posture_name, text):
        """전환 여부를 묻는다.

        Args:
            preset: 전환 뒤에 주입할 프리셋 이름.
            posture_name: 올릴 포스처 이름.
            text: 바에 적을 한 줄. 상수는 backend.posture 가 들고 있다.

        Returns:
            bool: 지금 바가 보이는가.
        """
        self._preset = str(preset or "")
        self._posture = str(posture_name or "")
        self._label.setText(str(text or ""))
        self.setVisible(True)
        return True

    def hide_bar(self):
        """바를 내린다."""
        self._preset = ""
        self._posture = ""
        self.setVisible(False)

    def preset(self):
        """지금 바가 가리키는 프리셋 이름."""
        return self._preset

    def posture(self):
        """지금 바가 올리려는 포스처 이름."""
        return self._posture

    def label_text(self):
        """바에 적힌 글. 검증 하네스가 읽는다."""
        return self._label.text()

    def _on_ok(self):
        """전환 승인. 프리셋 이름을 실어 올린다."""
        preset = self._preset
        self.hide_bar()
        self.confirmed.emit(preset)

    def _on_cancel(self):
        """취소. 포스처를 바꾸지 않는다."""
        self.hide_bar()
        self.cancelled.emit()


class SkillMarkerBar(QFrame):
    """마커가 안 보인 프리셋 턴의 안내 바(설계 6-2).

    시그널 둘을 낸다.

        fallback_requested(str)  자연어로 다시 요청. 인자는 프리셋 이름
        dismissed()              닫기

    이 바는 승인/권한과 무관하다. 거부 바(approval_bar.DenialRetryBar)와 문구와
    버튼이 달라야 한다 - 여기서 막힌 것은 권한이 아니라 **슬래시 명령이 스킬로
    해석되지 않은 것**(D02)이고, 포스처를 올려도 풀리지 않는다.
    """

    fallback_requested = pyqtSignal(str)
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        """숨은 상태로 만든다. show_miss() 가 띄운다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatSkillMarkerBar")
        self.setFrameShape(QFrame.NoFrame)

        self._label, (self._retry, self._close) = build_bar(
            self, [(detect.MARKER_FALLBACK_BUTTON, ""), ("확인", "")])
        self._retry.clicked.connect(self._on_retry)
        self._close.clicked.connect(self._on_close)

        self._turn_no = None
        self._preset = ""
        self.setVisible(False)

    def show_miss(self, turn_no, preset):
        """마커 미검출을 알린다.

        Args:
            turn_no: 턴 번호.
            preset: 그 턴을 띄운 프리셋 이름.

        Returns:
            bool: 지금 바가 보이는가.
        """
        self._turn_no = turn_no
        self._preset = str(preset or "")
        self._label.setText(
            MARKER_MISS_TEXT % detect.PRESET_LABELS.get(self._preset, self._preset)
        )
        self._retry.setToolTip(detect.fallback_prompt(self._preset))
        self.setVisible(True)
        return True

    def hide_bar(self):
        """바를 내린다."""
        self._turn_no = None
        self._preset = ""
        self.setVisible(False)

    def turn_no(self):
        """지금 바가 가리키는 턴 번호."""
        return self._turn_no

    def preset(self):
        """지금 바가 가리키는 프리셋 이름."""
        return self._preset

    def label_text(self):
        """바에 적힌 글. 검증 하네스가 읽는다."""
        return self._label.text()

    def _on_retry(self):
        """자연어 재요청. 프리셋 이름을 실어 올린다."""
        preset = self._preset
        self.hide_bar()
        self.fallback_requested.emit(preset)

    def _on_close(self):
        """닫기. 그 턴은 다시 띄우지 않는다(판단은 독이 한다)."""
        self.dismissed.emit()
