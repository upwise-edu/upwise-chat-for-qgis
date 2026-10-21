"""브랜드 팔레트, 테마 판정, 독 루트 스타일시트 조립 (S7 브랜딩).

이 모듈이 맡는 것 세 가지(설계 7-3)

    1. 테마 판정   현재 팔레트의 Window 색 상대 휘도로 다크/라이트를 가른다.
                   QGIS 에 공식 "다크 여부" API 가 없어서 쓰는 표준 관용구다.
    2. 팔레트 토큰 설계 7-3 표의 색을 테마별 dict 로 돌려준다.
    3. qss 조립    resources/style.qss 템플릿을 읽어 토큰을 끼운다.

왜 qss 를 파일로 두고 토큰만 끼우는가
    설계 7-4 가 `resources/style.qss` 를 S7 산출물로 적고 있다. 그런데 토큰은
    테마마다 다르므로 정적 qss 한 장으로는 두 테마를 담을 수 없다. 그래서
    **규칙(선택자)은 파일에, 값(색)은 이 모듈에** 둔다. 파일을 고치면 선택자가,
    이 모듈을 고치면 색이 바뀐다.

왜 독 내용 위젯에만 적용하는가
    설계 7-3 첫 줄이 QGIS 전역 스타일시트를 금지한다. 더 좁혀서 QDockWidget
    자체가 아니라 그 내용 위젯에 건다. QDockWidget 에 스타일시트를 걸면 Qt 가
    제목 줄까지 스타일시트 스타일로 그려서 플랫폼 기본 제목 줄과 버튼 모양이
    바뀐다. 내용 위젯에 걸면 그 위험이 없고 적용 범위는 같다.

색의 근거(실측)
    * 주 버튼 글자색은 네이비다. `#f7931e` 위 흰색은 대비 2.296 으로 소형 텍스트
      AA(4.5) 미달이고 네이비 `#0a1929` 는 7.726 으로 통과한다(V28-27 실계산).
    * 라이트 카드 `#f8fafc` 위 보조 텍스트는 `#475569` 다. 설계 7-3 표의
      `#94a3b8` 는 같은 배경에서 2.451 로 AA 미달이었다(V28-28). 후보를
      `#475569` -> `#334155` 순으로 두고 4.5 를 처음 넘는 것을 채택했다.
    * 다크 카드 `#1e3a5f` 위 `#cbd5e1` 는 7.747 로 통과한다. 그대로 쓴다.

글꼴 크기를 px 로 고정하지 않는다(설계 7-3 마지막 줄). qss 에 font-size 가
없는 것은 하네스가 검사한다.

0.2.2 심미 패스가 더한 것 (UI_TOKENS)
    설계 7-3 표의 토큰 9개는 `tokens()` 가 그대로 돌려준다 - **값도 키도
    바뀌지 않았다**(하네스 16 T2 의 기대값이 그래서 유지된다). 심미 패스가
    새로 쓰는 색은 `ui_tokens()` 로 따로 두고 `build_qss()` 에서 합친다.
    새 색은 전부 WCAG 를 실계산해 하네스 27 의 K 군이 기록한다.

    본문 글자가 올라가는 모든 새 조합은 >= 4.5(소형 AA), 정보를 전하는 새
    경계(바 왼쪽 강조선, 블록 레일)는 >= 3.0 이다. **기존**의 장식 경계
    (카드 테두리 `card_border` 대 `card_bg` = 1.178)는 값을 바꾸지 않았고
    정보를 전하지 않으므로 3.0 대상이 아니다 - 이 구분을 하네스에 박아 둔다.

0.3.x UI 패스 2차 "스타일 배치" 가 더한 것 (U1~U4, U7~U9)
    **새 색을 지어내지 않았다.** 더한 토큰 6개는 전부 README 2절의 로고 팔레트
    실측값(사이트 `global.css` 실측 + 로고 PNG 화소 대조)에서 꺼낸 것이고,
    그 대조는 하네스 48 의 U 군이 로고 자산을 다시 읽어 기록한다.

        user_bg / user_bg_to   U1 말풍선 선형 그라데이션의 두 끝.
                               라이트 = 로고 오렌지 짝(`#f7931e` -> `#ff6b35`,
                               README 2절이 "그라데이션 짝" 이라 적은 그 쌍).
                               다크 = 로고 네이비 마크 짝(`#1e3a5f` -> `#2c4870`).
                               다크에서 오렌지를 쓰지 않는 것은 설계 7-3 마지막
                               불릿(넓은 오렌지 면 금지)을 지키기 위함이다.
        header_glow            U3 헤더 글로우의 중심 색. 실시간 블러가 불가라
                               방사형 그라데이션으로 근사한다(사용자 승인).
        shadow_edge            U8 소프트 섀도 근사. 카드 배경 아래쪽 띠 한 줄로
                               단차를 만든다. QGraphicsDropShadowEffect 는 쓰지
                               않는다(무겁고 렌더 결함 위험 - docs/6 U8).
        window_bg / window_fg / base_bg
                               U2 가 테마를 **독 안에서만** 강제할 때 쓰는 면과
                               글자색. qss 가 아니라 `dock_palette()` 가 쓴다
                               (아래 "왜 팔레트로 강제하는가").

    그라데이션 면 위의 글자는 **두 끝 모두**에 대해 대비를 잰다. 한쪽만 재면
    사용자가 보는 화소의 절반이 미검증으로 남는다(하네스 27 K1 에 쌍 추가).

왜 팔레트로 강제하는가 (U2)
    qss 로 독 내용 위젯 배경만 칠하면 그 안의 평범한 QWidget 컨테이너들은 여전히
    QGIS 팔레트 색으로 자기 면을 그려 얼룩이 생긴다. Qt 에서 **팔레트는 자식에게
    상속**되므로, 독 내용 위젯 하나에 팔레트를 걸면 그 서브트리 전체가 따라온다.
    QGIS 전역(`QgsApplication`)은 건드리지 않으므로 0.2.2 의 전역 무오염이
    유지된다. 모드가 "시스템" 이면 팔레트를 걸지 않는다 - 그때는 0.2.2 와
    글자 하나 다르지 않게 동작해야 한다.

역할 속성 (ROLE_PROPERTY / STATE_PROPERTY)
    qss 선택자를 objectName 으로만 쓰면 같은 모양의 위젯마다 이름을 하나씩
    만들어야 한다. 그래서 되풀이되는 모양(캡션, 보조 텍스트, 경고 텍스트)은
    동적 속성으로 표시하고 속성 선택자로 건다. 속성을 **실행 중에** 바꾸면
    Qt 가 스타일을 다시 계산하지 않으므로 `repolish()` 로 강제한다.

설계 정본: docs/1.mvp_design_v1.md 7-1, 7-3, 7-4
"""

from pathlib import Path

from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from qgis.PyQt.QtWidgets import QFrame

# ----------------------------------------------------------------------
# 브랜드 자산과 문자열
# ----------------------------------------------------------------------

# 헤더 로고를 누르면 여는 주소(설계 7-1 [1]). 툴팁에는 호스트만 적는다.
BRAND_URL = "https://upwise.co.kr"
BRAND_TOOLTIP = "upwise.co.kr"

# 로고 옆 글자. 타일만으로는 24-32 px 에서 상표를 읽기 어렵다.
WORDMARK_TEXT = "UPWISE"

# 패키지 루트 기준 상대경로. metadata.txt 의 icon= 과 같은 방식이다.
LOGO_ASSET_RELPATH = "resources/logo_upwise@2x.png"
QSS_ASSET_RELPATH = "resources/style.qss"

# ----------------------------------------------------------------------
# 색 토큰 (설계 7-3 표 + V28-27/V28-28 실측 정정)
# ----------------------------------------------------------------------

NAVY = "#0a1929"
ORANGE = "#f7931e"
ORANGE_HOVER = "#ff6b35"
ACCENT = "#ffa756"
WHITE = "#ffffff"

CARD_BG_LIGHT = "#f8fafc"
CARD_BORDER_LIGHT = "#e2e8f0"
CARD_BG_DARK = "#1e3a5f"
CARD_BORDER_DARK = "#2c4870"

# 라이트 보조 텍스트 후보. 앞에서부터 `#f8fafc` 위 대비 4.5 를 처음 넘는 것을
# 쓴다(V28-28 의 사전 명세). 실계산에서 `#475569` 가 첫 통과였다.
MUTED_LIGHT_CANDIDATES = ("#475569", "#334155")
MUTED_LIGHT = MUTED_LIGHT_CANDIDATES[0]
MUTED_DARK = "#cbd5e1"

# ----------------------------------------------------------------------
# 0.2.2 심미 패스 토큰. 설계 7-3 표(위)와 **따로** 둔다 - 그 표는 정본이고
# 여기는 그 위에 얹는 층이다. 값 옆 괄호는 실계산 WCAG 대비다(하네스 27 K 군이
# 같은 값을 다시 계산해 기록한다. 여기 주석은 선정 근거이지 증거가 아니다).
# ----------------------------------------------------------------------

# 섹션 캡션. 라이트 9.086 / 다크 13.523 (각 테마 Window 위).
CAPTION_FG_LIGHT = "#334155"
CAPTION_FG_DARK = "#e2e8f0"

# 구분선. **장식 경계**다(정보를 전하지 않는다) - 3:1 대상이 아니다.
DIVIDER_LIGHT = "#cbd5e1"
DIVIDER_DARK = "#2c4870"

# 모델 응답 블록 왼쪽 레일. 사용자 띠와 응답을 가르는 **정보 경계**라
# 3:1 을 지킨다. 양 테마 공통색으로 둘 다 넘기는 값을 골랐다
# (라이트 4.176 / 다크 3.503).
BLOCK_RAIL = "#64748b"

# 사용자 메시지 띠. 글자색을 함께 정한다 - 배경을 우리가 칠했으면 그 위
# 글자색도 우리가 책임진다.
#
# U1(0.3.x): 단색이던 면을 **선형 그라데이션**으로 바꿨다. 두 끝은 로고 팔레트
# 실측값이고 값은 아래 ORANGE/ORANGE_HOVER, CARD_BG_DARK/CARD_BORDER_DARK 를
# 그대로 가리킨다 - 새 색을 만들지 않았다는 뜻이다. 0.2.2 의 `#dbe7f5`(라이트)
# 와 `#24405f`(다크)는 브랜드 밖의 값이어서 "로고 색 그라데이션" 요구를
# (docs/6 U1) 만족시킬 수 없었다.
#
# 글자 대비(실계산): 라이트 7.726 / 6.256, 다크 10.105 / 8.134. 네 값 모두
# 소형 AA(4.5)를 넘는다 - 그라데이션은 양 끝 다 재야 한다.
USER_BG_LIGHT = ORANGE
USER_BG_TO_LIGHT = ORANGE_HOVER
USER_BG_DARK = CARD_BG_DARK
USER_BG_TO_DARK = CARD_BORDER_DARK
USER_FG_LIGHT = "#0a1929"
USER_FG_DARK = "#eaf1f9"

# U3 헤더 글로우의 중심 색. 헤더는 양 테마 공통 네이비 면이라 값도 하나다.
# 네이비 마크의 중간 톤(`#1e3a5f`, 로고 화소 최근접 거리 3)을 쓴다 - 헤더
# 바탕(`#0a1929`)보다 한 단 밝아서 상표 쪽이 들려 보이고, 헤더 위의 글자
# 넷(흰색 11.503 / 칩 7.747 / 성공 6.177 / 실패 5.659 / 액센트 5.978)이
# 이 면에서도 전부 AA 를 넘는다.
HEADER_GLOW = CARD_BG_DARK

# U8 소프트 섀도 근사. 카드 배경 그라데이션의 **아래쪽 띠** 색이다.
# 카드 면 대비 1.419(라이트) / 1.542(다크) - 장식 경계이고 정보를 전하지
# 않으므로 3:1 대상이 아니다(0.2.2 K3 과 같은 구분). 글자가 이 띠에
# 겹칠 수 있으므로 **글자 대비는 잰다**(라이트 캡션 6.974 / 보조 5.104).
SHADOW_EDGE_LIGHT = "#cbd5e1"
SHADOW_EDGE_DARK = "#0a1929"

# U2 가 테마를 독 안에서만 강제할 때 쓰는 면과 글자색.
# 두 Window 값은 0.2.2 하네스(27)가 양 테마 측정 배경으로 쓴 값 그대로다 -
# 그래서 "카드/캡션 대 window" 로 이미 측정된 쌍들이 강제 모드에서도 참이 된다.
# Base(입력칸 면)는 라이트에서 흰색, 다크에서 헤더 네이비를 쓴다.
WINDOW_BG_LIGHT = "#f0f0f0"
WINDOW_BG_DARK = "#1e1e1e"
WINDOW_FG_LIGHT = NAVY
WINDOW_FG_DARK = "#eaf1f9"
BASE_BG_LIGHT = WHITE
BASE_BG_DARK = NAVY

# 위험(거부). 본문 라이트 8.975 / 다크 10.642, 강조선 4.758 / 5.130.
# 라이트 강조선은 chat_view.ERROR_BORDER_COLOR 와 같은 값이다(의도).
DANGER_BG_LIGHT = "#fdeceb"
DANGER_BG_DARK = "#43201d"
DANGER_FG_LIGHT = "#7a2018"
DANGER_FG_DARK = "#f6d7d2"
DANGER_BORDER_LIGHT = "#c0392b"
DANGER_BORDER_DARK = "#e08073"

# 주의(전제조건, 제외, 마커, stale, 포스처 확인).
# 본문 7.856 / 10.107, 강조선 3.891 / 6.194.
WARN_BG_LIGHT = "#fdf3e2"
WARN_BG_DARK = "#3b2f13"
WARN_FG_LIGHT = "#6b4306"
WARN_FG_DARK = "#f3e0bb"
WARN_BORDER_LIGHT = "#b06a00"
WARN_BORDER_DARK = "#dfa94e"

# 헤더 네이비 면 위의 색들. 헤더는 양 테마 공통이라 값도 하나씩이다.
CHIP_FG = "#cbd5e1"          # 11.946 on NAVY
BADGE_OK_FG = "#5fd39b"      # 9.525 on NAVY
BADGE_FAIL_FG = "#ff9b8e"    # 8.726 on NAVY

# 동적 속성 이름. qss 가 `[upwiseRole="caption"]` 처럼 받는다.
ROLE_PROPERTY = "upwiseRole"
STATE_PROPERTY = "upwiseState"
LEVEL_PROPERTY = "upwiseLevel"

# 역할 값. 문자열을 코드 여러 곳에 흩지 않으려고 상수로 둔다.
ROLE_CAPTION = "caption"
ROLE_MUTED = "muted"
ROLE_SECTION = "section"
ROLE_WARN_TEXT = "warnText"
ROLE_DANGER_TEXT = "dangerText"
ROLE_BUSY = "busy"
ROLE_DIVIDER = "divider"

# 프리셋 격자의 버튼(0.4.2, 사용자 실기 피드백 2026-10-17: "텍스트 길이에 비해
# 버튼 영역이 너무 넓습니다"). 이 역할이 하는 일은 **여백 축소 하나**다 -
# 색은 주지 않는다(네이티브 버튼 그대로). qss 규칙이 하나라도 걸리면 Qt 가
# QPushButton 의 네이티브 최소 폭 80 px 바닥을 쓰지 않고 규칙의 상자 모형으로
# 크기를 잰다(실측: 80 -> 48, "수집"). 그 바닥이 짧은 글자 버튼을 넓게 만든
# 원인이었다.
ROLE_PRESET = "preset"

# 배지 상태 값(설계 3-4 의 3상태를 색으로 가른다).
STATE_UNKNOWN = "unknown"
STATE_OK = "ok"
STATE_FAIL = "fail"

# 네 번째 상태(0.3.x UI 패스 2차 U6). 연결 표시에만 쓴다 - "틀렸다" 가 아니라
# "확인이 필요하다" 는 중간값이 필요했다(포트 재점유 의심, 응답 지연).
#
# **새 색을 만들지 않았다.** 이 값은 이미 측정된 `header_accent`(네이비 위
# 액센트 오렌지)로 그려진다. 0.2.2 의 "빨강 = 거부 유일" 체계를 지키려면
# 중간값에 danger 계열을 쓸 수 없고, 주의 축의 색이 헤더 면에 이미 있다.
STATE_WARN = "warn"

# 전제조건 항목 심각도. detect 의 MISSING/UNKNOWN 을 UI 어휘로 옮긴 것이다.
LEVEL_UNMET = "unmet"
LEVEL_UNKNOWN = "unknown"

# ----------------------------------------------------------------------
# U2 테마 모드 (독 내부 한정)
# ----------------------------------------------------------------------

# 3단 값. 문자열을 그대로 QgsSettings 에 적으므로 값을 바꾸면 사용자의 저장된
# 설정이 무효가 된다 - 늘리는 것은 되고 바꾸는 것은 안 된다.
THEME_MODE_SYSTEM = "system"
THEME_MODE_LIGHT = "light"
THEME_MODE_DARK = "dark"

# 세그먼트 컨트롤이 그리는 순서다(왼쪽부터). 기본값은 첫 항목이다.
THEME_MODES = (THEME_MODE_SYSTEM, THEME_MODE_LIGHT, THEME_MODE_DARK)
THEME_MODE_DEFAULT = THEME_MODE_SYSTEM

# 버튼 문구. 내부 용어를 쓰지 않는다(docs/6 U15 원칙).
THEME_MODE_LABELS = {
    THEME_MODE_SYSTEM: "시스템",
    THEME_MODE_LIGHT: "라이트",
    THEME_MODE_DARK: "다크",
}

THEME_MODE_TIPS = {
    THEME_MODE_SYSTEM: "QGIS 테마를 따릅니다.",
    THEME_MODE_LIGHT: "이 창만 밝게 그립니다. QGIS 테마는 바뀌지 않습니다.",
    THEME_MODE_DARK: "이 창만 어둡게 그립니다. QGIS 테마는 바뀌지 않습니다.",
}

# QgsSettings 경로. 접두사는 이 플러그인 것이다(keystore·detect 와 같은 표기).
THEME_MODE_SETTING_KEY = "upwise_chat/ui_theme_mode"

# 헤더 펼침 상태(0.4.x 헤더 최소화). 테마 모드와 **같은 모듈·같은 접두사**에
# 둔다 - 독 머리의 표시 설정을 읽고 쓰는 길이 둘로 갈라지지 않게 하기 위함이다.
HEADER_EXPANDED_SETTING_KEY = "upwise_chat/ui_header_expanded"

# 기본은 접힘이다. 사용자 실기 피드백(2026-10-16, 0.4.0)이 "배너에 추가된
# 기능들이 너무 여러 줄이라 채팅창이 좁아졌다" 였고, 기본을 펼침으로 두면
# 처음 여는 사용자가 보는 화면이 그 피드백 이전과 같아진다.
HEADER_EXPANDED_DEFAULT = False

# 다크/라이트 경계. WCAG 상대 휘도 0.5 를 기준으로 가른다. QGIS 다크 테마의
# Window 는 `#1e1e1e` 계열(L 약 0.012)이고 라이트는 `#f0f0f0` 계열(L 약 0.87)로
# 두 분포가 멀어서 경계 위치에 결과가 민감하지 않다.
DARK_LUMINANCE_THRESHOLD = 0.5

# WCAG 2.x sRGB 선형화 분기점.
SRGB_LINEAR_CUTOFF = 0.03928


def srgb_channel_to_linear(byte_value):
    """sRGB 채널 1개(0-255)를 선형 값으로 바꾼다 (WCAG 2.x).

    Args:
        byte_value: 0-255 정수.

    Returns:
        float: 선형화된 채널 값.
    """
    c = byte_value / 255.0
    if c <= SRGB_LINEAR_CUTOFF:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color):
    """QColor 의 WCAG 2.x 상대 휘도.

    Args:
        color: QColor 또는 QColor 가 받는 색 문자열.

    Returns:
        float: 0.0(검정) ~ 1.0(흰색).
    """
    qc = color if isinstance(color, QColor) else QColor(color)
    return (0.2126 * srgb_channel_to_linear(qc.red())
            + 0.7152 * srgb_channel_to_linear(qc.green())
            + 0.0722 * srgb_channel_to_linear(qc.blue()))


def contrast_ratio(color_a, color_b):
    """두 색의 WCAG 2.x 대비. 밝은 쪽이 분자다.

    Args:
        color_a: QColor 또는 색 문자열.
        color_b: QColor 또는 색 문자열.

    Returns:
        float: 1.0 ~ 21.0.
    """
    la = relative_luminance(color_a)
    lb = relative_luminance(color_b)
    lighter, darker = (la, lb) if la >= lb else (lb, la)
    return (lighter + 0.05) / (darker + 0.05)


def is_dark_palette(palette):
    """팔레트가 다크 테마인가 (설계 7-3).

    QGIS 는 "다크 테마인가" 를 묻는 API 를 주지 않는다. 그래서 Window 색의
    상대 휘도로 가르는 표준 관용구를 쓴다.

    Args:
        palette: QPalette.

    Returns:
        bool: 다크면 True.
    """
    window = palette.color(QPalette.Window)
    return relative_luminance(window) < DARK_LUMINANCE_THRESHOLD


def tokens(dark):
    """테마별 색 토큰 (설계 7-3 표).

    배경과 본문 색을 브랜드색으로 덮지 않는다. 그 둘은 QGIS 팔레트가 가지고
    있고 여기서 정하는 것은 **액센트와 카드/헤더 면**뿐이다. 다크 테마에서
    넓은 오렌지 면을 만들지 않는 것도 같은 이유다(설계 7-3 마지막 불릿).

    Args:
        dark: 다크 테마인가.

    Returns:
        dict: qss 템플릿에 끼울 토큰.
    """
    return {
        # 헤더는 양 테마 공통 네이비다. 로고 타일과 같은 계열이어야 한다.
        "header_bg": NAVY,
        "header_fg": WHITE,
        "header_accent": ACCENT,
        "primary_bg": ORANGE,
        "primary_fg": NAVY,
        "primary_hover_bg": ORANGE_HOVER,
        "card_bg": CARD_BG_DARK if dark else CARD_BG_LIGHT,
        "card_border": CARD_BORDER_DARK if dark else CARD_BORDER_LIGHT,
        "muted_fg": MUTED_DARK if dark else MUTED_LIGHT,
    }


def ui_tokens(dark):
    """0.2.2 심미 패스 토큰 + 0.3.x 스타일 배치 토큰 (설계 7-3 표 **밖**의 층).

    `tokens()` 와 키가 겹치지 않는다. 겹치면 설계 표가 조용히 덮인다.

    키를 **늘리기만** 한다. 0.2.2 의 14키는 이름과 역할이 그대로 남아 있고
    (0.3.x 스타일 배치가 더한 것은 아래 6개) 소비처(qss 치환자, 하네스 27 의
    대비쌍)가 그대로 돈다. 테마 인자도 그대로 `dark` 하나다 - U2 가 바꾼 것은
    **누가 그 dark 를 정하는가**(`resolve_dark`)이고 토큰 표 자체가 아니다.

    Args:
        dark: 다크 테마인가.

    Returns:
        dict: qss 템플릿에 끼울 추가 토큰.
    """
    return {
        "caption_fg": CAPTION_FG_DARK if dark else CAPTION_FG_LIGHT,
        "divider": DIVIDER_DARK if dark else DIVIDER_LIGHT,
        "block_rail": BLOCK_RAIL,
        "user_bg": USER_BG_DARK if dark else USER_BG_LIGHT,
        "user_bg_to": USER_BG_TO_DARK if dark else USER_BG_TO_LIGHT,
        "user_fg": USER_FG_DARK if dark else USER_FG_LIGHT,
        "header_glow": HEADER_GLOW,
        "shadow_edge": SHADOW_EDGE_DARK if dark else SHADOW_EDGE_LIGHT,
        "window_bg": WINDOW_BG_DARK if dark else WINDOW_BG_LIGHT,
        "window_fg": WINDOW_FG_DARK if dark else WINDOW_FG_LIGHT,
        "base_bg": BASE_BG_DARK if dark else BASE_BG_LIGHT,
        "danger_bg": DANGER_BG_DARK if dark else DANGER_BG_LIGHT,
        "danger_fg": DANGER_FG_DARK if dark else DANGER_FG_LIGHT,
        "danger_border": DANGER_BORDER_DARK if dark else DANGER_BORDER_LIGHT,
        "warn_bg": WARN_BG_DARK if dark else WARN_BG_LIGHT,
        "warn_fg": WARN_FG_DARK if dark else WARN_FG_LIGHT,
        "warn_border": WARN_BORDER_DARK if dark else WARN_BORDER_LIGHT,
        "chip_fg": CHIP_FG,
        "badge_ok_fg": BADGE_OK_FG,
        "badge_fail_fg": BADGE_FAIL_FG,
    }


def all_tokens(dark):
    """설계 표 토큰 + 심미 패스 토큰을 합친 dict.

    Args:
        dark: 다크 테마인가.

    Returns:
        dict: qss 치환에 쓰는 전체 토큰.

    Raises:
        KeyError: 두 층의 키가 겹치면 올린다. 조용히 덮는 것을 막는다.
    """
    base = tokens(dark)
    extra = ui_tokens(dark)
    clash = sorted(set(base) & set(extra))
    if clash:
        raise KeyError("token name clash: %s" % clash)
    base.update(extra)
    return base


def set_role(widget, role):
    """위젯에 역할 속성을 붙이고 스타일을 다시 계산시킨다.

    Args:
        widget: 대상 위젯.
        role: ROLE_* 값 중 하나.

    Returns:
        str: 붙인 역할.
    """
    widget.setProperty(ROLE_PROPERTY, role)
    repolish(widget)
    return role


def set_state(widget, state):
    """위젯에 상태 속성을 붙이고 스타일을 다시 계산시킨다.

    Args:
        widget: 대상 위젯.
        state: STATE_* 값 중 하나.

    Returns:
        str: 붙인 상태.
    """
    widget.setProperty(STATE_PROPERTY, state)
    repolish(widget)
    return state


def set_level(widget, level):
    """위젯에 심각도 속성을 붙이고 스타일을 다시 계산시킨다.

    Args:
        widget: 대상 위젯.
        level: LEVEL_* 값 중 하나.

    Returns:
        str: 붙인 심각도.
    """
    widget.setProperty(LEVEL_PROPERTY, level)
    repolish(widget)
    return level


def repolish(widget):
    """동적 속성을 바꾼 뒤 스타일을 다시 계산시킨다.

    Qt 는 속성 선택자에 걸린 규칙을 속성이 바뀌었다고 자동으로 다시 적용하지
    않는다. unpolish/polish 가 그것을 시키는 표준 관용구다.

    Args:
        widget: 대상 위젯.

    Returns:
        bool: 다시 계산을 요청했는가(위젯에 style 이 있으면 True).
    """
    style = widget.style()
    if style is None:
        return False
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
    return True


def package_dir():
    """플러그인 패키지 루트 경로.

    Returns:
        Path: `upwise_chat_for_qgis/` 폴더.
    """
    return Path(__file__).resolve().parent.parent


def asset_path(relpath):
    """패키지 루트 기준 자산 경로.

    Args:
        relpath: `resources/...` 같은 상대경로 문자열.

    Returns:
        Path: 절대경로.
    """
    return package_dir() / relpath


def load_qss_template():
    """style.qss 템플릿 원문을 읽는다.

    Returns:
        str: 템플릿. 파일이 없으면 빈 문자열(스타일 없이도 독은 동작한다).
    """
    path = asset_path(QSS_ASSET_RELPATH)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        # 자산이 빠진 설치본에서도 독은 떠야 한다. 스타일만 포기한다.
        return ""


def build_qss(dark):
    """테마에 맞는 독 스타일시트 문자열.

    Args:
        dark: 다크 테마인가.

    Returns:
        str: 토큰이 채워진 qss. 템플릿이 없으면 빈 문자열.
    """
    template = load_qss_template()
    if not template:
        return ""
    return template % all_tokens(dark)


# ----------------------------------------------------------------------
# U2 테마 모드 읽기/쓰기와 적용
# ----------------------------------------------------------------------

def _settings():
    """QgsSettings 하나. QGIS 밖에서는 None 이다 (keystore 와 같은 관용구).

    Returns:
        QgsSettings 또는 None.
    """
    try:
        from qgis.core import QgsSettings
    except ImportError:
        # 하네스는 QGIS 없이 이 모듈을 올린다. 설정이 없으면 기본 모드다.
        return None
    return QgsSettings()


def normalize_theme_mode(value):
    """모르는 값이 들어오면 기본 모드로 접는다.

    Args:
        value: 설정에서 읽은 값(문자열이 아닐 수도 있다).

    Returns:
        str: THEME_MODES 중 하나.
    """
    text = str(value or "").strip().lower()
    return text if text in THEME_MODES else THEME_MODE_DEFAULT


def read_theme_mode(settings=None):
    """저장된 테마 모드. 없거나 QGIS 밖이면 기본값이다.

    Args:
        settings: QSettings 호환 객체. None 이면 QgsSettings (하네스 주입구).

    Returns:
        str: THEME_MODES 중 하나.
    """
    store = settings if settings is not None else _settings()
    if store is None:
        return THEME_MODE_DEFAULT
    try:
        value = store.value(THEME_MODE_SETTING_KEY, THEME_MODE_DEFAULT)
    except Exception:  # noqa: BLE001 - 설정 읽기 실패가 독을 막지 않는다
        return THEME_MODE_DEFAULT
    return normalize_theme_mode(value)


def write_theme_mode(mode, settings=None):
    """테마 모드를 저장한다. 저장 즉시 sync 한다.

    키스토어와 같은 이유로 `sync()` 를 부른다(0.2.1 K6 실측) - QgsSettings 는
    메모리에 캐시하므로 sync 없이는 QGIS3.ini 에 값이 없고, QGIS 가 비정상
    종료하면 사용자가 고른 테마가 사라진다.

    Args:
        mode: THEME_MODES 중 하나. 그 밖이면 기본값으로 접는다.
        settings: QSettings 호환 객체. None 이면 QgsSettings.

    Returns:
        bool: 저장했는가.
    """
    value = normalize_theme_mode(mode)
    store = settings if settings is not None else _settings()
    if store is None:
        return False
    try:
        store.setValue(THEME_MODE_SETTING_KEY, value)
        store.sync()
    except Exception:  # noqa: BLE001 - 저장 실패도 표시는 이미 바뀐 상태로 둔다
        return False
    return True


def normalize_bool_setting(value, default=False):
    """QSettings 에서 돌아온 값을 불리언으로 접는다.

    INI 저장소는 True 를 문자열 "true" 로 돌려주므로 `bool(value)` 로 읽으면
    "false" 도 참이 된다(비어 있지 않은 문자열). 그래서 문자열 표기를 따로
    본다.

    Args:
        value: 설정에서 읽은 값.
        default: 알 수 없는 표기일 때 돌려줄 값.

    Returns:
        bool: 해석된 값.
    """
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off", "", "none"):
        return False
    return bool(default)


def read_header_expanded(settings=None):
    """저장된 헤더 펼침 상태. 없거나 QGIS 밖이면 기본값(접힘)이다.

    Args:
        settings: QSettings 호환 객체. None 이면 QgsSettings (하네스 주입구).

    Returns:
        bool: 펼친 상태로 뜰 것인가.
    """
    store = settings if settings is not None else _settings()
    if store is None:
        return HEADER_EXPANDED_DEFAULT
    try:
        value = store.value(HEADER_EXPANDED_SETTING_KEY,
                            HEADER_EXPANDED_DEFAULT)
    except Exception:  # noqa: BLE001 - 설정 읽기 실패가 독을 막지 않는다
        return HEADER_EXPANDED_DEFAULT
    return normalize_bool_setting(value, HEADER_EXPANDED_DEFAULT)


def write_header_expanded(expanded, settings=None):
    """헤더 펼침 상태를 저장한다. 저장 즉시 sync 한다.

    `write_theme_mode` 와 같은 이유로 `sync()` 를 부른다(0.2.1 K6 실측).

    Args:
        expanded: 펼친 상태인가.
        settings: QSettings 호환 객체. None 이면 QgsSettings.

    Returns:
        bool: 저장했는가.
    """
    store = settings if settings is not None else _settings()
    if store is None:
        return False
    try:
        store.setValue(HEADER_EXPANDED_SETTING_KEY, bool(expanded))
        store.sync()
    except Exception:  # noqa: BLE001 - 저장 실패도 표시는 이미 바뀐 상태로 둔다
        return False
    return True


def resolve_dark(palette, mode):
    """이 모드에서 다크로 그릴 것인가.

    "시스템" 이면 0.2.2 와 같은 휘도 판정이고, 그 밖이면 사용자가 고른 값이
    QGIS 테마를 **독 안에서만** 이긴다(docs/6 U2: QGIS 전역 불가침).

    Args:
        palette: QPalette (시스템 모드에서만 본다).
        mode: THEME_MODES 중 하나.

    Returns:
        bool: 다크로 그리는가.
    """
    resolved = normalize_theme_mode(mode)
    if resolved == THEME_MODE_DARK:
        return True
    if resolved == THEME_MODE_LIGHT:
        return False
    return is_dark_palette(palette)


def dock_palette(dark):
    """강제 모드에서 독 서브트리에 걸 팔레트 (U2).

    Qt 팔레트는 자식에게 상속되므로 독 내용 위젯 하나에 걸면 그 아래 전부가
    따라온다. QGIS 전역은 건드리지 않는다. 역할을 셋만 정하는 이유는 그것이
    면과 글자를 가르는 최소 집합이기 때문이다 - 나머지 역할은 QGIS 것을 물려
    받아야 플랫폼 위젯(스크롤바, 손잡이)이 낯설어지지 않는다.

    Args:
        dark: 다크로 그리는가.

    Returns:
        QPalette: Window/Base 계열이 채워진 팔레트.
    """
    tok = ui_tokens(dark)
    window = QColor(tok["window_bg"])
    text = QColor(tok["window_fg"])
    base = QColor(tok["base_bg"])
    pal = QPalette()
    for role in (QPalette.Window, QPalette.Button):
        pal.setColor(role, window)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(role, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, window)
    return pal


# 콤보 팝업 뷰에 붙이는 objectName (0.5.3).
#
# 이름이 필요한 이유는 구체도다 - `popup_qss` docstring 참조. `style.qss` 는
# 이 이름을 쓰지 않는다(팝업은 독 서브트리 밖이라 그 파일이 못 닿는다).
POPUP_VIEW_OBJECT_NAME = "UpwiseChatComboPopup"


def popup_palette(dark):
    """콤보 드롭다운 **팝업 목록**에 걸 팔레트 (0.5.3).

    왜 별 함수인가
        QComboBox 의 팝업 목록은 독 내용 위젯의 자식이 아니라 **자기 창**
        (`QComboBoxPrivateContainer`)에 얹힌 뷰다. `dock_palette` 가
        정하는 Window/Base/Text 셋은 독 서브트리에만 상속되고, `style.qss`
        에는 팝업을 **지목하는** 규칙이 없다 - 이 파일의 선택자 규약이
        objectName·동적 속성으로 제한돼 있어(후손 선택자 금지, 하네스
        48 V25) 팝업 뷰를 가리킬 선택자를 쓸 수 없다. 지목은 못 하지만
        **상속은 닿는다**는 것이 아래 실측의 핵심이다.

        그 결과가 2026-10-19 실기 실측이다: 콤보 자신의 qss `color`
        (`chip_fg` = #cbd5e1, 네이비 헤더 위에서 대비 11.9)가 팝업 뷰에
        글자색으로 **상속**되는데 팝업 면은 사용자 Qt 스타일의 밝은
        회색(#f0f0f0)이라, 비선택 항목 글자가 **대비 1.30** 이었다. 고른
        항목만 읽혔다(액센트 면 + 네이비 글자, 9.22). 라이트·다크가 **같은
        값**이었고 다크 테마는 팝업에 아예 닿지 않았다.

    왜 면이 양 테마 모두 네이비인가 (0.5.3 실측 결론)
        **항목 글자색은 우리가 고를 수 없다.** 조건 격자 실측(2026-10-19,
        scratchpad 프로브 3종)에서 팝업 항목의 글자색을 바꾸는 데 성공한
        조합은 단 하나였다 - 독 본문 qss 의 콤보 규칙에서 `color` 선언을
        **지우는 것**. 다음 전부가 렌더에 아무 영향이 없었다:

            팝업 뷰 팔레트 Text / 뷰 자기 스타일시트(ID·형·universal
            선택자, `::item` 포함) / 팝업 컨테이너 자기 스타일시트(세 선택자)
            / 콤보 자기 스타일시트의 후손 선택자

        Qt 스타일시트의 `color` 는 상속 속성이고, 조상 콤보 규칙
        (`#UpwiseChatThemePick { color: chip_fg }`)의 값이 항목 그리기
        시점에 팔레트를 덮는다. 즉 **항목 글자 = 콤보 글자 = chip_fg**
        (#cbd5e1)로 고정이다.

        그러면 면은 산술로 정해진다. #cbd5e1 의 상대 휘도는 0.6572 이므로
        대비 4.5 를 넘는 면은 휘도 0.1072 이하여야 한다 - **어두운 면뿐**
        이다. 반대로 콤보 자신은 네이비 헤더 위에 있어 밝은 글자가 필요하다.
        한 색으로 흰 면과 네이비 면을 동시에 만족시키는 값은 없다(앞쪽은
        휘도 0.1833 이하, 뒤쪽은 0.2164 이상을 요구해 모순). 그래서 팝업
        면을 **헤더와 같은 네이비**로 둔다 - 드롭다운이 열리는 그 컨트롤과
        같은 면이 되므로 읽는 사람에게도 한 덩이로 보인다.

    무슨 색을 쓰는가
        **새 색이 하나도 없다.** 면은 `tokens()` 의 `header_bg`(양 테마
        공통 네이비), 글자는 `CHIP_FG`, 고른 항목은 헤더 액센트 + 네이비
        (콤보 `:on` 규칙이 이미 쓰는 짝)다.

        대비: 비선택 #cbd5e1 on #0a1929 = 11.946(`CHIP_FG` 주석의 값과
        같은 짝) / 고른 항목 #0a1929 on #ffa756 = 9.218. 둘 다 WCAG 1.4.3
        본문 임계 4.5 위다(실렌더 판정은 하네스 70 R2·R3).

        다크 테마에서 이 면은 `BASE_BG_DARK` 와 **같은 값**이다(둘 다
        NAVY) - "다크에서 팝업이 다크 토큰을 따른다" 는 요구는 그래서
        문자 그대로 성립한다. 라이트 테마에서만 본문 면과 달라진다.

    Args:
        dark: 다크로 그리는가. 색은 같지만 서명을 유지한다 - 토큰 층의
            다른 함수와 호출 규약을 같게 두고, 뒤에 테마별로 갈라야 할
            때 호출 지점을 고치지 않게 한다.

    Returns:
        QPalette: 팝업 뷰에 걸 팔레트.
    """
    base = QColor(NAVY)
    text = QColor(CHIP_FG)
    pal = QPalette()
    # 면 역할 셋을 다 채운다. 팝업은 뷰(Base)와 그것을 담은 창(Window)이
    # 다른 위젯이라 한쪽만 칠하면 테두리 띠가 다른 색으로 남는다.
    for role in (QPalette.Base, QPalette.Window, QPalette.Button):
        pal.setColor(role, base)
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(role, text)
    pal.setColor(QPalette.AlternateBase, base)
    # 고른 항목. 콤보 `:on` 규칙과 같은 짝이라 열려 있는 컨트롤과 그
    # 목록의 현재 항목이 같은 색으로 읽힌다.
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor(NAVY))
    return pal


def popup_qss(dark):
    """콤보 팝업 목록 위젯에 **직접** 걸 스타일시트 (0.5.3).

    왜 팔레트만으로는 안 되는가
        **면이 팔레트만으로는 안 선다.** 팝업 뷰에 스타일시트가 한 장이라도
        걸리면 그 순간부터 면은 스타일시트가 정하고, `background-color` 가
        없으면 사용자 Qt 스타일의 기본 회색(#efefef)이 나온다(실측
        2026-10-19: 팔레트 Base 는 그대로 #ffffff 인데 렌더는 #efefef).
        그래서 면 값을 여기에 적어 둔다.

        글자색은 여기서도 못 정한다 - `popup_palette` docstring 의 조건
        격자 결론이다(조상 콤보 qss 의 `color` 가 상속으로 이긴다). 그래도
        `color` 를 같이 적는 이유는 **값이 어긋나지 않게** 하는 것이다:
        실제로 그려지는 색과 같은 값을 적어 두면 뒤에 Qt 동작이 바뀌어
        이 선언이 먹게 되더라도 대비가 그대로 산다.

        `style.qss` 에 팝업 선택자를 넣는 길은 선택자 규약이 막는다
        (후손 선택자 금지, 하네스 48 V25). 그래서 위젯 자신의 스타일시트다.

    색은 `popup_palette` 와 같다 - 새 색이 없다.

    Args:
        dark: 다크로 그리는가. `popup_palette` 와 같은 이유로 서명을
            유지한다.

    Returns:
        str: 팝업 뷰에 걸 스타일시트. `POPUP_VIEW_OBJECT_NAME` 을
            objectName 으로 가진 위젯에 걸어야 한다.
    """
    name = POPUP_VIEW_OBJECT_NAME
    return (
        "#%(n)s { color: %(fg)s; background-color: %(bg)s; }"
        "#%(n)s::item { color: %(fg)s; background-color: %(bg)s; }"
        "#%(n)s::item:selected { color: %(sel_fg)s;"
        " background-color: %(sel_bg)s; }"
        % {"n": name, "fg": CHIP_FG, "bg": NAVY,
           "sel_fg": NAVY, "sel_bg": ACCENT})


def apply_dock_theme(widget, mode=None):
    """독 내용 위젯에 테마를 건다 (설계 7-3 + U2).

    QGIS 전역(`QgsApplication.setStyleSheet`·`setPalette`)을 건드리지 않는다.
    또한 QDockWidget 자체가 아니라 내용 위젯에 거는 것이 이 함수의 계약이다.

    모드가 "시스템" 이면 **팔레트를 걸지 않고 되돌린다**. 빈 QPalette 는 해석
    마스크가 비어 있어서 모든 역할을 부모에게서 다시 물려받는다 - 강제 모드에서
    시스템으로 돌아오는 경로가 이것이다.

    Args:
        widget: 독 내용 루트 위젯.
        mode: THEME_MODES 중 하나. None 이면 저장된 값을 읽는다.

    Returns:
        bool: 다크 테마로 그렸는가.
    """
    resolved = normalize_theme_mode(
        read_theme_mode() if mode is None else mode)
    if resolved == THEME_MODE_SYSTEM:
        widget.setPalette(QPalette())
        dark = is_dark_palette(widget.palette())
    else:
        dark = resolved == THEME_MODE_DARK
    # **순서가 중요하다**: 스타일시트를 나중에 걸면 QStyleSheetStyle 의 polish
    # 가 위젯 팔레트를 스타일시트 적용 전 값으로 되돌린다(오프스크린 실측:
    # 강제 라이트인데 body 의 Window 가 QGIS 다크 값으로 남았다). 그래서
    # 스타일시트를 먼저 걸고 팔레트를 그 뒤에 건다.
    widget.setStyleSheet(build_qss(dark))
    if resolved != THEME_MODE_SYSTEM:
        widget.setPalette(dock_palette(dark))
    return dark


# ----------------------------------------------------------------------
# U4 그라데이션 테두리 카드
# ----------------------------------------------------------------------

# 테두리 두께(px)와 둥근 모서리 반지름(px). 반지름은 qss 카드들의 5 px 과
# 같아야 면과 선이 어긋나 보이지 않는다.
GRADIENT_BORDER_WIDTH = 2
GRADIENT_BORDER_RADIUS = 5


class GradientBorderFrame(QFrame):
    """면은 qss 가 칠하고 **테두리만** 그라데이션으로 그리는 카드 (U4).

    qss 로는 테두리에 그라데이션을 줄 수 없다(`border-image` 는 자산이 필요하고
    `border-color` 는 단색만 받는다). 그래서 테두리만 QPainter 로 그린다.

    색은 자기가 정하지 않는다 - 자기 팔레트의 휘도로 테마를 가르고
    `tokens()` 에서 주 색 짝을 꺼낸다. 그래서 U2 로 테마를 강제하면(팔레트가
    바뀌면) 이 테두리도 함께 따라온다. 하드코딩 색이 0 인 것이 이 클래스의
    계약이다(하네스 48 가 소스에서 단정한다).

    장식 경계다 - 정보를 전하지 않으므로 3:1 대상이 아니다(0.2.2 K3 의 구분).
    """

    def __init__(self, parent=None):
        """프레임을 만든다. 모양은 qss 가, 테두리는 paintEvent 가 그린다."""
        super().__init__(parent)
        # 자기 테두리를 직접 그리므로 Qt 기본 프레임선을 끈다. 두 선이 겹치면
        # 1 px 이 두 번 그려져 모서리가 지저분해진다.
        self.setFrameShape(QFrame.NoFrame)

    def border_colors(self):
        """그라데이션 두 끝 (하네스가 읽는 창구).

        Returns:
            tuple: (시작 hex, 끝 hex).
        """
        tok = tokens(is_dark_palette(self.palette()))
        return (tok["primary_bg"], tok["primary_hover_bg"])

    def paintEvent(self, event):  # noqa: N802 - Qt 가 요구하는 고정 이름
        """qss 가 그린 면 위에 그라데이션 테두리를 올린다."""
        super().paintEvent(event)
        start, end = self.border_colors()
        half = GRADIENT_BORDER_WIDTH / 2.0
        # 선 두께의 절반만큼 안으로 들여야 선이 위젯 밖으로 반쪽 잘리지 않는다.
        rect = QRectF(self.rect()).adjusted(half, half, -half, -half)
        grad = QLinearGradient(rect.left(), rect.top(), rect.right(),
                               rect.bottom())
        grad.setColorAt(0.0, QColor(start))
        grad.setColorAt(1.0, QColor(end))
        pen = QPen(grad, GRADIENT_BORDER_WIDTH)
        pen.setJoinStyle(Qt.RoundJoin)
        path = QPainterPath()
        path.addRoundedRect(rect, GRADIENT_BORDER_RADIUS,
                            GRADIENT_BORDER_RADIUS)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.end()
