"""전사 영역 위젯 (설계 7-1 [4], 4-2, 4-4).

무엇을 그리는가
    사용자 말풍선, 모델 텍스트 블록, 생각 블록(접힘), 도구 카드(접힘),
    턴 구분선, 로컬 공지(백엔드 종료 등). 그릴 재료는 전부 TurnMachine 이
    들고 있고 이 위젯은 그것을 읽어 위젯으로 옮긴다.

어떻게 그리는가 - 증분이다
    sync() 는 50 ms 드레인마다 불린다. 그래서 전사를 매번 다시 만들지 않고,
    블록 키로 위젯을 찾아 **바뀐 것만** 갱신한다. 텍스트 블록은 스트리밍으로
    자라기만 하므로, 이미 그린 접두를 넘는 부분만 커서로 삽입한다.

    왜 QLabel 이 아닌가 (측정으로 고른 것이다)
        같은 조건(앞선 블록 40개, 델타 2,500건, 틱당 10건, 최종 37,500자)에서
        QLabel.setText(전문) 은 틱당 평균 25.0 ms / 최대 44.5 ms 였다. 드레인
        간격이 50 ms 이므로 예산을 거의 다 쓴다. QTextEdit 증분 삽입 + 높이
        추종은 평균 9.2 ms / 최대 29.2 ms 였다. 그래서 텍스트는 QTextEdit 다.
        (측정 2026-10-10, QT_QPA_PLATFORM=offscreen, QGIS 3.44.14 번들 Qt 5.15.13)

    사용자 말풍선과 공지는 한 번 쓰고 바뀌지 않으므로 QLabel 이다.

하단 고정 추적 (0.1.3)
    스트리밍으로 전사가 자라면 화면은 최신 출력을 따라가야 한다. 다만 사용자가
    위를 올려 읽고 있을 때 끌어내리면 더 나쁘다. 그래서 "바닥에 붙어 있었는가"
    를 상태로 들고(ChatView._pinned), 스크롤 범위가 실제로 바뀌는 순간
    (verticalScrollBar().rangeChanged)에만 다시 내린다. 위젯을 끼운 직후의
    maximum() 은 아직 옛 값이라 그 자리에서 내려도 뒤처진다(ChatView.__init__
    주석에 기전).

상한 (설계 4-4)
    블록 위젯은 최근 200개만 유지하고 그 위는 접는다. 전체는 session_*.jsonl
    에 남아 있다. 도구 결과는 protocol 이 이미 4,000자로 자른 사본을 주고,
    잘린 경우 "전문 보기" 로 원문을 임시 파일에 열어 준다.

레다크션 (0.2.1, 설계 docs/2 5-4 적용 지점 2)
    독이 소유하는 레다크터를 `set_redactor()` 로 받아, 말풍선/공지/텍스트
    블록/도구 카드(인자·결과·"전문 보기" 원문)를 그리기 **전에** 통과시킨다.
    치환은 값 완전 일치 부분문자열만 바꾸고 비가역이다. 이미 그려진 행에는
    소급 적용하지 않는다 - append-only 규약(위 상한 절)을 깨기 때문이다.

    비소급이므로 **화면 밖으로 사본을 내보내는 경로에는 따로 관문이 있다**.
    내보내기는 쓰기 직전 한 번(dock._redacted_export), 복사는 클립보드 쓰기
    직전 한 번(_set_clipboard)이다. 0.2.3 에는 복사 쪽 관문이 없어서 레다크터
    부착 전에 그려진 행의 키가 클립보드로 나갔다(0.2.4 에서 닫았다).

    0.2.4 가 닫은 것은 **우리가 만든** 복사 경로 셋이었고, 자식 위젯의 Qt
    표준 우클릭 메뉴가 하나 남아 있었다 - 그 Copy 는 클립보드로 직행한다
    (V32-A01 실측: 키 원문 1건, 관문 카운터 공백). 0.3.0 에서 ContextMenu 를
    항상 소비해 표준 메뉴를 띄우지 않고, 글자 선택 복사를 우리 메뉴
    (_show_char_menu)로 받아 같은 관문에 태운다. 이로써 "모든 클립보드 쓰기가
    한 관문을 지난다" 가 우클릭 축까지 성립한다.

복사 경로 셋 (0.2.3, 사용자 요청)
    1. 칸 단위   행마다 우상단 [복사] 버튼. 그 칸의 **보이는 글**만 담는다.
    2. 범위      전사를 가로질러 드래그하면 걸친 **행 범위**가 잡히고
                 Ctrl+C 또는 우클릭 메뉴로 그 범위를 담는다. 위젯 하나를
                 벗어나지 않는 드래그는 종전처럼 글자 단위 선택이다.
    3. 전체      독 헤더의 [내보내기]. ui 가 아니라 dock 이 맡는다.

    왜 범위 선택을 이렇게 하는가 (위젯을 바꾸지 않은 근거)
        Qt 의 글자 단위 선택은 **문서 하나 안에서만** 이어진다. 전사가 행마다
        독립 위젯(QLabel, QTextEdit, 카드 QFrame)이라 위젯 경계를 넘는 글자
        선택은 구조적으로 불가능하다. 하나의 QTextEdit 로 합치면 가능해지지만
        그 대가가 크다 - 접히는 도구 카드와 생각 블록(설계 4-2)이 사라지고,
        증분 삽입 측정(위 docstring)과 행 상한 걷어내기(설계 4-4), 하단 고정
        추종(V28-P14)이 전부 다시 설계된다. 그래서 **행 범위**를 선택 단위로
        둔다. 사용자가 원하는 범위를 드래그로 집고 복사하는 목적은 달성되고,
        한 행 안에서는 기존 글자 선택이 그대로 남는다.

    클립보드에 올라가는 것은 **화면에 보이는 글**이다 - 즉 레다크션을 이미
    통과한 문자열이다(위 레다크션 절). 원문을 따로 들고 있다가 복사하는
    경로는 만들지 않는다.

줄바꿈과 가로 넘침 (U13, 0.3.x UI 패스 2차)
    전사 스크롤 영역은 가로 스크롤바를 아예 꺼 둔다(ChatView.__init__). 그래서
    본문 폭이 뷰포트보다 넓어지면 넘친 글은 **읽을 수단이 없이** 잘린다. 폭을
    미는 주범은 위젯의 wrap 설정이 아니라 **레이아웃 최소 폭**이었다.

        QLabel 은 wordWrap 을 켜도 minimumSizeHint().width() 가 "가장 긴
        낱말" 폭을 돌려준다(Qt qSmartMinSize 가 Preferred 정책에서 그 값을
        최소 폭으로 쓴다). 사용자가 긴 경로나 URL 을 한 덩이로 보내면 그
        한 낱말이 전사 본문의 최소 폭이 되고, 라벨은 제 폭을 받았으므로
        줄바꿈할 이유가 없다 - 사용자 눈에는 "줄바꿈이 안 되고 좌우 스크롤도
        없는" 상태로 보인다. 그래서 줄바꿈 라벨은 minimumWidth 를 1 로 박아
        본문이 뷰포트까지 줄게 한다(WRAP_LABEL_MIN_W).

    일반 텍스트 블록(QTextEdit)은 낱말 중간에서도 끊어 접는다
    (WrapAtWordBoundaryOrAnywhere). Qt 기본값이 이미 그렇지만 명시한다 -
    기본값이 QTextEdit 과 QTextDocument 에서 다르고, 끊김 정책은 이 위젯의
    계약이라 기본값에 기대지 않는다.

    코드 블록과 JSON 은 접지 않는다. 들여쓰기와 줄 경계가 뜻을 나르므로 접으면
    읽기 더 어려워진다. 그래서 그 블록만 NoWrap + **블록 안쪽 가로 스크롤**
    이다(GrowingTextView(preformatted=True)). 전사 전체를 좌우로 미는 것과
    다르다 - 넘치는 블록 하나만 자기 안에서 밀린다.

도구 카드 기본 접힘 (U14, 0.3.x UI 패스 2차)
    카드 머리(도구 이름과 상태) 한 줄만 기본으로 보인다. 인자 미리보기는
    접힘 영역 **안으로** 옮겼다 - 그전에는 미리보기가 접힘 밖에 있어서, 턴마다
    도구 호출 JSON 200자가 전사를 채웠다(사용자 피드백 2026-10-12). 바꾼 것은
    표시 계층뿐이고 jsonl 감사 경로와 레다크션 관문은 그대로다.

화면 비우기 (U11, 0.3.x UI 패스 2차)
    clear_transcript() 는 **화면만** 비운다. 상태머신도 CLI 세션도 건드리지
    않는다. 그런데 sync() 는 상태머신을 다시 읽으므로, 비운 직후 드레인이
    같은 블록을 새 행으로 다시 그린다. 그래서 비운 키를 `_cleared_keys` 에
    적어 두고 그 키는 다시 만들지 않는다. 이미 쓴 내보내기 파일과 jsonl 은
    디스크에 그대로다 - 비우기는 지우기가 아니다.

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog, 중첩 이벤트 루프.
우클릭 메뉴는 `QMenu.popup()` 으로 띄운다 - `exec_()` 는 중첩 이벤트 루프라
금지 목록이고 popup 은 비차단이다.
Qt import 는 전부 qgis.PyQt 셰임 경로로 한다(설계 7-4).

설계 정본: docs/1.mvp_design_v1.md 4-2, 4-3, 4-4, 7-1 / docs/2 5-4
"""

import json
import tempfile
import time
from pathlib import Path

from qgis.PyQt.QtCore import (
    QEvent,
    QPoint,
    QRect,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from qgis.PyQt.QtGui import (
    QDesktopServices,
    QKeySequence,
    QTextBlockFormat,
    QTextCursor,
    QTextOption,
)
from qgis.PyQt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QRubberBand,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..backend import protocol
from ..backend import transcript as transcript_mod
from . import theme as theme_mod

# 전사에 위젯으로 유지하는 블록 수 상한(설계 4-4). protocol 의 값을 그대로 쓴다.
BLOCK_WIDGET_MAX = protocol.TRANSCRIPT_BLOCK_MAX

# 도구 카드 머리에 항상 보이는 인자 미리보기 길이(설계 4-2 tool_use 행).
ARGS_PREVIEW_CHARS = 200

# 전사 레이아웃 여백과 행 간격(px). 고정 px 는 여백뿐이고 글꼴은 QGIS 배율을
# 그대로 따른다(설계 7-3). 0.2.2: 행 사이를 6 -> 9 로 벌렸다. 사용자 띠와
# 응답 블록이 붙어 있으면 띠 색만으로는 경계가 안 읽힌다.
VIEW_MARGIN = 8
ROW_SPACING = 9

# 본문 행간(%). 0.2.2 심미 패스. 글꼴 **크기**는 건드리지 않고 줄 간격만
# 비례로 벌린다 - 한글 본문이 기본 행간에서 빽빽하게 읽힌다.
LINE_HEIGHT_PCT = 125

# 턴 구분선 두께(px).
SEPARATOR_PX = 1

# 위험 표시 테두리색. 거부/오류 카드에만 쓴다(설계 4-2 tool_result 행의 "빨간
# 테두리"). 브랜드 팔레트 확정은 S7 범위이므로 여기서는 중립적인 빨강 하나만
# 쓰고 독 전역 스타일시트는 건드리지 않는다(설계 7-3).
ERROR_BORDER_COLOR = "#c0392b"

# 사용자 말풍선 앞머리. 띠 색과 함께 "누가 말했는가" 를 두 겹으로 준다 -
# 색만으로 구분하면 색각 이상이나 흑백 캡처에서 사라진다.
USER_PREFIX = "나: "

# 전사가 "바닥에 붙어 있다" 고 볼 임계(px). 스크롤바 value 가 maximum 에서 이
# 값 안에 들어와 있으면 하단 고정 모드다. 0 으로 두면 줄 높이 반올림이나 1 px
# 떨림만으로도 고정이 풀리고, 크게 두면 사용자가 조금 올려 읽는 것을 바닥으로
# 오인해 끌어내린다. 4 px 은 S4 때부터 _at_bottom() 이 쓰던 값이고 0.1.3 에서
# 이름을 붙여 상수로 올렸다(값 변경 없음).
BOTTOM_EPSILON_PX = 4

# 접힘 머리 툴팁(0.2.2). 모달을 못 쓰므로 안내는 그 자리에 둔다.
COLLAPSE_TIP = "누르면 접고 펼칩니다."

# ----------------------------------------------------------------------
# U13 줄바꿈 (0.3.x UI 패스 2차)
# ----------------------------------------------------------------------

# 줄바꿈 라벨에 박는 최소 폭(px). 0 이 아니라 1 인 이유가 있다 - Qt 의
# qSmartMinSize 는 `minimumSize().width() > 0` 일 때만 그 값으로 minimumSizeHint
# 를 덮는다. 0 을 주면 덮지 않고 "가장 긴 낱말" 폭이 그대로 최소 폭이 된다
# (모듈 docstring 의 U13 절). 1 px 은 실질적으로 "최소 폭 없음" 이다.
WRAP_LABEL_MIN_W = 1

# ----------------------------------------------------------------------
# U11 화면 비우기 (0.3.x UI 패스 2차)
# ----------------------------------------------------------------------

# 교체 표시 공지의 키 접두. 같은 키로 다시 들어온 공지는 옛 행을 걷어내고
# **맨 아래에** 새로 붙는다 - 제자리에서 글자만 갈면 위로 밀려 올라간 줄이
# 조용히 바뀌어 사용자가 새 결과를 못 본다.
STATUS_NOTICE_KEY = "status"

# ----------------------------------------------------------------------
# 0.2.3 복사 경로 문구와 치수
# ----------------------------------------------------------------------

# 칸 복사 버튼. 글자만 쓴다 - 아이콘 자산을 늘리지 않고, 글자는 QGIS 배율을
# 따라가므로 HiDPI 에서도 눌릴 크기가 유지된다(설계 7-3).
CELL_COPY_TEXT = "복사"
CELL_COPIED_TEXT = "복사됨"
CELL_COPY_TIP = "이 칸에 보이는 글을 클립보드로 복사합니다."

# 복사 피드백을 되돌리는 시간(ms). 모달도 상태 바도 쓰지 않으므로 버튼 글자가
# 유일한 확인 신호다. 0.9 s 는 사용자가 읽고 놓치지 않을 하한으로 잡았다.
COPY_FEEDBACK_MS = 900

# 내용 위젯과 복사 버튼 사이 간격(px).
CELL_BUTTON_SPACING = 4

# 0.2.4: 복사가 레다크션 관문에서 막혔을 때 독이 안내 바에 적을 사유. 문구를
# 여기 두는 이유는 막는 자리가 여기(ChatView._set_clipboard)라서다 - 독은
# 받은 사유를 그대로 옮기고 자기 말로 다시 쓰지 않는다.
#
# U15(0.3.x UI 패스 2차): dock.EXPORT_REDACT_FAIL 과 **같은 문장 가족**이라
# 함께 바꿨다. 둘 중 하나만 쉬운 한글로 가면 같은 바에 두 어휘가 번갈아 뜬다.
COPY_REDACT_FAIL = "민감정보 가림 처리에 실패해 클립보드에 쓰지 않았습니다"

# 범위 선택 우클릭 메뉴 문구.
RANGE_COPY_TEXT = "선택한 범위 복사"

# 범위가 없을 때(한 행 안 글자 선택) 우클릭 메뉴 문구. 0.3.0 에서 생겼다 -
# 그전에는 이 자리를 위젯 표준 메뉴에 넘겼고 그 Copy 가 관문을 비켰다
# (V32-A01). 문구가 따로인 이유는 담기는 것이 다르다는 것을 알리기 위함이다.
CHAR_COPY_TEXT = "선택한 글자 복사"

# 범위 복사에서 행 사이에 넣는 구분. 빈 줄 하나를 둬서 붙여 넣은 글에서도
# 행 경계가 남는다.
RANGE_JOIN = "\n\n"

# 도구 상태별 표시 문구. ToolSearch 는 따로 구분한다(설계 4-2 ToolSearch 행).
STAGE_LABELS = {
    "searching_tools": "도구 찾는 중",
    "running": "실행 중",
}


def _format_args(tool_input):
    """도구 인자 dict 를 사람이 읽을 JSON 문자열로 만든다.

    한글이 \\uXXXX 로 깨지지 않게 ensure_ascii=False 다. 직렬화가 안 되는 값이
    섞여 있어도 카드가 안 그려지는 일은 없어야 하므로 default=str 로 떨어뜨린다.
    """
    if not tool_input:
        return "{}"
    try:
        return json.dumps(tool_input, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(tool_input)


class GrowingTextView(QTextEdit):
    """내용 높이를 따라가는 읽기 전용 텍스트 뷰.

    세로 스크롤은 전사 영역 하나만 쓰고 이 위젯은 세로 스크롤바를 갖지 않는다.
    그래서 높이를 문서 높이에 맞춘다. 갱신은 증분이다(모듈 docstring 의 측정
    참조).

    가로는 두 모드다 (U13).
        일반 텍스트     낱말 중간에서도 끊어 접는다. 가로 스크롤바 없음.
        preformatted   접지 않고 **이 블록 안에서만** 가로로 스크롤한다.
                       코드 블록과 JSON 은 줄 경계가 뜻을 나르기 때문이다.
    """

    def __init__(self, parent=None, preformatted=False):
        """읽기 전용, 높이 고정 정책으로 만든다.

        Args:
            parent: 부모 위젯.
            preformatted: 코드/JSON 블록인가(U13). True 면 접지 않고 블록
                안쪽 가로 스크롤을 켠다.
        """
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._preformatted = bool(preformatted)
        if self._preformatted:
            # 접지 않는다. 넘친 줄은 이 블록의 가로 스크롤바로 읽는다 -
            # 전사 전체를 좌우로 미는 것이 아니라 블록 하나만 밀린다.
            self.setLineWrapMode(QTextEdit.NoWrap)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.setLineWrapMode(QTextEdit.WidgetWidth)
            # 낱말 경계가 없는 긴 덩이(경로, URL, base64)도 끊어 접는다.
            # WordWrap 만으로는 그 덩이가 위젯 밖으로 삐져 나가고 가로
            # 스크롤바가 없어 읽을 수단이 사라진다(모듈 docstring U13 절).
            self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rendered = ""
        self._fixed_height = -1
        self._apply_line_height()

    def is_preformatted(self):
        """코드/JSON 모드인가(U13). 검증 하네스가 읽는다."""
        return self._preformatted

    def _apply_line_height(self):
        """문서 전체에 비례 행간을 건다(0.2.2).

        글꼴 크기는 건드리지 않는다(설계 7-3). 커서로 블록 서식을 걸어 두면
        뒤에 삽입되는 블록이 그 서식을 물려받으므로, 증분 삽입 경로에서는
        다시 부를 필요가 없다. setPlainText 는 문서를 갈아 끼우므로 그
        경로에서만 다시 부른다.
        """
        fmt = QTextBlockFormat()
        fmt.setLineHeight(LINE_HEIGHT_PCT, QTextBlockFormat.ProportionalHeight)
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)

    def rendered_text(self):
        """지금 화면에 들어가 있는 문자열. 중복 검사와 검증에 쓴다."""
        return self._rendered

    def set_text_incremental(self, text):
        """바뀐 부분만 반영한다.

        이미 그린 문자열이 새 문자열의 접두면 꼬리만 커서로 삽입한다. 아니면
        전문을 다시 넣는다(권위 텍스트가 스트리밍 버퍼와 다른 경우).

        Returns:
            bool: 실제로 갱신했는가.
        """
        text = text if isinstance(text, str) else ("" if text is None else str(text))
        if text == self._rendered:
            return False
        if self._rendered and text.startswith(self._rendered):
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(text[len(self._rendered):])
        else:
            self.setPlainText(text)
            # 문서가 갈아 끼워졌다. 행간 서식을 다시 건다.
            self._apply_line_height()
        self._rendered = text
        self._fit_height()
        return True

    def _fit_height(self):
        """문서 높이에 맞춰 고정 높이를 다시 잡는다.

        값이 바뀔 때만 setFixedHeight 를 부른다. 매번 부르면 resizeEvent 가
        다시 들어와 레이아웃이 왕복한다.

        preformatted 모드에서는 두 가지가 다르다(U13). (1) textWidth 를 -1 로
        둔다 - 뷰포트 폭을 박으면 Qt 가 그 폭에서 접어 버려 NoWrap 이 무의미
        해진다. (2) 가로 스크롤바가 필요하면 그 높이를 더한다. 높이를 고정해
        두는 위젯이라 더하지 않으면 스크롤바가 마지막 줄을 덮는다.
        """
        doc = self.document()
        if self._preformatted:
            doc.setTextWidth(-1)
        else:
            doc.setTextWidth(max(1, self.viewport().width()))
        want = int(doc.size().height()) + 2 * int(doc.documentMargin()) + 2
        if self._preformatted and doc.idealWidth() > self.viewport().width():
            want += self.horizontalScrollBar().sizeHint().height()
        if want != self._fixed_height:
            self._fixed_height = want
            self.setFixedHeight(want)

    def resizeEvent(self, event):  # noqa: N802 - Qt 가 요구하는 고정 이름
        """폭이 바뀌면 줄바꿈이 바뀌므로 높이를 다시 잡는다."""
        super().resizeEvent(event)
        self._fit_height()


class CollapsibleSection(QWidget):
    """제목 버튼 하나로 본문을 접고 펴는 영역.

    모달 없이 상세를 숨기는 수단이다. 생각 블록과 도구 카드가 쓴다.
    """

    def __init__(self, title, parent=None, expanded=False, object_name=""):
        """
        Args:
            title: 제목 버튼 문구.
            parent: 부모 위젯.
            expanded: 처음에 펴 둘지. 생각 블록과 도구 카드는 둘 다 접힘이다
                (설계 4-2 thinking_delta 행, tool_use 행).
            object_name: 제목 버튼의 objectName. 하네스가 찾아 쓴다.
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._button = QToolButton(self)
        self._button.setText(title)
        if object_name:
            self._button.setObjectName(object_name)
        self._button.setCheckable(True)
        self._button.setChecked(bool(expanded))
        self._button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._button.setAutoRaise(True)
        # 0.2.2: 접힘 머리는 캡션 위계다. 화살표만으로는 "눌러서 편다" 가
        # 안 읽혀서 툴팁으로도 말한다(모달을 못 쓰므로 안내는 제자리에).
        theme_mod.set_role(self._button, theme_mod.ROLE_SECTION)
        self._button.setToolTip(COLLAPSE_TIP)
        self._button.setCursor(Qt.PointingHandCursor)
        self._button.toggled.connect(self._on_toggled)
        layout.addWidget(self._button)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(12, 0, 0, 0)
        self._body_layout.setSpacing(4)
        self._body.setVisible(bool(expanded))
        layout.addWidget(self._body)

    def set_title(self, title):
        """제목을 바꾼다. 도구 상태가 바뀔 때 쓴다."""
        if self._button.text() != title:
            self._button.setText(title)

    def title(self):
        """지금 제목 문구."""
        return self._button.text()

    def add_body_widget(self, widget):
        """본문에 위젯을 더한다."""
        self._body_layout.addWidget(widget)

    def is_expanded(self):
        """펴져 있는가. 검증 하네스가 읽는다."""
        return self._button.isChecked()

    def _on_toggled(self, checked):
        """화살표 방향과 본문 가시성을 맞춘다."""
        self._button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self._body.setVisible(bool(checked))


class ToolCardWidget(QFrame):
    """도구 호출 1건의 카드(설계 4-2 tool_use/tool_result 행).

    기본 상태에서는 머리 한 줄(도구 이름과 상태)만 보인다(U14). 펴면 인자 200자
    미리보기, 인자 전문, 결과가 나온다. 결과는 protocol 이 4,000자로 자른
    사본이고 잘렸으면 "전문 보기" 로 원문을 임시 파일에 연다(설계 4-4).
    """

    def __init__(self, parent=None, redactor=None):
        """빈 카드를 만든다. 내용은 update_from() 이 채운다.

        Args:
            parent: 부모 위젯.
            redactor: callable(str) -> str (0.2.1). 인자/결과/원문을 그리기
                전에 통과시킨다. None 이면 치환하지 않는다.
        """
        super().__init__(parent)
        self._redact = redactor
        # S7. 독 qss 가 이 이름으로 카드 배경과 테두리를 건다(설계 7-3 "카드
        # 배경" 행). 오류 테두리는 update_from 이 더 구체적인 선택자로 덮는다.
        self.setObjectName("UpwiseChatToolCard")
        self.setFrameShape(QFrame.StyledPanel)
        self._error_style = False
        self._raw_body = ""
        self._full_args = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(3)

        self._section = CollapsibleSection(
            "", self, expanded=False, object_name="UpwiseChatToolCardTitle")
        layout.addWidget(self._section)

        # 인자 미리보기. U14 에서 접힘 영역 **안으로** 옮겼다 - 그전에는 접힘
        # 밖(카드 레이아웃 직속)이어서 기본 상태에서도 인자 JSON 200자가
        # 보였고, 도구를 여러 번 부르는 턴에서 전사가 그것으로 채워졌다.
        # 위젯과 objectName(qss 규칙)과 preview_text() 창구는 그대로 둔다.
        self._preview = QLabel("", self)
        self._preview.setObjectName("UpwiseChatToolCardPreview")
        self._preview.setWordWrap(True)
        # U13: 긴 경로 한 덩이가 카드의 최소 폭을 밀지 않게 한다.
        self._preview.setMinimumWidth(WRAP_LABEL_MIN_W)
        self._preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._section.add_body_widget(self._preview)

        # U13: 인자와 결과는 JSON 과 도구 출력 원문이다. 접으면 들여쓰기와 줄
        # 경계가 깨져 읽기 더 어려우므로 블록 안쪽 가로 스크롤로 간다.
        self._args_view = GrowingTextView(self, preformatted=True)
        self._section.add_body_widget(self._args_view)
        self._result_view = GrowingTextView(self, preformatted=True)
        self._section.add_body_widget(self._result_view)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self._full_button = QPushButton("전문 보기", row)
        self._full_button.setToolTip("잘리지 않은 원문을 임시 파일로 연다")
        self._full_button.clicked.connect(self._on_open_full)
        self._full_button.setVisible(False)
        row_layout.addWidget(self._full_button)
        row_layout.addStretch(1)
        self._section.add_body_widget(row)

    def set_redactor(self, redactor):
        """레다크터를 붙인다(0.2.1). 카드 생성 후에도 바꿀 수 있다."""
        self._redact = redactor

    def _redacted(self, text):
        """레다크터가 있으면 치환한다. 실패해도 그리기를 멈추지 않는다."""
        if self._redact is None:
            return text
        try:
            return self._redact(text)
        except Exception:  # noqa: BLE001 - 치환 실패가 전사를 비우게 하지 않는다
            return text

    def update_from(self, card):
        """ToolCard 상태를 위젯에 반영한다.

        Args:
            card: machine.ToolCard.

        Returns:
            bool: 무언가 바뀌었는가.
        """
        changed = False
        self._section.set_title(self._title_for(card))

        # 0.2.1: 설계 docs/2 5-4 적용 지점 2. 도구 카드가 인자 JSON 을 그대로
        # 보여 주므로(L5) 인자/결과/원문 셋 다 치환을 통과시킨다.
        args_text = self._redacted(_format_args(card.tool_input))
        if args_text != self._full_args:
            self._full_args = args_text
            preview = args_text[:ARGS_PREVIEW_CHARS]
            if len(args_text) > ARGS_PREVIEW_CHARS:
                preview += " ..."
            self._preview.setText(preview)
            self._args_view.set_text_incremental("인자\n" + args_text)
            changed = True

        if card.closed:
            body = self._redacted(card.result_display or "")
            if card.result_truncated:
                body += "\n... (%d자에서 잘림. 전문 보기를 누르세요)" % len(body)
            if self._result_view.set_text_incremental("결과\n" + body):
                changed = True
            # "전문 보기" 가 쓰는 원문도 치환본을 들고 있는다. 임시 파일은
            # 사용자 디스크에 남으므로 전사와 같은 기준이어야 한다.
            self._raw_body = self._redacted(card.result_raw or "")
            # 잘린 결과와 오류 결과는 원문을 열 수 있게 둔다. 거부 사유 전문이
            # 오류 본문으로 오기 때문이다(설계 3-5 항목 3).
            want_full = bool(card.result_truncated or card.is_error)
            if self._full_button.isVisible() != want_full:
                self._full_button.setVisible(want_full)
                changed = True

        want_error = bool(card.is_error) or bool(card.denied)
        if want_error != self._error_style:
            self._error_style = want_error
            # 스타일시트는 이 카드 위젯에만 건다. 독 전역이나 QGIS 전역에
            # 적용하지 않는다(설계 7-3).
            #
            # 선택자가 `QFrame#UpwiseChatToolCard` 인 이유(S7, V28-A33 정정):
            # Qt 는 조상 스타일시트와 자기 것을 합치지만, 충돌할 때 이기는 것은
            # **위젯 자신의 styleSheet** 다. 조상(독 qss)이 `#UpwiseChatToolCard`
            # 로 카드 테두리를 걸고 있어도 자기 규칙이 덮는다. 즉 형 선택자
            # (`QFrame`)만 써도 오류 테두리는 그려진다 - verifier 15/15 실측.
            # ID 를 함께 적는 것은 의도를 드러내는 명시성 취향이고, 덮어쓰기의
            # 필요조건이 아니다. (이전 주석은 "조상 ID 규칙이 형 선택자를
            # 이긴다" 고 적었는데 실측과 반대였다.)
            # 0.2.2: 왼쪽 강조선을 3 px 로 둬서 접힌 카드 더미에서도 어느
            # 카드가 거부/오류인지 훑어 읽힌다. 테두리 **색**은 그대로다
            # (하네스 16 W7c 가 이 값을 실픽셀로 잡고 있다).
            self.setStyleSheet(
                "QFrame#UpwiseChatToolCard {"
                " border: 1px solid %s; border-left: 3px solid %s; }"
                % (ERROR_BORDER_COLOR, ERROR_BORDER_COLOR)
                if want_error
                else ""
            )
            changed = True
        return changed

    # ------------------------------------------------------------------
    # 조회 (검증 하네스가 읽는다)
    # ------------------------------------------------------------------

    def preview_text(self):
        """인자 미리보기 문구. U14 부터 펼쳤을 때만 보인다(값은 그대로 계산된다)."""
        return self._preview.text()

    def args_text(self):
        """펼쳤을 때 보이는 인자 전문 문구."""
        return self._args_view.rendered_text()

    def result_text(self):
        """펼쳤을 때 보이는 결과 문구. cat -n 접두가 제거된 사본이다."""
        return self._result_view.rendered_text()

    def title_text(self):
        """카드 제목(도구 이름과 상태)."""
        return self._section.title()

    def is_expanded(self):
        """카드가 펴져 있는가. 기본은 접힘이다."""
        return self._section.is_expanded()

    def full_button_visible(self):
        """"전문 보기" 버튼을 띄우기로 했는가.

        isVisible() 은 카드가 접혀 있으면(본문이 숨어 있으면) 거짓이 된다.
        여기서 알고 싶은 것은 버튼 자체의 표시 결정이므로 isHidden() 의 반대다.
        """
        return not self._full_button.isHidden()

    def has_error_style(self):
        """거부/오류 테두리가 걸려 있는가."""
        return self._error_style

    def copy_text(self):
        """이 카드를 한 덩이로 복사할 때의 글(0.2.3).

        카드는 접혀 있어도 제목과 인자 미리보기가 보이고, 펴면 인자 전문과
        결과가 보인다. 복사는 **접힘 상태와 무관하게 전문**을 담는다 - 접혀
        있다는 것은 지금 읽지 않는다는 뜻이고 복사는 나중에 읽으려는 행동이다.
        세 조각 모두 이미 레다크션을 통과한 사본이다.

        Returns:
            str: 제목, 인자 전문, 결과를 이어 붙인 글.
        """
        parts = [self.title_text()]
        for body in (self._args_view.rendered_text(),
                     self._result_view.rendered_text()):
            if body:
                parts.append(body)
        return "\n\n".join(p for p in parts if p)

    def _title_for(self, card):
        """카드 제목. 상태를 사람 말로 적는다."""
        if card.denied:
            state = "거부됨"
        elif getattr(card, "excluded", False):
            # 제외는 거부가 아니다. 사용자가 "허용" 으로 풀 수 없는 상태이므로
            # 제목에서도 갈라 쓴다(설계 3-5).
            state = "포스처에 없음"
        elif card.closed and card.is_error:
            state = "오류"
        elif card.closed:
            state = "완료"
        else:
            state = STAGE_LABELS.get(card.stage, "실행 중")
        return "도구 · %s · %s" % (card.name or "(이름 없음)", state)

    def _on_open_full(self):
        """원문을 임시 파일에 쓰고 운영체제 기본 프로그램으로 연다(설계 4-4).

        모달 대화상자를 쓰지 않는 유일한 "전문 보기" 경로다.
        """
        if not self._raw_body:
            return
        path = Path(tempfile.gettempdir()) / (
            "upwise_chat_tool_result_%s.txt" % time.strftime("%y%m%d_%H%M%S")
        )
        try:
            path.write_text(self._raw_body, encoding="utf-8")
        except OSError:
            # 쓰기 실패가 독을 멈추게 하지 않는다. 결과는 jsonl 에도 있다.
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class TranscriptCell(QWidget):
    """행 하나를 감싸는 칸. 내용 위젯 + 우상단 복사 버튼 (0.2.3).

    왜 감싸는가
        복사 버튼을 행 위젯 **안에** 넣으려면 말풍선(QLabel), 응답 블록
        (QTextEdit), 도구 카드(QFrame) 세 종류를 각각 고쳐야 하고, 그 중
        QLabel 과 QTextEdit 는 레이아웃이 없는 위젯이라 버튼을 얹으면 글과
        겹친다. 감싸는 칸 하나를 두면 세 종류가 같은 자리에 같은 버튼을 갖고,
        기존 위젯의 objectName 과 qss 규칙은 그대로다.

    왜 겹치지 않고 오른쪽에 두는가
        겹쳐 띄우면(절대 배치) 긴 글의 첫 줄을 버튼이 가린다. 오른쪽 열에
        상단 정렬로 두면 가리는 글이 없고, 버튼 폭만큼 본문이 좁아진다.

    장부가 들고 있는 "행 위젯" 은 계속 **내용 위젯**이다. 칸은 레이아웃
    도우미일 뿐이라 조회 창구(row_texts, card_widgets, block_views)의 반환이
    바뀌지 않는다.

    시그널 하나.
        copy_requested(str)  복사 버튼이 눌렸고, 담을 글은 이것이다
    """

    copy_requested = pyqtSignal(str)

    def __init__(self, content, text_getter=None, parent=None):
        """내용 위젯을 감싸고 복사 버튼을 붙인다.

        Args:
            content: 감쌀 내용 위젯.
            text_getter: callable() -> str. 복사할 글을 그때 읽어 온다 -
                스트리밍으로 자라는 블록이 있으므로 생성 시점의 값을 들고
                있으면 안 된다. None 이면 버튼을 만들지 않는다(구분선 행).
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self._content = content
        self._text_getter = text_getter
        self._button = None
        self._timer = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(CELL_BUTTON_SPACING)
        content.setParent(self)
        layout.addWidget(content, 1)

        if text_getter is None:
            return

        self._button = QToolButton(self)
        self._button.setObjectName("UpwiseChatCellCopy")
        self._button.setText(CELL_COPY_TEXT)
        self._button.setToolTip(CELL_COPY_TIP)
        self._button.setCursor(Qt.PointingHandCursor)
        self._button.setAutoRaise(True)
        self._button.clicked.connect(self._on_clicked)
        layout.addWidget(self._button, 0, Qt.AlignTop)

        # 피드백 되돌리기 타이머는 칸의 자식이다. 칸이 상한에 걸려 걷힐 때
        # (설계 4-4) 타이머도 함께 죽어야 죽은 위젯의 슬롯이 불리지 않는다.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(COPY_FEEDBACK_MS)
        self._timer.timeout.connect(self._reset_button)

    def content(self):
        """감싼 내용 위젯."""
        return self._content

    def copy_button(self):
        """복사 버튼. 없으면 None(구분선 행)."""
        return self._button

    def cell_text(self):
        """지금 이 칸이 복사할 글. 공급자가 없으면 빈 문자열이다."""
        if self._text_getter is None:
            return ""
        try:
            return self._text_getter() or ""
        except Exception:  # noqa: BLE001 - 조회 실패가 전사를 멈추지 않는다
            return ""

    def show_copied(self):
        """복사가 성립했다고 버튼으로 알리고 타이머로 되돌린다 (0.2.4).

        칸이 스스로 부르지 않는다. 복사는 전사의 클립보드 관문을 지나야
        성립하고(ChatView._set_clipboard), 관문이 막은 뒤의 "복사됨" 은
        거짓말이 된다. 그래서 성립을 아는 쪽(전사)이 부른다.

        Returns:
            bool: 알렸는가(버튼이 없는 행이면 False).
        """
        if self._button is None:
            return False
        self._button.setText(CELL_COPIED_TEXT)
        if self._timer is not None:
            self._timer.start()
        return True

    def _on_clicked(self):
        """복사 버튼. 글이 있을 때만 신호를 낸다.

        0.2.4: 버튼 피드백을 여기서 세우지 않는다 - 전사의 관문이 통과시킨
        뒤에 show_copied() 로 돌아온다.
        """
        text = self.cell_text()
        if not text:
            return
        self.copy_requested.emit(text)

    def _reset_button(self):
        """복사 피드백을 원래 글자로 되돌린다."""
        if self._button is not None:
            self._button.setText(CELL_COPY_TEXT)


class ChatView(QScrollArea):
    """전사 영역. 행을 append 만 하고 재배치하지 않는다.

    append 만으로 시간순이 맞는 이유: 사용자 말풍선은 전송 시점에, 모델 블록은
    상태머신이 발견한 순서대로 들어온다. 그래서 발견 순서가 곧 화면 순서다.

    시그널 하나 (0.2.4).
        copy_failed(str)  복사가 레다크션 관문에서 막혔다. 사유는 이것이다
    """

    copy_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        """스크롤 영역과 내부 레이아웃을 만든다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatTranscript")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._body = QWidget()
        self._body.setObjectName("UpwiseChatTranscriptBody")
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(VIEW_MARGIN, VIEW_MARGIN, VIEW_MARGIN, VIEW_MARGIN)
        self._layout.setSpacing(ROW_SPACING)
        # 꼬리 스트레치. 행은 항상 이 스트레치 앞에 끼운다.
        self._layout.addStretch(1)
        self.setWidget(self._body)

        # 접힘 안내 라벨. 블록 상한을 넘겼을 때만 보인다(설계 4-4).
        self._fold_label = QLabel("", self._body)
        self._fold_label.setObjectName("UpwiseChatFoldNotice")
        self._fold_label.setWordWrap(True)
        self._fold_label.setMinimumWidth(WRAP_LABEL_MIN_W)
        self._fold_label.setVisible(False)
        self._layout.insertWidget(0, self._fold_label)

        # 행 장부. kind 는 "user", "notice", "separator", "block", "card".
        self._rows = []
        self._by_key = {}
        self._seen_turns = set()
        self._folded_n = 0
        # U11: 화면에서 비운 블록/카드 키. sync() 가 상태머신을 다시 읽어도
        # 이 키는 새 행으로 되살리지 않는다(모듈 docstring 의 U11 절).
        self._cleared_keys = set()
        # 비우기 횟수. 하네스와 진단이 읽는다.
        self.cleared_rows = 0
        self.clear_count = 0

        # 측정값. S4 완료 판정 "렌더 끊김 없음" 의 근거다.
        self.render_ms = []
        self.sync_calls = 0
        self.updates = 0

        # 레다크션(0.2.1, 설계 docs/2 5-4 적용 지점 2 "전사 위젯 전").
        # 독이 Redactor 를 소유하고 여기에 콜러블로 넘긴다. None 이면 치환
        # 하지 않는다 - 키를 저장하지 않은 사용자에게 오버헤드를 주지 않는다.
        self._redact = None

        # 하단 고정 추적(0.1.3). 처음 전사는 비어 있어 바닥이므로 True 다.
        self._pinned = True
        # 재진입 가드. 우리가 부른 setValue 가 valueChanged 로 돌아와 고정
        # 상태를 다시 계산하면, "사용자가 스크롤했다" 와 "프로그램이 내렸다" 를
        # 구분하지 못한다. 이 플래그가 서 있는 동안의 valueChanged 는 사용자
        # 조작이 아니다.
        self._adjusting = False

        bar = self.verticalScrollBar()
        # rangeChanged 가 이 수정의 핵심이다(0.1.3). 행 위젯을 끼운 직후의
        # maximum() 은 아직 옛 값이다 - QScrollArea 는 내부 위젯의
        # LayoutRequest 를 받고 나서야 스크롤 범위를 다시 계산하고, 그
        # LayoutRequest 는 다음 이벤트 루프로 미뤄진다. 그래서 sync() 안에서
        # setValue(maximum()) 를 불러도 **옛 바닥**으로 갈 뿐이고, 범위가 자란
        # 뒤에는 자란 만큼 뒤처진다. 이것이 사용자가 매번 손으로 내려야 했던
        # 이유다(V28-A45). 범위가 실제로 바뀌는 그 순간에 다시 내린다.
        bar.rangeChanged.connect(self._on_scroll_range_changed)
        # 사용자가 위로 올리면 고정을 풀고, 다시 바닥으로 내리면 복귀시킨다.
        bar.valueChanged.connect(self._on_scroll_value_changed)

        # --------------------------------------------------------------
        # 0.2.3 복사 경로
        # --------------------------------------------------------------

        # 범위 선택 상태. None 이면 범위 선택이 없고(= 글자 단위 선택이 유효),
        # 있으면 (낮은 행 인덱스, 높은 행 인덱스) 다.
        self._range = None
        # 드래그를 시작한 행 인덱스. 눌린 동안만 값이 있다.
        self._anchor = None
        self._dragging = False
        # 범위 표시는 QRubberBand 다. 새 색을 만들지 않으려고 플랫폼 선택
        # 밴드를 쓴다 - 색을 우리가 정하면 두 테마 대비를 또 책임져야 한다.
        self._band = QRubberBand(QRubberBand.Rectangle, self._body)
        self._band.hide()
        # 우클릭 메뉴를 지역 변수로 두면 popup 직후 수거된다(비차단이라
        # 함수가 바로 끝난다). 참조를 들고 있는다.
        self._menu = None

        # 복사 장부. 클립보드는 플랫폼 플러그인에 딸려 있어 오프스크린에서
        # 왕복이 안 될 수 있다(하네스가 먼저 왕복을 재고 판정한다). 그래서
        # "복사 경로가 무엇을 만들었는가" 를 여기에 남긴다.
        self.last_copied = ""
        self.copy_count = 0
        # 0.2.4: 관문이 막은 횟수. "복사한 것이 없다" 와 "복사를 막았다" 는
        # 다른 사실이라 last_copied 하나로는 구분되지 않는다.
        self.copy_blocked = 0

        # Ctrl+C. 전사와 그 자식 안에서만 듣는다. 자식(QTextEdit)의 기본
        # 복사를 가리므로 핸들러가 글자 단위 선택도 함께 처리한다.
        self._copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self._copy_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._copy_shortcut.activated.connect(self.copy_selection)

    # ------------------------------------------------------------------
    # 로컬 행 (독이 직접 넣는 것)
    # ------------------------------------------------------------------

    def set_redactor(self, redactor):
        """레다크터를 붙이거나 뗀다(0.2.1).

        이미 그려진 행은 다시 쓰지 않는다. 붙기 전에 그려진 전사에 키가 있다면
        그 행은 그대로 남는다 - 사용자가 키를 저장하는 시점 이후의 행만
        보장한다. 되돌릴 수 없는 치환이라 소급 적용은 전사 전체 재구성이고,
        그것은 설계 4-4 의 append-only 규약을 깬다.

        Args:
            redactor: callable(str) -> str. None 이면 치환하지 않는다.
        """
        self._redact = redactor
        for row in self._rows:
            widget = row.get("widget")
            if hasattr(widget, "set_redactor"):
                widget.set_redactor(redactor)
        return True

    def _redacted(self, text):
        """레다크터가 있으면 치환한다. 실패해도 그리기를 멈추지 않는다."""
        if self._redact is None:
            return text
        try:
            return self._redact(text)
        except Exception:  # noqa: BLE001 - 치환 실패가 전사를 비우게 하지 않는다
            return text

    def add_user_message(self, text):
        """사용자 말풍선. 전송 즉시 그린다(설계 4-2 user 행: replay 는 렌더 금지).

        0.2.1: 사용자가 키를 입력창에 붙여 넣은 경로가 여기로 들어온다 -
        레다크션이 가장 먼저 걸려야 하는 행이다(설계 docs/2 5-4 의 전제).
        """
        # 0.2.3: 복사와 내보내기가 담을 글은 앞머리 없는 본문이다. 화면에는
        # "나: " 를 붙여 두고 복사본에는 넣지 않는다 - 역할은 내보낸 글의
        # 제목 줄이 따로 적는다.
        body = self._redacted(text or "")
        label = QLabel(USER_PREFIX + body, self._body)
        # 0.2.2: 사용자 메시지는 색 띠로 응답과 가른다. 배경을 칠하므로 글자색도
        # qss 가 함께 정한다(theme.USER_FG_*).
        label.setObjectName("UpwiseChatUserBubble")
        label.setWordWrap(True)
        # U13: 붙여 넣은 긴 경로 한 덩이가 전사 본문의 최소 폭이 되지 않게
        # 한다. 사용자 입력이 들어오는 행이라 가장 자주 걸리는 자리다.
        label.setMinimumWidth(WRAP_LABEL_MIN_W)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._append_row("user", None, label, text_getter=lambda: body,
                         body_text=body)
        return label

    def add_notice(self, text):
        """로컬 공지. 백엔드 종료, 취소 마감 같은 플러그인 쪽 사실을 적는다."""
        return self._append_notice(text, key=None)

    def add_status_notice(self, name, text):
        """같은 이름의 공지는 최신 1건만 남긴다 (U11 교체 표시).

        [점검] 같은 무과금 상태 출력이 쓰는 창구다. 누를 때마다 add_notice 로
        쌓으면 같은 사실의 사본이 전사를 채운다(사용자 피드백 2026-10-12).

        제자리에서 글자만 갈지 않고 **옛 행을 걷어내고 맨 아래에 새로 붙인다**.
        제자리 갱신은 위로 밀려 올라간 줄을 조용히 바꾸는 것이라, 사용자가 새
        결과를 보지 못한 채 옛 줄을 읽게 된다.

        Args:
            name: 교체 묶음 이름. 같은 이름끼리만 교체된다.
            text: 적을 글.

        Returns:
            QLabel: 새로 붙인 공지 라벨.
        """
        key = (STATUS_NOTICE_KEY, str(name))
        old = self._by_key.get(key)
        if old is not None:
            # 행 인덱스가 밀리므로 잡혀 있던 범위 선택은 푼다(_enforce_cap 과
            # 같은 이유 - 밴드만 남으면 엉뚱한 행을 복사한다).
            self._rows = [row for row in self._rows if row is not old]
            self._drop_row(old)
            self._clear_range()
        return self._append_notice(text, key=key)

    def _append_notice(self, text, key=None):
        """공지 라벨 하나를 만들어 행으로 붙인다.

        Args:
            text: 적을 글. 레다크터를 통과시킨다.
            key: 증분/교체용 키. None 이면 순수 append 다.

        Returns:
            QLabel: 붙인 라벨.
        """
        body = self._redacted(text or "")
        label = QLabel(body, self._body)
        label.setObjectName("UpwiseChatNotice")
        label.setWordWrap(True)
        # U13: 공지에는 경로와 포트가 자주 들어간다. 그 한 덩이가 최소 폭을
        # 밀면 전사 전체가 잘린다.
        label.setMinimumWidth(WRAP_LABEL_MIN_W)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._append_row("notice", key, label, text_getter=lambda: body,
                         body_text=body)
        return label

    def clear_transcript(self):
        """화면 전사만 비운다 (U11).

        비우지 **않는** 것을 먼저 적는다. 상태머신(machine.turns)도, CLI 세션도,
        모델이 들고 있는 대화 맥락도, 이미 쓴 세션 jsonl 과 내보내기 파일도
        건드리지 않는다. 이 함수가 하는 일은 행 위젯을 걷어내는 것뿐이다.
        세션까지 새로 시작하는 것은 다른 기능이고(U16) 이 패스 범위가 아니다.

        상태머신이 남아 있으므로 다음 드레인이 같은 블록을 다시 그리려 한다.
        그래서 걷어낸 블록/카드 키를 `_cleared_keys` 에 넣어 재생성을 막는다.
        `_seen_turns` 는 지우지 않는다 - 지우면 옛 턴 구분선이 다시 붙는다.

        Returns:
            int: 걷어낸 행 수.
        """
        n = len(self._rows)
        for row in self._rows:
            key = row.get("key")
            # 막을 대상은 상태머신에서 다시 올라오는 행(블록, 카드)뿐이다.
            # 공지와 말풍선은 독이 그때그때 넣는 것이라 되살아날 길이 없다.
            if key is not None and row.get("kind") in ("block", "card"):
                self._cleared_keys.add(key)
            self._drop_row(row)
        self._rows = []
        self._by_key = {}
        self._clear_range()
        self._anchor = None
        self._dragging = False
        # 접힘 안내는 "상한으로 접은 블록이 있다" 는 사실이다. 화면이 비었으니
        # 그 줄도 내린다. 누적수(_folded_n)는 지우지 않는다 - 다음에 상한이
        # 걸리면 같은 누적에 이어서 센다.
        self._fold_label.setVisible(False)
        # 빈 화면은 바닥이다. 다음 출력부터 다시 따라붙는다.
        self._pinned = True
        self.cleared_rows += n
        self.clear_count += 1
        return n

    def reset_session_view(self):
        """화면을 비우고 **재생성 차단까지 푼다** (U16 [새 대화]).

        U11([대화 지우기])과 갈리는 자리다. U11 은 상태머신이 그대로 남으므로
        걷어낸 키를 `_cleared_keys` 에 넣어 되살아나는 것을 막아야 한다. U16 은
        세션을 버리고 독이 **새 상태머신**을 세우므로 그 차단을 그대로 들고
        가면 반대 방향으로 틀린다.

        왜 틀리는가 (두 집합의 근거가 다르다)
            `_seen_turns` 는 **턴 번호**가 키다. 새 상태머신은 턴 1 부터 다시
            세므로, 비우지 않으면 새 대화의 첫 턴 구분선이 "이미 본 턴" 으로
            걸러진다. 이쪽은 확실한 충돌이다.

            `_cleared_keys` 는 블록 `(message_id, index)` 와 `tool_use_id` 가
            키다(backend/machine `_make_block`). CLI 가 주는 message_id 는
            세션을 넘어 겹치지 않으므로 평소에는 충돌하지 않는다. 그래도
            비우는 이유는 둘이다. (1) message_id 가 없는 이벤트는 키가
            `(None, index)` 로 떨어지고, 그때는 새 세션의 첫 블록이 방금 비운
            옛 블록과 같은 키를 받아 **화면에 못 나타난다.** (2) 죽은 세션의
            차단 목록을 들고 가는 것은 그 자체로 틀린 상태다 - 자라기만 하고
            아무것도 가리키지 않는다.

        Returns:
            int: 걷어낸 행 수.
        """
        n = self.clear_transcript()
        self._cleared_keys = set()
        self._seen_turns = set()
        return n

    # ------------------------------------------------------------------
    # 상태머신 동기화
    # ------------------------------------------------------------------

    def sync(self, machine):
        """상태머신의 전사를 위젯에 반영한다. 바뀐 것만 만진다.

        Args:
            machine: backend.machine.TurnMachine.

        Returns:
            int: 갱신한 행 수.
        """
        t0 = time.perf_counter()
        changed = 0
        for turn in machine.turns:
            if turn.turn_no not in self._seen_turns:
                self._seen_turns.add(turn.turn_no)
                self._append_separator(turn.turn_no)
                changed += 1
            for rb in turn.blocks:
                if rb.kind == "tool_use":
                    card = turn.cards.get(rb.tool_use_id)
                    if card is not None and self._sync_card(card):
                        changed += 1
                elif rb.kind in ("text", "thinking"):
                    if self._sync_block(rb):
                        changed += 1
            # tool_use 를 못 본 결과로 생긴 카드는 블록이 없다. 턴 끝에 붙인다.
            for cid in turn.card_order:
                card = turn.cards.get(cid)
                if card is not None and card.orphan and self._sync_card(card):
                    changed += 1
        self._enforce_cap()
        # 고정 모드면 지금 알고 있는 바닥까지 내려 둔다. 범위가 아직 안 자랐을
        # 수 있으므로 최종 추종은 rangeChanged 가 맡는다(__init__ 주석 참조).
        if self._pinned:
            self._scroll_to_bottom()
        self.sync_calls += 1
        self.updates += changed
        self.render_ms.append((time.perf_counter() - t0) * 1000.0)
        return changed

    def _sync_block(self, rb):
        """텍스트/생각 블록 하나를 반영한다."""
        key = ("block", rb.key)
        if key in self._cleared_keys:
            # U11: 사용자가 화면에서 비운 블록이다. 상태머신에는 그대로
            # 남아 있으므로 여기서 막지 않으면 다음 드레인에 되살아난다.
            return False
        row = self._by_key.get(key)
        if row is None:
            if rb.kind == "thinking":
                # 생각은 기본 접힘이다(설계 4-2 thinking_delta 행).
                section = CollapsibleSection(
                    "생각 중", self._body, expanded=False,
                    object_name="UpwiseChatThinkingTitle")
                view = GrowingTextView(section)
                view.setObjectName("UpwiseChatThinkingText")
                section.add_body_widget(view)
                row = self._append_row("block", key, section, view=view,
                                       block_kind=rb.kind,
                                       text_getter=view.rendered_text)
            else:
                view = GrowingTextView(self._body)
                # 0.2.2: 모델 응답 블록은 왼쪽 레일로 사용자 띠와 가른다.
                view.setObjectName("UpwiseChatAssistantText")
                row = self._append_row("block", key, view, view=view,
                                       block_kind=rb.kind,
                                       text_getter=view.rendered_text)
        view = row["view"]
        return view.set_text_incremental(self._redacted(rb.text()))

    def _sync_card(self, card):
        """도구 카드 하나를 반영한다."""
        key = ("card", card.tool_use_id or id(card))
        if key in self._cleared_keys:
            # U11. _sync_block 과 같은 이유다.
            return False
        row = self._by_key.get(key)
        if row is None:
            widget = ToolCardWidget(self._body, redactor=self._redact)
            row = self._append_row("card", key, widget,
                                   text_getter=widget.copy_text)
        return row["widget"].update_from(card)

    def _append_separator(self, turn_no):
        """턴 구분선.

        0.2.2: Sunken HLine(음각 2선)을 1 px 평선으로 바꿨다. 음각 선은 카드
        테두리와 섞여 "경계가 두 종류" 로 보였다.
        """
        line = QFrame(self._body)
        line.setObjectName("UpwiseChatTurnSeparator")
        line.setFrameShape(QFrame.NoFrame)
        line.setFixedHeight(SEPARATOR_PX)
        self._append_row("separator", None, line, turn_no=turn_no)

    # ------------------------------------------------------------------
    # 내부 - 행 장부와 상한
    # ------------------------------------------------------------------

    def _append_row(self, kind, key, widget, text_getter=None, **extra):
        """행을 꼬리 스트레치 앞에 끼우고 장부에 남긴다.

        extra 의 키 이름은 "kind" 와 겹치지 않아야 한다. 겹치면 행 종류가
        덮어써져서 상한 계산이 틀어진다(그래서 블록 종류는 block_kind 다).

        0.2.3: 내용 위젯을 TranscriptCell 로 감싸 레이아웃에 끼운다. 장부의
        "widget" 은 **계속 내용 위젯**이고 칸은 "cell" 로 따로 둔다 - 기존
        조회 창구가 그대로 돌아야 한다.

        Args:
            kind: 행 종류("user", "notice", "separator", "block", "card").
            key: 증분 갱신용 키. 없으면 None.
            widget: 내용 위젯.
            text_getter: 칸 복사 버튼이 읽을 공급자. None 이면 버튼이 없다.
            **extra: 장부에 함께 남길 값.

        Returns:
            dict: 장부 행.
        """
        cell = TranscriptCell(widget, text_getter, self._body)
        cell.copy_requested.connect(self._on_cell_copy)
        self._layout.insertWidget(self._layout.count() - 1, cell)
        # 범위 선택은 자식 위젯의 마우스 이벤트를 보고 판정한다. 칸이 생기는
        # 이 자리에서 한 번만 걸면 뒤에 위젯이 더 생기지 않는다(카드 내부
        # 위젯은 카드 생성 시점에 전부 만들어진다).
        self._install_filters(cell)
        row = {"kind": kind, "key": key, "widget": widget, "cell": cell,
               "ts": time.time()}
        row.update(extra)
        self._rows.append(row)
        if key is not None:
            self._by_key[key] = row
        return row

    def _enforce_cap(self):
        """블록/카드 위젯을 최근 200개로 제한한다(설계 4-4).

        세는 대상은 블록과 카드다. 구분선과 공지는 내용이 아니므로 상한의
        분모에 넣지 않지만, 앞쪽 블록이 접힐 때 함께 걷어낸다.
        """
        content = [r for r in self._rows if r["kind"] in ("block", "card")]
        over = len(content) - BLOCK_WIDGET_MAX
        if over <= 0:
            return
        dropped = 0
        kept = []
        for row in self._rows:
            if dropped < over and row["kind"] in ("block", "card", "separator", "user", "notice"):
                if row["kind"] in ("block", "card"):
                    dropped += 1
                self._drop_row(row)
                continue
            kept.append(row)
        self._rows = kept
        # 0.2.3: 행 인덱스가 밀렸다. 잡혀 있던 범위는 다른 행을 가리키게 되므로
        # 푼다. 밴드만 남겨 두면 엉뚱한 행을 복사한다.
        self._clear_range()
        self._folded_n += dropped
        self._fold_label.setText(
            "이전 %d개 블록은 접었습니다. 전문은 세션 기록 파일에 있습니다." % self._folded_n
        )
        self._fold_label.setVisible(True)

    def _drop_row(self, row):
        """행 위젯을 떼어내고 장부에서 지운다.

        0.2.3: 레이아웃에 들어 있는 것은 칸이다. 내용 위젯만 떼면 빈 칸이
        남아 행 간격이 어긋난다.
        """
        if row["key"] is not None:
            self._by_key.pop(row["key"], None)
        widget = row.get("cell") or row["widget"]
        self._layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()

    def _at_bottom(self):
        """스크롤이 이미 바닥에 있는가. 사용자가 위를 읽고 있으면 끌어내리지 않는다."""
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - BOTTOM_EPSILON_PX

    def _scroll_to_bottom(self):
        """바닥으로 내린다.

        이 호출로 생기는 valueChanged 는 사용자 조작이 아니므로 재진입 가드를
        세운 채로 움직인다. 가드를 안 세우면 고정 상태를 자기 자신의 스크롤로
        다시 계산하게 된다.
        """
        bar = self.verticalScrollBar()
        self._adjusting = True
        try:
            bar.setValue(bar.maximum())
        finally:
            self._adjusting = False

    def _on_scroll_range_changed(self, _minimum, _maximum):
        """스크롤 범위가 바뀌었다. 고정 모드일 때만 새 바닥으로 다시 내린다.

        내용이 자라 범위가 늘어난 바로 그 순간이고, 이때의 maximum() 은 이미
        갱신된 값이다. 고정이 풀려 있으면(사용자가 위를 읽는 중이면) 아무것도
        하지 않는다.
        """
        if self._pinned:
            self._scroll_to_bottom()

    def _on_scroll_value_changed(self, _value):
        """스크롤 위치가 바뀌었다. 사용자가 움직인 것일 때만 고정을 다시 판단한다.

        위로 올렸으면 고정이 풀려 새 출력이 와도 위치를 지키고, 다시 바닥까지
        내렸으면 고정으로 복귀한다. 우리가 부른 setValue 로 들어온 호출은
        재진입 가드에 걸려 상태를 건드리지 않는다.
        """
        if self._adjusting:
            return
        self._pinned = self._at_bottom()

    # ------------------------------------------------------------------
    # 내부 - 범위 선택과 복사 (0.2.3)
    # ------------------------------------------------------------------

    def _install_filters(self, cell):
        """칸과 그 자손 전부에 이벤트 필터를 건다.

        드래그의 시작점은 사용자가 누른 **말 위**다. 그 위젯은 말풍선일 수도
        있고 QTextEdit 의 viewport 일 수도 있고 카드 안쪽 뷰일 수도 있다.
        한 군데라도 빠지면 그 자리에서 시작한 드래그가 추적되지 않으므로
        자손을 전부 훑는다.

        Args:
            cell: TranscriptCell.

        Returns:
            int: 필터를 건 객체 수.
        """
        n = 0
        for widget in [cell] + cell.findChildren(QWidget):
            widget.installEventFilter(self)
            n += 1
        return n

    def eventFilter(self, obj, event):  # noqa: N802 - Qt 가 요구하는 고정 이름
        """행 위젯의 마우스 이벤트로 범위 선택을 판정한다.

        누름은 **소비하지 않는다** - 한 행 안에서의 글자 단위 선택이 그대로
        살아 있어야 한다. 행 경계를 넘는 순간부터 범위 모드로 들어가고
        그때부터 이동을 소비한다.

        Args:
            obj: 이벤트를 받은 객체.
            event: 이벤트.

        Returns:
            bool: 이벤트를 소비했는가.
        """
        kind = event.type()
        if kind == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self._clear_range()
                self._anchor = self._row_index_at(event.globalPos())
                self._dragging = True
        elif kind == QEvent.MouseMove:
            if self._dragging and event.buttons() & Qt.LeftButton:
                if self._on_drag_move(event.globalPos()):
                    return True
        elif kind == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                self._dragging = False
        elif kind == QEvent.ContextMenu:
            # 우클릭은 **항상** 우리가 받는다(0.3.0). 넘기면 자식 위젯의 Qt
            # 표준 메뉴가 뜨고 그 Copy 가 클립보드로 직행해 관문을
            # 비킨다(V32-A01 실측). 범위가 있으면 범위 메뉴, 없으면 글자
            # 선택 메뉴다 - 둘 다 _set_clipboard 를 지난다.
            if self._show_range_menu(event):
                return True
            return self._show_char_menu(obj, event)
        return super(ChatView, self).eventFilter(obj, event)

    def _on_drag_move(self, global_pos):
        """드래그 중 커서 위치로 범위를 갱신한다.

        Args:
            global_pos: 전역 좌표.

        Returns:
            bool: 이벤트를 소비해야 하는가(범위 모드에 들어와 있는가).
        """
        if self._anchor is None:
            return False
        index = self._row_index_at(global_pos)
        if index is None:
            # 전사 밖으로 나갔다. 이미 범위 모드면 그 범위를 지키고 계속
            # 소비한다 - 여기서 놓으면 범위가 깜박인다.
            return self._range is not None
        if self._range is None and index == self._anchor:
            # 아직 같은 행 안이다. 글자 단위 선택에 맡긴다.
            return False
        lo = min(self._anchor, index)
        hi = max(self._anchor, index)
        self._set_range(lo, hi)
        return True

    def _row_index_at(self, global_pos):
        """전역 좌표가 가리키는 행 인덱스.

        행 사이 간격이나 전사 끝 바깥에 떨어져도 가장 가까운 행을 고른다 -
        마지막 행보다 아래로 끌면 "끝까지" 가 되어야 한다.

        Args:
            global_pos: 전역 좌표.

        Returns:
            int: 행 인덱스. 행이 없으면 None.
        """
        items = [(i, r["cell"].geometry())
                 for i, r in enumerate(self._rows) if r.get("cell") is not None]
        if not items:
            return None
        y = self._body.mapFromGlobal(global_pos).y()
        for index, geo in items:
            if geo.top() <= y <= geo.bottom():
                return index
        if y < items[0][1].top():
            return items[0][0]
        if y > items[-1][1].bottom():
            return items[-1][0]
        best_index, best_gap = items[0][0], None
        for index, geo in items:
            gap = min(abs(y - geo.top()), abs(y - geo.bottom()))
            if best_gap is None or gap < best_gap:
                best_index, best_gap = index, gap
        return best_index

    def _set_range(self, lo, hi):
        """행 범위를 잡고 밴드를 그린다. 걸친 행의 글자 선택은 지운다.

        Args:
            lo: 낮은 행 인덱스.
            hi: 높은 행 인덱스.

        Returns:
            bool: 밴드를 띄웠는가.
        """
        self._range = (lo, hi)
        for index in range(lo, hi + 1):
            if 0 <= index < len(self._rows):
                self._clear_child_selection(self._rows[index].get("widget"))
        return self._update_band()

    def _clear_range(self):
        """범위 선택을 풀고 밴드를 내린다."""
        self._range = None
        self._band.hide()

    def _update_band(self):
        """범위에 걸친 칸들의 합집합 사각형으로 밴드를 맞춘다.

        Returns:
            bool: 밴드를 띄웠는가.
        """
        if self._range is None:
            self._band.hide()
            return False
        lo, hi = self._range
        rect = None
        for index in range(lo, hi + 1):
            if not (0 <= index < len(self._rows)):
                continue
            cell = self._rows[index].get("cell")
            if cell is None:
                continue
            geo = cell.geometry()
            rect = QRect(geo) if rect is None else rect.united(geo)
        if rect is None:
            self._band.hide()
            return False
        self._band.setGeometry(rect)
        self._band.show()
        self._band.raise_()
        return True

    def _clear_child_selection(self, widget):
        """행 위젯이 들고 있는 글자 선택을 지운다.

        범위 모드로 들어가는 순간 두 종류의 선택이 함께 보이면 무엇이 복사될지
        읽히지 않는다.

        Args:
            widget: 행의 내용 위젯.

        Returns:
            bool: 지울 것이 있었는가.
        """
        if widget is None:
            return False
        for target in [widget] + widget.findChildren(QWidget):
            getter = getattr(target, "textCursor", None)
            setter = getattr(target, "setTextCursor", None)
            if callable(getter) and callable(setter):
                cursor = getter()
                if cursor.hasSelection():
                    cursor.clearSelection()
                    setter(cursor)
            deselect = getattr(target, "setSelection", None)
            if callable(deselect) and isinstance(target, QLabel):
                deselect(0, 0)
        return True

    def _selected_text_of(self, widget):
        """위젯 하나가 들고 있는 글자 선택.

        Args:
            widget: 검사할 위젯.

        Returns:
            str: 선택된 글. 없으면 빈 문자열.
        """
        getter = getattr(widget, "textCursor", None)
        if callable(getter):
            cursor = getter()
            if cursor.hasSelection():
                # QTextCursor.selectedText() 는 단락 구분을 U+2029 로 준다.
                # 붙여 넣을 글에는 줄바꿈이어야 하므로 fragment 로 뽑는다.
                return cursor.selection().toPlainText()
        getter = getattr(widget, "selectedText", None)
        if callable(getter):
            try:
                return getter() or ""
            except TypeError:
                # 인자를 요구하는 동명 메서드(위젯 종류에 따라)는 건너뛴다.
                return ""
        return ""

    def _focused_selection(self):
        """포커스를 가진 전사 안 위젯의 글자 선택.

        Ctrl+C 를 전사 수준에서 가로채므로(기본 복사를 가린다) 범위 선택이
        없을 때의 복사도 여기서 책임진다.

        Returns:
            str: 선택된 글. 없으면 빈 문자열.
        """
        widget = QApplication.focusWidget()
        if widget is None:
            return ""
        if not (widget is self or self.isAncestorOf(widget)):
            return ""
        # QTextEdit 는 viewport 가 포커스를 갖는다. 몇 단계 위까지 본다.
        for _ in range(4):
            if widget is None:
                break
            text = self._selected_text_of(widget)
            if text:
                return text
            widget = widget.parentWidget()
        return ""

    def _show_range_menu(self, event):
        """범위가 잡혀 있을 때의 우클릭 메뉴.

        `popup()` 으로 띄운다 - `exec_()` 는 중첩 이벤트 루프라 금지
        목록이다(설계 3-5). 범위가 없으면 아무것도 하지 않고 False 를
        돌린다. 그 경우를 받는 자리는 0.3.0 부터 `_show_char_menu` 다
        (그전에는 위젯 표준 메뉴였고 그것이 V32-A01 의 유출면이었다).

        Args:
            event: QContextMenuEvent.

        Returns:
            bool: 메뉴를 띄웠는가.
        """
        if self._range is None:
            return False
        menu = QMenu(self)
        menu.setAttribute(Qt.WA_DeleteOnClose)
        action = menu.addAction(RANGE_COPY_TEXT)
        action.triggered.connect(self.copy_selection)
        # popup 은 비차단이라 이 함수가 바로 끝난다. 지역 변수로 두면 메뉴가
        # 그 자리에서 수거된다.
        self._menu = menu
        menu.popup(event.globalPos())
        return True

    def _show_char_menu(self, obj, event):
        """범위가 없을 때의 우클릭 메뉴. 글자 선택 복사를 관문에 태운다 (0.3.0).

        왜 위젯 표준 메뉴를 쓰지 않는가 (V32-A01)
            0.2.4 는 "모든 클립보드 쓰기가 한 관문(_set_clipboard)을 지난다"
            를 불변식으로 세웠는데, 이 경로 하나가 빠져 있었다. 범위가 없을
            때 ContextMenu 를 넘기면 자식 QTextEdit/QLabel 이 자기
            `createStandardContextMenu()` 를 띄우고, 그 메뉴의 Copy 는
            `QClipboard` 에 **직행**한다. 레다크션은 비소급이라(모듈
            docstring) 레다크터 부착 전에 그려진 행에는 키 원문이 남아 있고,
            실측에서 그 행의 글자를 선택해 표준 메뉴 Copy 를 누르면
            클립보드에 키 원문이 1건 올라갔다(관문 카운터 last_copied 는
            공백). Ctrl+C 축은 QShortcut 으로 이미 가로채 관문을 지난다 -
            열려 있던 것은 우클릭 축 하나였다.

            그래서 표준 메뉴를 "고치는" 대신 **띄우지 않는다**. 표준 메뉴에는
            Copy 말고도 링크 주소 복사처럼 클립보드로 직행하는 항목이 더
            생길 수 있어, 항목을 골라 막는 방식은 다음 Qt 판에서 다시 뚫린다.
            기능은 보존한다 - 한 행 안 글자 선택 복사는 여기서 같은 글을
            같은 관문으로 내보낸다.

            담을 것이 없으면 메뉴를 띄우지 않는다. 그래도 이벤트는 소비해서
            표준 메뉴가 뜨지 못하게 한다. 선택이 없을 때 Qt 가 Copy 를
            비활성으로 두는 것에 기대지 않기 위함이다(그 비활성은 Qt 판에
            딸린 동작이고 우리 불변식이 아니다).

        `popup()` 으로 띄운다 - 금지 API 목록(설계 3-5) 때문이다.

        Args:
            obj: ContextMenu 를 받은 위젯. 글자 선택을 여기서부터 찾는다.
            event: QContextMenuEvent.

        Returns:
            bool: 항상 True. 이벤트를 소비해 표준 메뉴를 막는 것이 이
                함수의 목적이므로, 메뉴를 띄우지 못한 경우에도 소비한다.
        """
        text = self._selection_text_near(obj)
        if not text:
            self._menu = None
            return True
        menu = QMenu(self)
        menu.setAttribute(Qt.WA_DeleteOnClose)
        action = menu.addAction(CHAR_COPY_TEXT)
        # triggered 는 checked(bool) 를 실어 보내므로 인자를 흘려 버린다.
        # 복사할 글은 메뉴를 띄운 시점의 선택으로 고정한다 - 메뉴가 열려 있는
        # 동안 선택이 풀려도 사용자가 본 그 글이 복사되어야 한다.
        action.triggered.connect(lambda *_ignored: self._set_clipboard(text))
        self._menu = menu
        menu.popup(self._menu_pos(event))
        return True

    def _menu_pos(self, event):
        """메뉴를 띄울 전역 좌표.

        이벤트가 전역 좌표를 주지 않는 경로(합성 호출 등)에서도 메뉴 자리를
        정할 수 있어야 한다.

        Args:
            event: QContextMenuEvent 또는 None.

        Returns:
            QPoint: 전역 좌표.
        """
        getter = getattr(event, "globalPos", None)
        if callable(getter):
            return getter()
        return self.mapToGlobal(QPoint(0, 0))

    def _selection_text_near(self, obj):
        """우클릭을 받은 위젯 쪽의 글자 선택.

        포커스가 아니라 **이벤트를 받은 위젯**에서 올라간다. 오프스크린이나
        창 활성이 없는 구성에서는 `focusWidget()` 이 비어 있을 수 있는데
        우클릭의 출처는 항상 있다. QTextEdit 는 viewport 가 이벤트를 받으므로
        `_focused_selection` 과 같은 이유로 몇 단계 위까지 본다. 거기서도 못
        찾으면 포커스 경로로 되돌아간다.

        Args:
            obj: 이벤트를 받은 객체.

        Returns:
            str: 선택된 글. 없으면 빈 문자열.
        """
        widget = obj if isinstance(obj, QWidget) else None
        for _ in range(4):
            if widget is None:
                break
            if widget is not self and not self.isAncestorOf(widget):
                break
            text = self._selected_text_of(widget)
            if text:
                return text
            widget = widget.parentWidget()
        return self._focused_selection()

    def _on_cell_copy(self, text):
        """칸 복사 버튼이 낸 신호. 관문을 지난 글만 클립보드로 보낸다.

        관문이 막으면 버튼 피드백도 세우지 않는다 - 0.2.4 의 요점이 "막고
        나서 막았다고 말한다" 이므로, 같은 동작이 "복사됨" 을 띄우면 안 된다.

        Args:
            text: 칸이 담아 보낸 보이는 글.

        Returns:
            str: 실제로 클립보드에 올린 글. 막혔으면 빈 문자열.
        """
        copied = self._set_clipboard(text)
        if not copied:
            return ""
        cell = self.sender()
        if isinstance(cell, TranscriptCell):
            cell.show_copied()
        return copied

    def _redacted_clipboard(self, text):
        """클립보드로 나갈 글을 레다크터에 통과시킨다 (0.2.4).

        내보내기(dock._redacted_export)와 **같은 의미론**이다. 레다크터가
        없으면 그대로 돌려준다(저장된 키가 없으니 치환 대상도 없다). 예외가
        나면 None 을 돌려 호출자가 **쓰지 않게** 한다.

        그리기 경로의 `_redacted()` 와 다른 점이 여기다: 그리기는 치환이
        실패해도 원문을 화면에 두고 계속 간다(전사를 비울 수는 없다). 복사는
        화면 밖으로 사본을 내보내는 일이라, 실패를 원문 복제로 바꾸지 않는다.

        Args:
            text: 올리려는 글.

        Returns:
            str: 치환된 글. 치환이 실패하면 None.
        """
        redactor = self._redact
        if redactor is None:
            return text
        try:
            return redactor(text)
        except Exception:  # noqa: BLE001 - 실패를 원문 복사로 바꾸지 않는다
            return None

    def _set_clipboard(self, text):
        """레다크션 관문을 지난 글만 클립보드에 올리고 장부에 남긴다.

        왜 관문이 여기 한 곳인가 (0.2.4)
            0.2.3 은 칸 복사와 범위 복사가 각각 클립보드로 직행했고 관문이
            없었다. 레다크션은 비소급이라(set_redactor) 레다크터가 붙기 전에
            그려진 행에는 키가 그대로 남아 있고, 그 행을 복사하면 키가
            클립보드로 나갔다(V28-A89 실측: 복사 2경로 key_hits=1, 같은 행
            내보내기는 0). 내보내기는 쓰기 직전 관문 하나로 그 면을 닫아
            두었다(dock._redacted_export). 복사도 같은 자리를 갖도록 모든
            클립보드 쓰기를 이 함수로 모은다 - 앞으로 생기는 복사 경로도
            여기를 지나야 클립보드에 닿는다.

        장부(`last_copied`)를 따로 두는 이유: 클립보드는 플랫폼 플러그인에
        딸려 있어 오프스크린 QPA 에서 왕복이 안 되는 구성이 있다. 그 구성에서도
        "복사 경로가 무엇을 만들었는가" 는 판정할 수 있어야 한다.

        Args:
            text: 올리려는 글.

        Returns:
            str: 실제로 올린 글. 관문이 막으면 빈 문자열이고 클립보드와
                장부는 건드리지 않는다.
        """
        safe = self._redacted_clipboard(text)
        if safe is None:
            self.copy_blocked += 1
            self.copy_failed.emit(COPY_REDACT_FAIL)
            return ""
        self.last_copied = safe
        self.copy_count += 1
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(safe)
        return safe

    # ------------------------------------------------------------------
    # 복사와 내보내기 (0.2.3 공개 창구)
    # ------------------------------------------------------------------

    def selected_rows(self):
        """지금 범위 선택에 걸린 행 인덱스 목록. 없으면 빈 목록."""
        if self._range is None:
            return []
        lo, hi = self._range
        return [i for i in range(lo, hi + 1) if 0 <= i < len(self._rows)]

    def selection_text(self):
        """지금 복사하면 담길 글.

        범위 선택이 있으면 걸친 행들의 **보이는 글**을 빈 줄로 이어 붙이고,
        없으면 포커스 위젯의 글자 선택을 돌려준다.

        Returns:
            str: 담길 글. 담을 것이 없으면 빈 문자열.
        """
        if self._range is not None:
            parts = []
            for index in self.selected_rows():
                cell = self._rows[index].get("cell")
                if cell is None:
                    continue
                text = cell.cell_text()
                if text:
                    parts.append(text)
            return RANGE_JOIN.join(parts)
        return self._focused_selection()

    def copy_selection(self):
        """Ctrl+C 와 우클릭 메뉴가 부르는 복사.

        Returns:
            str: 클립보드에 올린 글. 담을 것이 없거나 레다크션 관문이
                막으면 빈 문자열(0.2.4).
        """
        text = self.selection_text()
        if not text:
            return ""
        return self._set_clipboard(text)

    def export_rows(self):
        """내보내기용 행 목록(0.2.3).

        담는 글은 전부 **화면에 보이는 사본**이다 - 즉 레다크션을 이미 통과한
        문자열이다. 원문을 따로 꺼내는 경로를 만들지 않는다.

        Returns:
            list[dict]: kind, ts, turn_no, block_kind, title, body, detail.
        """
        out = []
        for row in self._rows:
            kind = row.get("kind")
            block_kind = row.get("block_kind") or ""
            item = {"kind": kind, "ts": row.get("ts", 0.0),
                    "turn_no": row.get("turn_no"), "block_kind": block_kind,
                    "title": "", "body": "", "detail": ""}
            if kind in ("user", "notice"):
                item["title"] = transcript_mod.ROLE_TITLES.get(kind, kind)
                item["body"] = row.get("body_text") or ""
            elif kind == "block":
                view = row.get("view")
                role = "thinking" if block_kind == "thinking" else "assistant"
                item["title"] = transcript_mod.ROLE_TITLES.get(role, role)
                item["body"] = view.rendered_text() if view is not None else ""
            elif kind == "card":
                widget = row.get("widget")
                item["title"] = widget.title_text() if widget is not None else "도구"
                item["body"] = widget.args_text() if widget is not None else ""
                item["detail"] = widget.result_text() if widget is not None else ""
            out.append(item)
        return out

    # ------------------------------------------------------------------
    # 조회 (검증 하네스가 읽는다)
    # ------------------------------------------------------------------

    def cells(self):
        """행마다의 TranscriptCell 목록. 추가 순서다(검증 하네스가 읽는다)."""
        return [r.get("cell") for r in self._rows]

    def row_count(self):
        """지금 장부에 있는 행 수.

        stats() 는 렌더 시간 목록을 정렬하므로 키 입력마다 부를 값이 아니다.
        내보내기 버튼 활성 판정이 그 경로에 있어서 가벼운 창구를 따로 둔다.
        """
        return len(self._rows)

    def stats(self):
        """렌더 비용과 행 구성 요약."""
        times = sorted(self.render_ms)
        n = len(times)
        return {
            "rows": len(self._rows),
            "blocks": len([r for r in self._rows if r["kind"] == "block"]),
            "cards": len([r for r in self._rows if r["kind"] == "card"]),
            "folded": self._folded_n,
            "sync_calls": self.sync_calls,
            "updates": self.updates,
            "render_max_ms": times[-1] if n else 0.0,
            "render_mean_ms": (sum(times) / n) if n else 0.0,
            "render_p95_ms": times[int(n * 0.95)] if n else 0.0,
            # 0.2.1. 레다크터가 붙어 있는가. 건수는 독이 레다크터에서 읽는다.
            "redactor_attached": self._redact is not None,
            # U11. 몇 번 비웠고 몇 행을 걷어냈는가, 재생성을 막고 있는 키가
            # 몇 개인가. "비웠다" 와 "비울 것이 없었다" 를 밖에서 가른다.
            "clear_count": self.clear_count,
            "cleared_rows": self.cleared_rows,
            "cleared_keys": len(self._cleared_keys),
        }

    def is_pinned(self):
        """하단 고정 모드인가(0.1.3). 검증 하네스가 읽는다."""
        return self._pinned

    def scroll_state(self):
        """스크롤바 상태 (value, maximum, pinned). 검증 하네스가 읽는다.

        고정 추종을 밖에서 판정할 창구다. value == maximum 이어야 최신 출력이
        보이고, maximum == 0 이면 내용이 뷰포트보다 작아 판정이 공허하다.
        """
        bar = self.verticalScrollBar()
        return bar.value(), bar.maximum(), self._pinned

    def row_texts(self):
        """행마다 (종류, 보이는 글) 목록. 검증 하네스가 읽는다.

        전사에 무엇이 실제로 쓰였는지를 밖에서 확인할 창구가 필요하다.
        위젯 종류가 섞여 있으므로 text() 가 있는 것만 읽는다.
        """
        out = []
        for row in self._rows:
            widget = row.get("widget")
            getter = getattr(widget, "text", None)
            try:
                text = getter() if callable(getter) else ""
            except Exception:  # noqa: BLE001 - 조회가 하네스를 멈추지 않게 한다
                text = ""
            out.append((row["kind"], text or ""))
        return out

    def card_widgets(self):
        """지금 살아 있는 도구 카드 위젯 목록. 추가 순서다."""
        return [r["widget"] for r in self._rows if r["kind"] == "card"]

    def block_views(self):
        """지금 살아 있는 텍스트/생각 블록의 (종류, 뷰) 목록."""
        return [
            (r.get("block_kind"), r.get("view"))
            for r in self._rows
            if r["kind"] == "block"
        ]

    def thinking_sections(self):
        """생각 블록의 접힘 영역 위젯 목록. 기본 접힘 확인에 쓴다."""
        return [
            r["widget"]
            for r in self._rows
            if r["kind"] == "block" and r.get("block_kind") == "thinking"
        ]

    def fold_notice_visible(self):
        """접힘 안내를 띄우기로 했는가(설계 4-4 상한 적용 여부)."""
        return not self._fold_label.isHidden()

    def rendered_text(self):
        """화면에 들어간 텍스트 블록만 이어 붙인 값. 중복 검사용이다."""
        parts = []
        for row in self._rows:
            if row["kind"] == "block" and row.get("block_kind") != "thinking":
                view = row.get("view")
                if view is not None:
                    parts.append(view.rendered_text())
        return "\n".join(parts)
