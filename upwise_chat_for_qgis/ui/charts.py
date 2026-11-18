"""독 안의 미니 차트 2종 (docs/6 "링 진행·미니 바 차트" 의 2차 분).

무엇을 그리는가

    UsageCard    사용 한도와 비용. 스트림의 `rate_limit_event` 가 싣고 오는
                 5시간/7일 utilization 두 값과, `result` 이벤트의
                 `total_cost_usd` 로 만든 이 대화 누적 비용이다. 그 필드는
                 턴 하나의 값이 아니라 **세션 누적**이라 더하지 않는다
                 (`UsageCard.add_cost` docstring 의 실측).
    CollectCard  제공자별 수집 회차. 프로필 workspace 아래 `collected/` 의
                 사이드카(`collect_meta.json`)를 세어 만든다.

왜 새 의존을 들이지 않는가
    차트 라이브러리를 넣으면 QGIS 번들 파이썬에 휠을 깔아야 하고, 그것은
    플러그인 설치 경로가 아니다. 그릴 것이 막대 하나뿐이라 QPainter 로
    충분하다(`MiniGaugeBar`).

왜 세로 막대가 아니라 가로 막대인가
    예시 원본(docs/ui_pass2_refs/3.png)의 미니 바 차트는 세로다. 이 독은
    가장 좁을 때 본문 뷰포트가 311 px 이고(하네스 88 W8 실측), 그 폭에서
    세로 막대 밑에 제공자 이름을 붙이면 이름이 잘린다. 그래서 막대를
    눕히고 이름을 왼쪽에 둔다 - 읽히는 것이 먼저다.

왜 글자를 QPainter 로 안 그리는가
    offscreen QPA 에서는 `QFontDatabase` 가 비어 `drawText` 가 예외 없이
    아무것도 그리지 않는다(README 5, S7a 실측). 글자는 전부 QLabel 이고
    QPainter 는 면만 칠한다 - 그래서 하네스가 글자를 위젯 창구로 읽는다.

색
    새 색을 만들지 않는다. 전부 `theme.all_tokens()` 에 이미 있는 값이고
    하드코딩 hex 가 0 인 것이 이 모듈의 계약이다(하네스 92 가 단정한다).

폭
    이 카드들은 독 최소 폭을 밀어 올리면 안 된다(임계 480, 하네스 47 W1).
    줄바꿈 라벨은 전부 최소 폭 1 이고(README 5: QLabel 최소 폭은 "가장 긴
    낱말"), 막대 위젯도 최소 폭 1 이다.

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog, 중첩
이벤트 루프. Qt import 는 전부 qgis.PyQt 셰임 경로로 한다(설계 7-4).
"""

import os

from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from qgis.PyQt.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from . import theme as theme_mod

# ----------------------------------------------------------------------
# 문구 (사용자 노출. 내부 용어 금지 - docs/6 U15)
# ----------------------------------------------------------------------

USAGE_CARD_TITLE = "사용량"
USAGE_FIVE_HOUR_LABEL = "5시간"
USAGE_SEVEN_DAY_LABEL = "7일"
USAGE_PERCENT_FMT = "%d%%"
USAGE_COST_FMT = "이번 대화 누적 %s"
USAGE_COST_VALUE_FMT = "$%.4f"
USAGE_EMPTY = "아직 사용량 정보가 없습니다. 답변을 한 번 받으면 표시됩니다."

# API 모드 토큰 행(0.7.0, docs/13 5-4). **달러는 띄우지 않는다.**
#
# 왜 금액을 안 적는가: `result.total_cost_usd` 가 실려 오는 것은 Claude Code
# 가 계산해 주기 때문이고 **API 응답에는 금액이 없다.** 금액을 띄우려면
# 단가표를 플러그인에 박아야 하고 단가는 바뀐다. 플러그인이 한 번 출하되면
# 그 숫자가 몇 달 그대로 남아 사용자에게 **틀린 금액**을 보여 준다. 검증할
# 수 없는 값을 UI 에 쓰지 않는다는 규칙이 여기 적용된다.
USAGE_TOKENS_TOTAL_FMT = "누적 토큰 입력 %s . 출력 %s . 턴 %d"
USAGE_TOKENS_LAST_FMT = "직전 턴 입력 %s . 출력 %s"

# 값이 없을 때 적는 것. **0 을 적지 않는다** - 0 은 "안 썼다" 로 읽히고
# 그것은 거짓이다. OpenAI 호환 모드는 `stream_options` 를 안 보내므로
# usage 가 대개 오지 않는다(docs/13 2-2-1).
USAGE_TOKENS_NONE = "-"
USAGE_TIP = (
    "Claude 가 보내 주는 사용 한도 정보입니다. 5시간 창과 7일 창의 사용 "
    "비율이고, 비용은 이번 대화에서 지금까지 쓴 금액입니다."
)

COLLECT_CARD_TITLE = "수집 통계"
COLLECT_SUMMARY_FMT = "제공자 %d곳 . 수집 %d회"
COLLECT_COUNT_FMT = "%d회"
COLLECT_EMPTY = "아직 수집한 자료가 없습니다."
COLLECT_TIP = (
    "공공데이터 수집 산출물 폴더를 세어 그린 값입니다. 제공자마다 몇 번 "
    "받았는지를 보여 줍니다."
)

# 사이드카 파일 이름. 수집 서버가 회차마다 산출 폴더에 한 개 쓴다
# (collect_server.py `collect_meta.json`). 이 파일이 있는 폴더만 "한 번
# 수집했다" 로 센다 - 중간에 끊긴 폴더를 세지 않기 위함이다.
SIDECAR_NAME = "collect_meta.json"

# 산출물 고정 하위 폴더. 수집 서버의 `COLLECTED_SUBDIR` 과 같은 값이어야
# 한다 - 갈라지면 UI 가 빈 통계를 그린다.
COLLECTED_SUBDIR = "collected"

# 한 번 훑을 때 보는 산출 폴더 수 상한. 수집이 쌓여도 UI 스레드가 디스크를
# 오래 잡지 않게 한다(렌더 틱 예산, docs/6 제약 3).
SCAN_DIR_LIMIT = 2000

# ----------------------------------------------------------------------
# 치수 (px). 글꼴 크기를 고정하지 않는 것과 같은 이유로 최소한만 박는다.
# ----------------------------------------------------------------------

GAUGE_HEIGHT = 8
GAUGE_RADIUS = 4
GAUGE_MIN_W = 1
CARD_PADDING = 8
CARD_SPACING = 4
ROW_SPACING = 6

# 값이 0 이어도 막대가 "있다" 는 것은 보여야 한다. 0 이면 아예 안 그리는
# 쪽은 "아직 안 쟀다" 와 구분이 안 된다.
MIN_FILL_RATIO = 0.02


def track_token_name(dark):
    """게이지 바탕 띠에 쓸 토큰 이름 (테마별).

    막대는 장식이 아니라 **값을 전하는 면**이라 채움과 바탕이 3:1 로 갈려야
    한다(WCAG 1.4.11). 그런데 라이트에서 `divider`(#cbd5e1)를 띠로 쓰면
    브랜드 오렌지와 1.546 이고, 그라데이션 끝(#ff6b35)과는 1.910 이다
    (실측). 오렌지의 상대 휘도가 중간이라 산술로 상한이 닫힌다 - 3:1 을
    넘기려면 띠의 휘도가 0.077 이하여야 하므로 **밝은 띠로는 불가능**하다.
    그래서 라이트에서는 캡션색(#334155)을 띠로 쓴다(4.510 / 3.652).

    다크의 `divider`(#2c4870)는 이미 4.033 / 3.266 이라 그대로 둔다.

    새 색은 0 이다 - 둘 다 0.2.2 에서 이미 측정된 토큰이다. 하네스 92 K2 가
    이 함수를 **그대로 불러** 같은 선택으로 대비를 잰다(판정식이 두 벌이면
    갈라진다).

    Args:
        dark: 다크 테마인가.

    Returns:
        str: `theme.all_tokens()` 의 키 이름.
    """
    return "divider" if dark else "caption_fg"


def collected_counts(workspace, limit=SCAN_DIR_LIMIT):
    """제공자별 수집 회차 수를 산출물 폴더에서 센다.

    폴더 구조는 수집 서버가 정한 것이다(collect_server `_collect`):
    `<workspace>/collected/<제공자>/<데이터셋>/<시각>/collect_meta.json`.
    서버를 고치지 않고 **이미 디스크에 있는 산출 구조만** 읽는다.

    Args:
        workspace: 프로필 workspace 폴더. 빈 문자열이면 빈 결과다.
        limit: 셀 산출 폴더 수 상한.

    Returns:
        tuple: (dict 제공자 -> 회차 수, 총 회차 수). 폴더가 없거나 읽을 수
            없으면 ({}, 0) 이다 - 통계가 없다고 독이 멈추지 않는다.
    """
    counts = {}
    total = 0
    root = os.path.join(str(workspace or ""), COLLECTED_SUBDIR)
    if not workspace or not os.path.isdir(root):
        return counts, 0
    try:
        providers = sorted(os.listdir(root))
    except OSError:
        return counts, 0
    for provider in providers:
        pdir = os.path.join(root, provider)
        if not os.path.isdir(pdir):
            continue
        n = 0
        try:
            datasets = sorted(os.listdir(pdir))
        except OSError:
            continue
        for dataset in datasets:
            ddir = os.path.join(pdir, dataset)
            if not os.path.isdir(ddir):
                continue
            try:
                stamps = sorted(os.listdir(ddir))
            except OSError:
                continue
            for stamp in stamps:
                if total >= limit:
                    break
                if os.path.isfile(os.path.join(ddir, stamp, SIDECAR_NAME)):
                    n += 1
                    total += 1
        if n:
            counts[provider] = n
    return counts, total


def usage_from_event(event):
    """`rate_limit_event` 한 건에서 두 창의 사용 비율을 꺼낸다.

    실측 녹화본(`tests/fixtures/s2_live_261010_005950.jsonl`)의 모양을 그대로
    읽는다 - `rate_limit_info.unifiedWindows.{five_hour,seven_day}.utilization`.
    백엔드는 이 값을 경고 한 줄로만 쓰고 수치를 보관하지 않으므로(설계 9 의
    "수치 표시는 비범위"), UI 가 배치에서 직접 읽는다. 백엔드를 고치지 않는다.

    Args:
        event: 스트림 이벤트 dict.

    Returns:
        tuple: (five_hour, seven_day). 각각 0~1 실수 또는 None.
    """
    if not isinstance(event, dict):
        return None, None
    info = event.get("rate_limit_info")
    if not isinstance(info, dict):
        return None, None
    windows = info.get("unifiedWindows")
    if not isinstance(windows, dict):
        return None, None
    out = []
    for name in ("five_hour", "seven_day"):
        win = windows.get(name)
        value = win.get("utilization") if isinstance(win, dict) else None
        out.append(float(value) if isinstance(value, (int, float)) else None)
    return out[0], out[1]


def usage_tokens_from_event(event):
    """`result` 한 건이 싣고 온 `usage` 에서 입출력 토큰을 꺼낸다(0.7.0).

    **키가 없으면 None 이다.** 0 으로 떨어뜨리지 않는 이유는 "안 왔다" 와
    "0 이었다" 가 다른 사실이기 때문이다 - API 백엔드는 모르는 키를 넣지
    않는 계약이고(`apiclient` 번역기의 `usage()`), UI 는 그 자리에 "-" 를
    적는다.

    Args:
        event: `result` 이벤트 dict.

    Returns:
        tuple: (input_tokens, output_tokens). 각각 int 또는 None.
    """
    if not isinstance(event, dict):
        return None, None
    usage = event.get("usage")
    if not isinstance(usage, dict):
        return None, None
    out = []
    for name in ("input_tokens", "output_tokens"):
        value = usage.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            out.append(None)
        else:
            out.append(value)
    return out[0], out[1]


def cost_from_event(event):
    """`result` 한 건이 싣고 온 `total_cost_usd`. 없으면 None.

    **이 값은 그 턴의 비용이 아니라 세션 누적**이다(V52 B7 실측). 파서는
    원문을 그대로 돌려주고, 누계로 접는 규칙은 `UsageCard.add_cost` 가
    맡는다 - 파서가 차액을 계산하면 한 건만 놓쳐도 영구히 틀어진다.

    Args:
        event: 스트림 이벤트 dict.

    Returns:
        float 또는 None.
    """
    if not isinstance(event, dict):
        return None
    value = event.get("total_cost_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class MiniGaugeBar(QWidget):
    """0~1 비율 하나를 가로 막대로 그리는 위젯.

    면만 칠한다 - 글자는 곁의 QLabel 이 맡는다(모듈 docstring 의 이유).
    색은 자기가 정하지 않고 자기 팔레트의 휘도로 테마를 가른 뒤 토큰 층에서
    꺼낸다(`theme.GradientBorderFrame` 과 같은 관용구). 그래서 U2 로 테마를
    강제하면 막대도 함께 따라온다.

    장식이 아니라 **값을 전하는** 면이라 바탕과의 대비가 필요하다. 쓰는 색이
    0.2.2 에서 이미 측정된 토큰뿐이라 새 대비쌍이 생기지 않는다.
    """

    def __init__(self, parent=None):
        """빈 막대를 만든다. 값은 `set_ratio` 가 넣는다."""
        super().__init__(parent)
        self._ratio = None
        self.setFixedHeight(GAUGE_HEIGHT)
        # 줄지 않는 최소 폭을 만들면 그것이 그대로 독 최소 폭이 된다
        # (README 5 "Qt 최소 폭은 줄지 않는 것들이 정한다").
        self.setMinimumWidth(GAUGE_MIN_W)

    def set_ratio(self, ratio):
        """비율을 넣고 다시 그린다.

        Args:
            ratio: 0~1 실수 또는 None(미측).

        Returns:
            float or None: 0~1 로 자른 값.
        """
        if ratio is None:
            self._ratio = None
        else:
            self._ratio = max(0.0, min(1.0, float(ratio)))
        self.update()
        return self._ratio

    def ratio(self):
        """지금 비율. 하네스가 읽는 창구다."""
        return self._ratio

    def bar_colors(self):
        """(바탕 hex, 시작 hex, 끝 hex). 하네스가 읽는 창구다."""
        dark = theme_mod.is_dark_palette(self.palette())
        tok = theme_mod.all_tokens(dark)
        return (tok[track_token_name(dark)], tok["primary_bg"],
                tok["primary_hover_bg"])

    def paintEvent(self, event):  # noqa: N802 - Qt 가 요구하는 고정 이름
        """바탕 띠를 깔고 그 위에 비율만큼 그라데이션을 채운다."""
        super().paintEvent(event)
        track_hex, start_hex, end_hex = self.bar_colors()
        rect = QRectF(self.rect())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        track = QPainterPath()
        track.addRoundedRect(rect, GAUGE_RADIUS, GAUGE_RADIUS)
        painter.fillPath(track, QColor(track_hex))
        if self._ratio is not None:
            width = rect.width() * max(self._ratio, MIN_FILL_RATIO)
            fill_rect = QRectF(rect.left(), rect.top(), width, rect.height())
            grad = QLinearGradient(rect.left(), rect.top(),
                                   rect.right(), rect.top())
            grad.setColorAt(0.0, QColor(start_hex))
            grad.setColorAt(1.0, QColor(end_hex))
            fill = QPainterPath()
            fill.addRoundedRect(fill_rect, GAUGE_RADIUS, GAUGE_RADIUS)
            painter.fillPath(fill, grad)
        painter.end()


class _ChartCard(QFrame):
    """차트 카드 둘의 공통 껍데기 (제목 + 본문 + 빈 상태 자리표시).

    빈 상태를 **숨김이 아니라 자리표시**로 둔다. 숨기면 [통계] 로 들어온
    사용자가 빈 화면을 보고 "고장" 으로 읽는다 - 왜 비어 있고 언제 채워지는지
    한 줄로 말하는 쪽이 모달을 못 쓰는 이 독의 안내 방식과 같다.
    """

    def __init__(self, title, object_name, tip, empty_text, parent=None):
        """카드 하나를 만든다.

        Args:
            title: 제목 캡션.
            object_name: qss 가 면을 거는 이름.
            tip: 툴팁 전문.
            empty_text: 데이터가 없을 때의 한 줄.
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.NoFrame)
        self.setToolTip(tip)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(CARD_PADDING, CARD_PADDING,
                                 CARD_PADDING, CARD_PADDING)
        outer.setSpacing(CARD_SPACING)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName(object_name + "Title")
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(1)
        theme_mod.set_role(self.title_label, theme_mod.ROLE_CAPTION)
        outer.addWidget(self.title_label)

        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(CARD_SPACING)
        outer.addWidget(self.body)

        self.empty_label = QLabel(empty_text, self)
        self.empty_label.setObjectName(object_name + "Empty")
        self.empty_label.setWordWrap(True)
        self.empty_label.setMinimumWidth(1)
        theme_mod.set_role(self.empty_label, theme_mod.ROLE_MUTED)
        outer.addWidget(self.empty_label)

        self._show_empty(True)

    def _show_empty(self, empty):
        """빈 상태와 본문 중 하나만 띄운다.

        Args:
            empty: 비어 있는가.

        Returns:
            bool: 빈 상태인가.
        """
        self.empty_label.setVisible(bool(empty))
        self.body.setVisible(not empty)
        return bool(empty)

    def is_empty(self):
        """빈 상태인가. 하네스가 읽는 창구다."""
        return not self.empty_label.isHidden()


class UsageCard(_ChartCard):
    """사용 한도 2창 + 이번 대화 누적 비용 (docs/6 2절 "미니 바 차트" 분).

    지표는 사용자 결정(2026-10-21)이다 - 5시간/7일 사용 비율과 비용 합.
    둘 다 **공짜 신호**다. 비율은 스트림이 알아서 보내 오고(README 5
    `rate_limit_event` 행) 비용은 턴이 끝날 때 오는 result 가 싣는다.
    수치를 받으려고 모델을 더 부르지 않는다.
    """

    def __init__(self, parent=None):
        """빈 사용량 카드를 만든다."""
        super().__init__(USAGE_CARD_TITLE, "UpwiseChatUsageCard", USAGE_TIP,
                         USAGE_EMPTY, parent)
        self._five_hour = None
        self._seven_day = None
        # 카드에 찍히는 값. 항상 `_cost_carried + _cost_session` 이다.
        self._cost_usd = 0.0
        self._cost_turns = 0
        # 끝난 세션들의 마지막 누적값 합. 백엔드가 재시작하면 이쪽으로 접는다.
        self._cost_carried = 0.0
        # 현 세션의 누적값(result 의 total_cost_usd 최신값). 더하지 않는다.
        self._cost_session = 0.0
        # 현 세션 식별자. None 은 "아직 어느 세션도 못 봤다" 다.
        self._cost_session_id = None

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(ROW_SPACING)
        grid.setVerticalSpacing(CARD_SPACING)
        # 이름 칸은 줄지 않아도 되는 짧은 글자라 그대로 두고, 늘어나는 것은
        # 막대 칸 하나뿐이다. 그래야 좁은 독에서 막대만 줄어든다.
        grid.setColumnStretch(1, 1)
        self.five_hour_bar = self._add_row(grid, 0, USAGE_FIVE_HOUR_LABEL,
                                           "UpwiseChatUsageFiveHour")
        self.seven_day_bar = self._add_row(grid, 1, USAGE_SEVEN_DAY_LABEL,
                                           "UpwiseChatUsageSevenDay")
        self.body_layout.addLayout(grid)

        self.cost_label = QLabel("", self.body)
        self.cost_label.setObjectName("UpwiseChatUsageCost")
        self.cost_label.setWordWrap(True)
        self.cost_label.setMinimumWidth(1)
        theme_mod.set_role(self.cost_label, theme_mod.ROLE_MUTED)
        self.body_layout.addWidget(self.cost_label)

        # ----- API 모드 토큰 행 2개(0.7.0, docs/13 5-4) -----
        #
        # 모드에 따라 행 구성을 가른다. Claude 모드에서는 숨어 있고
        # (그 모드의 `result` 에는 우리가 읽는 `usage` 모양이 없다)
        # API 모드에서는 게이지와 USD 행이 숨고 이 둘이 보인다.
        self._api_mode = False
        self._tok_input = None
        self._tok_output = None
        self._tok_turns = 0
        self._tok_last_input = None
        self._tok_last_output = None

        self.tokens_label = QLabel("", self.body)
        self.tokens_label.setObjectName("UpwiseChatUsageTokens")
        self.tokens_label.setWordWrap(True)
        self.tokens_label.setMinimumWidth(1)
        theme_mod.set_role(self.tokens_label, theme_mod.ROLE_MUTED)
        self.body_layout.addWidget(self.tokens_label)

        self.tokens_last_label = QLabel("", self.body)
        self.tokens_last_label.setObjectName("UpwiseChatUsageTokensLast")
        self.tokens_last_label.setWordWrap(True)
        self.tokens_last_label.setMinimumWidth(1)
        theme_mod.set_role(self.tokens_last_label, theme_mod.ROLE_CAPTION)
        self.body_layout.addWidget(self.tokens_last_label)
        self.tokens_label.setVisible(False)
        self.tokens_last_label.setVisible(False)

        self._refresh_text()

    def _add_row(self, grid, row, text, name):
        """이름 + 막대 + 퍼센트 한 줄을 격자에 넣는다.

        Returns:
            MiniGaugeBar: 그 줄의 막대.
        """
        label = QLabel(text, self.body)
        label.setObjectName(name + "Label")
        theme_mod.set_role(label, theme_mod.ROLE_MUTED)
        grid.addWidget(label, row, 0)

        bar = MiniGaugeBar(self.body)
        bar.setObjectName(name)
        grid.addWidget(bar, row, 1)

        value = QLabel("", self.body)
        value.setObjectName(name + "Value")
        theme_mod.set_role(value, theme_mod.ROLE_CAPTION)
        grid.addWidget(value, row, 2)
        setattr(self, "_" + name + "_value", value)
        return bar

    def _value_label(self, name):
        """막대 이름에 딸린 퍼센트 라벨."""
        return getattr(self, "_" + name + "_value")

    def _refresh_text(self):
        """퍼센트와 비용 문구를 지금 값으로 다시 쓴다."""
        for name, ratio in (("UpwiseChatUsageFiveHour", self._five_hour),
                            ("UpwiseChatUsageSevenDay", self._seven_day)):
            label = self._value_label(name)
            label.setText("" if ratio is None
                          else USAGE_PERCENT_FMT % int(round(ratio * 100)))
        self.cost_label.setText(
            USAGE_COST_FMT % (USAGE_COST_VALUE_FMT % self._cost_usd))
        self.tokens_label.setText(USAGE_TOKENS_TOTAL_FMT % (
            self._token_text(self._tok_input),
            self._token_text(self._tok_output), self._tok_turns))
        self.tokens_last_label.setText(USAGE_TOKENS_LAST_FMT % (
            self._token_text(self._tok_last_input),
            self._token_text(self._tok_last_output)))

    @staticmethod
    def _token_text(value):
        """토큰 수 하나를 글자로. None 은 "-" 다(0 을 적지 않는다)."""
        return USAGE_TOKENS_NONE if value is None else "%d" % value

    def set_api_mode(self, api_mode):
        """행 구성을 모드에 맞춘다(0.7.0, docs/13 5-4).

        API 모드에서 숨기는 것과 그 이유
            5시간/7일 게이지  `rate_limit_event` 가 오지 않는다. 빈 게이지를
                두면 "한도를 다 썼다" 로도 "0% 다" 로도 읽힌다.
            누적 비용(USD)  API 응답에 금액이 없다(모듈 상수 주석).

        Args:
            api_mode: API 직결 백엔드인가.

        Returns:
            bool: 적용된 모드.
        """
        self._api_mode = bool(api_mode)
        for bar_name in ("five_hour_bar", "seven_day_bar"):
            bar = getattr(self, bar_name, None)
            if bar is not None:
                bar.setVisible(not self._api_mode)
        for name in ("UpwiseChatUsageFiveHour", "UpwiseChatUsageSevenDay"):
            self._value_label(name).setVisible(not self._api_mode)
            label = self.findChild(QLabel, name + "Label")
            if label is not None:
                label.setVisible(not self._api_mode)
        self.cost_label.setVisible(not self._api_mode)
        self.tokens_label.setVisible(self._api_mode)
        self.tokens_last_label.setVisible(self._api_mode)
        return self._api_mode

    def add_tokens(self, input_tokens, output_tokens):
        """턴 1개의 토큰 수를 누계에 넣는다(0.7.0).

        **모르는 값은 0 으로 세지 않는다.** 누계는 값이 온 턴만 더하고,
        직전 턴 칸은 안 온 값을 None 으로 둬 "-" 로 그려진다.

        Args:
            input_tokens: 입력 토큰 수 또는 None.
            output_tokens: 출력 토큰 수 또는 None.

        Returns:
            int: 센 턴 수.
        """
        self._tok_turns += 1
        self._tok_last_input = input_tokens
        self._tok_last_output = output_tokens
        if input_tokens is not None:
            self._tok_input = (self._tok_input or 0) + int(input_tokens)
        if output_tokens is not None:
            self._tok_output = (self._tok_output or 0) + int(output_tokens)
        self._refresh_text()
        # 토큰만 와도 보여 줄 것이 생긴다.
        self._show_empty(False)
        return self._tok_turns

    def set_usage(self, five_hour, seven_day):
        """두 창의 사용 비율을 넣는다.

        Args:
            five_hour: 0~1 실수 또는 None.
            seven_day: 0~1 실수 또는 None.

        Returns:
            bool: 하나라도 값이 들어왔는가.
        """
        if five_hour is not None:
            self._five_hour = self.five_hour_bar.set_ratio(five_hour)
        if seven_day is not None:
            self._seven_day = self.seven_day_bar.set_ratio(seven_day)
        self._refresh_text()
        got = self._five_hour is not None or self._seven_day is not None
        if got:
            self._show_empty(False)
        return got

    def _fold_session(self, session_id):
        """세션 경계. 직전 세션 누적을 누계에 접고 현 세션을 0 으로 둔다.

        Args:
            session_id: 새 세션 식별자. None 이면 식별자 미상으로 둔다.

        Returns:
            float: 접은 뒤의 누계(끝난 세션들의 합).
        """
        self._cost_carried += self._cost_session
        self._cost_session = 0.0
        self._cost_session_id = session_id
        return self._cost_carried

    def note_session(self, session_id):
        """`system`/`init` 이 알려 준 세션 식별자를 받아 둔다.

        백엔드가 재시작하거나 CLI 가 새 세션을 열면 `total_cost_usd` 가 0 부터
        다시 센다고 본다 - **미측 전제**다(세션 두 개가 비용을 싣는 실녹화가
        아직 없다, V54-02. 새 세션이 0 이 아니라 이어받는다면 접기는 과대로
        기운다). 그 경계를 init 에서 먼저 잡아 두면 새 세션의 첫 result 가
        오기 전에도 카드가 맞는다.

        **같은 세션 id 로 오는 init 은 경계가 아니다.** 녹화본
        s2_live_261010_005950.jsonl 은 한 세션 안에서 init 을 두 번 싣고
        (L1, L42) 그 뒤 result 의 누적이 계속 커진다 - init 만 보고 접으면
        같은 세션 비용을 두 번 센다.

        Args:
            session_id: `session_id` 원문. None 이면 아무것도 하지 않는다.

        Returns:
            bool: 세션 경계로 판정했는가.
        """
        if session_id is None or session_id == self._cost_session_id:
            return False
        if self._cost_session_id is None:
            # 첫 세션. 접을 직전 값이 없다.
            self._cost_session_id = session_id
            return False
        self._fold_session(session_id)
        self._refresh_text()
        return True

    def add_cost(self, usd, session_id=None):
        """`result` 가 싣고 온 세션 누적 비용을 카드에 반영한다.

        왜 더하지 않는가
            `result.total_cost_usd` 는 그 턴 하나의 비용이 아니라 **세션
            누적**이다(V52 B7 실측: 한 세션의 result 3건이 0.471981 ->
            0.489733 -> 0.501717 로 커지고 modelUsage 토큰도 같이 누적된다).
            result 마다 더하면 턴 수에 따라 과대해진다(실측 2.92배).

        그래서 현 세션분은 **최신값**으로 두고, 세션이 바뀔 때만 직전 값을
        누계에 접는다. 카드 문구("이번 대화 누적")의 뜻은 그대로다.

        세션 경계는 두 축으로 가른다. ① 식별자가 바뀌었다. ② 식별자를 못
        싣는 경로에서 값이 **줄었다** - 세션 누적은 단조 증가라 감소를
        설명하는 것은 새 세션뿐이다.

        Args:
            usd: `result` 의 `total_cost_usd` 원문.
            session_id: 그 result 의 `session_id`. None 이면 현 세션으로 본다.

        Returns:
            float: 카드에 찍히는 누적 비용.
        """
        if usd is None:
            return self._cost_usd
        value = float(usd)
        key = self._cost_session_id if session_id is None else session_id
        # 감소를 경계로 읽는 것은 식별자를 못 싣는 경로뿐이다(docstring 축 2).
        # 식별자가 같은데 값이 준 경우까지 접으면 직전 값이 누계로 더해져
        # 0.6.1 과 같은 방향의 과대가 된다(V54 P2-1).
        if key != self._cost_session_id or (
                session_id is None and value < self._cost_session):
            self._fold_session(key)
        # 같은 세션에서 역주행한 result 가 와도 최댓값을 지킨다(순서 보장이
        # 없는 드레인 배치에서 카드가 뒤로 가지 않게).
        self._cost_session = max(self._cost_session, value)
        self._cost_usd = self._cost_carried + self._cost_session
        self._cost_turns += 1
        self._refresh_text()
        # 비용만 와도 보여 줄 것이 생긴다. 한도 정보가 늦게 오는 회차에서
        # 빈 자리표시를 그대로 두면 "비용도 없다" 로 읽힌다.
        self._show_empty(False)
        return self._cost_usd

    def reset(self):
        """새 대화. 누적을 0 으로 되돌리고 빈 상태로 간다 (U16 과 같은 축).

        한도 비율은 계정 단위라 대화와 무관하지만, 다음 `rate_limit_event`
        가 곧 다시 실어 온다. 비용과 섞어 두면 "이번 대화 누적" 이라는
        문구가 거짓이 되므로 둘을 같이 비운다.

        Returns:
            float: 되돌린 뒤의 누적 비용(0.0).
        """
        self._five_hour = self.five_hour_bar.set_ratio(None)
        self._seven_day = self.seven_day_bar.set_ratio(None)
        self._cost_usd = 0.0
        self._cost_turns = 0
        # 세션 추적도 함께 비운다. 새 대화는 새 세션을 열고, 그 init 을
        # 경계로 다시 세기 시작해야 한다.
        self._cost_carried = 0.0
        self._cost_session = 0.0
        self._cost_session_id = None
        # 토큰 누계도 함께 비운다(0.7.0). "누적" 문구가 대화 단위이므로
        # 비용과 같은 자리에서 리셋돼야 한다.
        self._tok_input = None
        self._tok_output = None
        self._tok_turns = 0
        self._tok_last_input = None
        self._tok_last_output = None
        self._refresh_text()
        self._show_empty(True)
        return self._cost_usd

    def feed_batch(self, batch):
        """드레인 배치 하나를 훑어 두 지표를 갱신한다.

        독의 `_on_events` 가 부른다. 배치 원문을 읽는 쪽이 UI 인 이유는
        `usage_from_event` docstring 에 있다.

        Args:
            batch: process.StreamLine 목록(.event 가 dict).

        Returns:
            tuple: (한도 이벤트 수, 비용 이벤트 수).
        """
        rate_n = 0
        cost_n = 0
        for line in batch or ():
            event = getattr(line, "event", None)
            if not isinstance(event, dict):
                continue
            etype = event.get("type")
            if etype == "rate_limit_event":
                five, seven = usage_from_event(event)
                if self.set_usage(five, seven):
                    rate_n += 1
            elif etype == "result":
                usd = cost_from_event(event)
                if usd is not None:
                    self.add_cost(usd, event.get("session_id"))
                    cost_n += 1
                if self._api_mode:
                    # API 모드 토큰 행(0.7.0). 금액 키가 없는 쪽이라
                    # 위 분기가 안 돌고, 턴 수를 여기서 센다. 모드를 보는
                    # 이유는 Claude 모드의 `result.usage` 모양을 우리가
                    # 재지 않았기 때문이다 - 안 쟀으면 읽지 않는다.
                    tin, tout = usage_tokens_from_event(event)
                    self.add_tokens(tin, tout)
                    cost_n += 1
            elif etype == "system" and event.get("subtype") == "init":
                # 세션 경계 후보. 비용 이벤트가 아니므로 셈에 넣지 않는다 -
                # `cost_events` 는 "턴이 몇 번 끝났나" 를 세는 창구다.
                self.note_session(event.get("session_id"))
        return rate_n, cost_n

    def stats(self):
        """하네스가 읽는 한 줄 요약."""
        return {
            "empty": self.is_empty(),
            "five_hour": self._five_hour,
            "seven_day": self._seven_day,
            "cost_usd": round(self._cost_usd, 6),
            "cost_turns": self._cost_turns,
            "five_hour_text": self._value_label(
                "UpwiseChatUsageFiveHour").text(),
            "seven_day_text": self._value_label(
                "UpwiseChatUsageSevenDay").text(),
            "cost_text": self.cost_label.text(),
            # 0.7.0 API 모드 행. 하네스 110 G4 가 읽는다.
            "api_mode": self._api_mode,
            "tokens_in": self._tok_input,
            "tokens_out": self._tok_output,
            "tokens_turns": self._tok_turns,
            "tokens_text": self.tokens_label.text(),
            "tokens_last_text": self.tokens_last_label.text(),
            "tokens_visible": not self.tokens_label.isHidden(),
            "cost_visible": not self.cost_label.isHidden(),
            "gauge_visible": not self.five_hour_bar.isHidden(),
        }


class CollectCard(_ChartCard):
    """제공자별 수집 회차 막대 (docs/6 2절 "미니 바 차트" 분).

    데이터는 **이미 디스크에 있는 산출 구조**다. 수집 서버를 고치지 않고
    사이드카가 있는 폴더를 센다(`collected_counts`). 서버가 새 창구를
    만들어 주기를 기다리지 않는 쪽을 고른 이유는 그 서버가 이 회차의 수정
    금지 대상이기 때문이다.
    """

    def __init__(self, parent=None):
        """빈 수집 통계 카드를 만든다."""
        super().__init__(COLLECT_CARD_TITLE, "UpwiseChatCollectCard",
                         COLLECT_TIP, COLLECT_EMPTY, parent)
        self._counts = {}
        self._total = 0
        self._rows = []

        self.rows_host = QWidget(self.body)
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(CARD_SPACING)
        self.body_layout.addWidget(self.rows_host)

        self.summary_label = QLabel("", self.body)
        self.summary_label.setObjectName("UpwiseChatCollectSummary")
        self.summary_label.setWordWrap(True)
        self.summary_label.setMinimumWidth(1)
        theme_mod.set_role(self.summary_label, theme_mod.ROLE_MUTED)
        self.body_layout.addWidget(self.summary_label)

    def _clear_rows(self):
        """막대 줄을 전부 걷어낸다. 제공자 집합이 바뀌면 다시 만든다."""
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows = []

    def set_counts(self, counts, total=None):
        """제공자별 회차 수를 넣고 막대를 다시 세운다.

        Args:
            counts: dict 제공자 -> 회차 수.
            total: 총 회차 수. None 이면 값들의 합이다.

        Returns:
            int: 그린 막대 줄 수.
        """
        counts = dict(counts or {})
        self._counts = counts
        self._total = int(total if total is not None else sum(counts.values()))
        self._clear_rows()
        if not counts:
            self.summary_label.setText("")
            self._show_empty(True)
            return 0
        # 큰 쪽부터 세운다. 같으면 이름 순이다 - 회차마다 순서가 흔들리면
        # 사용자가 같은 그림을 두 번 못 본다.
        order = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        top = max(counts.values()) or 1
        for provider, n in order:
            self._rows.append(self._add_row(provider, n, top))
        self.summary_label.setText(
            COLLECT_SUMMARY_FMT % (len(counts), self._total))
        self._show_empty(False)
        return len(self._rows)

    def _add_row(self, provider, n, top):
        """제공자 한 줄(이름 + 막대 + 회차)을 만든다.

        Returns:
            tuple: (제공자, MiniGaugeBar).
        """
        row = QWidget(self.rows_host)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ROW_SPACING)

        name = QLabel(str(provider), row)
        name.setObjectName("UpwiseChatCollectName")
        # 제공자 id 는 영문 한 덩이라 줄바꿈이 안 먹는다. 최소 폭 1 로 두어
        # 좁은 독에서 레이아웃이 이 글자에 묶이지 않게 한다(README 5).
        name.setMinimumWidth(1)
        theme_mod.set_role(name, theme_mod.ROLE_MUTED)
        layout.addWidget(name)

        bar = MiniGaugeBar(row)
        bar.setObjectName("UpwiseChatCollectBar")
        bar.set_ratio(float(n) / float(top))
        layout.addWidget(bar, 1)

        count = QLabel(COLLECT_COUNT_FMT % int(n), row)
        count.setObjectName("UpwiseChatCollectCount")
        theme_mod.set_role(count, theme_mod.ROLE_CAPTION)
        layout.addWidget(count)

        self.rows_layout.addWidget(row)
        return (str(provider), bar)

    def refresh_from(self, workspace):
        """workspace 를 훑어 다시 그린다.

        Args:
            workspace: 프로필 workspace 폴더.

        Returns:
            int: 총 회차 수.
        """
        counts, total = collected_counts(workspace)
        self.set_counts(counts, total)
        return total

    def stats(self):
        """하네스가 읽는 한 줄 요약."""
        return {
            "empty": self.is_empty(),
            "providers": sorted(self._counts),
            "counts": dict(self._counts),
            "total": self._total,
            "bars": len(self._rows),
            "ratios": [round(bar.ratio() or 0.0, 4)
                       for _name, bar in self._rows],
            "summary_text": self.summary_label.text(),
        }


class StatsPane(QWidget):
    """차트 두 장을 세로로 담는 칸. 바텀 내비 [통계] 가 여닫는다.

    기본은 숨김이다. 독이 뜨자마자 보이면 전사가 그만큼 좁아지고, 그것이
    0.4.0 실기 피드백("배너가 여러 줄이라 채팅창이 좁아졌다")이 고친 축과
    같은 결함이다.
    """

    def __init__(self, parent=None):
        """차트 두 장을 세운다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatStatsPane")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(CARD_SPACING)
        self.usage_card = UsageCard(self)
        layout.addWidget(self.usage_card)
        self.collect_card = CollectCard(self)
        layout.addWidget(self.collect_card)
        self.setVisible(False)

    def stats(self):
        """하네스가 읽는 한 줄 요약."""
        return {
            "visible": not self.isHidden(),
            "usage": self.usage_card.stats(),
            "collect": self.collect_card.stats(),
        }
