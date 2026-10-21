"""바텀 내비 (docs/6 2절 "플로팅 바텀 내비" 보류분의 채택 구현).

무엇인가
    본문 아래쪽에 놓이는 알약 모양 한 줄이다. 지금 어느 칸을 보고 있는지를
    말하고, 누르면 그 칸으로 바꾼다. 칸은 셋이다.

        대화   전사만 본다(키 패널·통계 칸을 내린다)
        키     공공 API 키 패널을 연다
        통계   사용량·수집 차트 칸을 연다

왜 보류였고 무엇이 바뀌었나
    docs/6 2절은 "독 최소 폭 347 px 에서 공간 비용 큼" 을 이유로 보류했다.
    그 비용은 **세로 한 줄**이고, 이 패스가 통계 칸을 더하면서 "지금 무엇을
    보고 있는가" 를 말할 자리가 어차피 필요해졌다. 헤더에 토글을 하나 더
    얹는 대안은 상시 줄의 폭을 올린다(README 5: QPushButton 최소 폭은 글자
    폭이라 헤더 한 줄에 버튼을 더할 때마다 독 최소 폭이 그만큼 오른다) -
    그래서 자기 줄에 둔다. 자기 줄은 폭 중립이다.

예시 원본과 다른 점 (근사)
    예시(docs/ui_pass2_refs/3.png)의 내비는 본문 **위에 떠 있는** 알약이다.
    여기서는 레이아웃의 한 줄로 둔다. 독 안에서 겹쳐 띄우려면 부모 위에
    수동 geometry 를 얹어야 하고, 그 코드는 독 크기가 바뀔 때마다 다시
    맞춰야 하는 경로를 하나 더 만든다. 모양(알약 면, 고른 칸만 밝은 알약)은
    그대로 받고 띄우는 것만 접었다 - U3·U8 의 "근사 수용" 과 같은 선이다.

배타 선택의 집행자는 `QButtonGroup` 이다. 체크 상태를 손으로 맞추면 두 칸이
동시에 켜진 상태가 날 수 있고, 그러면 "지금 어디" 가 거짓이 된다.

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog, 중첩
이벤트 루프. Qt import 는 전부 qgis.PyQt 셰임 경로로 한다(설계 7-4).
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

# 칸 키. 독이 이 문자열로 분기하고 하네스가 같은 값을 읽는다.
NAV_CHAT = "chat"
NAV_KEYS = "keys"
NAV_STATS = "stats"

# (키, 버튼 문구, objectName, 툴팁). 문구는 사용자 말이다 - 내부 용어를
# 쓰지 않는다(docs/6 U15). 헤더 아이콘의 [공공 API 키] 와 같은 것을 가리키되
# 한 줄에 셋이 들어가야 해서 짧은 말로 적는다.
NAV_ITEMS = (
    (NAV_CHAT, "대화", "UpwiseChatNavChat",
     "대화 내용만 봅니다. 키 패널과 통계 칸을 내립니다."),
    (NAV_KEYS, "키", "UpwiseChatNavKeys",
     "공공 API 키 패널을 엽니다. 헤더의 [공공 API 키] 와 같은 칸입니다."),
    (NAV_STATS, "통계", "UpwiseChatNavStats",
     "사용량과 수집 통계를 봅니다."),
)

# 알약 안쪽 여백과 버튼 사이 간격(px). 글꼴 크기는 고정하지 않는다
# (설계 7-3) - 여백만 박는다.
NAV_PADDING = 3
NAV_SPACING = 3


class BottomNav(QWidget):
    """칸 셋을 가리키는 알약 한 줄.

    Signals:
        selected(str): 사용자가 칸을 눌렀다. 값은 NAV_* 중 하나다.
            프로그램이 `set_current` 로 맞춘 경우에는 **발화하지 않는다** -
            독이 자기가 바꾼 상태를 자기 슬롯으로 되받으면 재진입이 된다.
    """

    selected = pyqtSignal(str)

    def __init__(self, parent=None):
        """버튼 셋을 배타 그룹으로 묶어 만든다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatBottomNav")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(NAV_PADDING, NAV_PADDING,
                                  NAV_PADDING, NAV_PADDING)
        layout.setSpacing(NAV_SPACING)

        self._buttons = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, text, name, tip in NAV_ITEMS:
            button = QPushButton(text, self)
            button.setObjectName(name)
            button.setCheckable(True)
            button.setToolTip(tip)
            button.setCursor(Qt.PointingHandCursor)
            button.setFlat(True)
            # `clicked` 는 사용자가 누른 경우에만 온다. `toggled` 로 이으면
            # set_current 가 세운 체크까지 시그널이 되어 독이 자기 변경을
            # 되받는다(README 5 PyQt `clicked` 함정과 같은 축의 주의).
            button.clicked.connect(
                lambda _checked=False, k=key: self._on_clicked(k))
            self._group.addButton(button)
            layout.addWidget(button, 1)
            self._buttons[key] = button
        layout.addStretch(0)
        self._current = NAV_CHAT
        self._buttons[NAV_CHAT].setChecked(True)

    def _on_clicked(self, key):
        """사용자 누름. 현재 칸을 기억하고 시그널을 올린다.

        같은 칸을 다시 눌러도 발화한다 - 헤더 토글로 칸이 바뀐 뒤 내비를
        다시 누르는 경로에서 "이미 그 칸" 으로 보이지만 실제 화면은 다를 수
        있기 때문이다.

        Returns:
            str: 고른 칸 키.
        """
        self._current = key
        self.selected.emit(key)
        return key

    def set_current(self, key):
        """프로그램 쪽에서 칸을 맞춘다. 시그널은 올리지 않는다.

        Args:
            key: NAV_* 중 하나. 모르는 값이면 아무것도 하지 않는다.

        Returns:
            str: 맞춘 뒤의 현재 칸.
        """
        button = self._buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        if button is not None:
            self._current = key
        return self._current

    def current(self):
        """지금 칸. 하네스가 읽는 창구다."""
        return self._current

    def button(self, key):
        """칸 버튼 하나. 하네스가 실제 누름을 흉내 낼 때 쓴다."""
        return self._buttons.get(key)

    def stats(self):
        """하네스가 읽는 한 줄 요약."""
        return {
            "current": self._current,
            "exclusive": bool(self._group.exclusive()),
            "keys": [k for k, _t, _n, _p in NAV_ITEMS],
            "checked": [k for k, b in sorted(self._buttons.items())
                        if b.isChecked()],
            "texts": {k: b.text() for k, b in self._buttons.items()},
        }
