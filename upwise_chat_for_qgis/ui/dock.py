"""UPWISE Chat 독 위젯 (S4 채팅 UI).

설계 7-1 의 7개 영역 중 S4 가 만드는 것

    [1] 헤더      상태 칩(모델/도구 수/MCP)과 권한 배지
    [4] 전사 영역  chat_view.ChatView
    [5] 승인 바    거부 재시도 바(approval_bar.DenialRetryBar)와 제외 안내 바
                   (approval_bar.ExclusionNoticeBar). 둘은 신호가 다르다.
                   포스처 토글과 턴 승인 바는 S5 범위 목록에 없어 만들지 않는다
    [6] 입력 영역  멀티라인 입력, [전송](Ctrl+Enter), [취소], cwd 표시
    [7] 상태 바    상태/턴 경과/침묵/stderr 줄 수, 침묵 워치독 행

S6 이 더한 것
    [2] 전제조건 바  preset_bar.PrereqBar. 미충족 항목만 적는다
    [3] 프리셋 행    preset_bar.PresetRow. 프리셋 4개 + [점검] 1개(0.3.0).
                     프리셋은 주입 + 포커스뿐이고 자동 전송 대상은 없다.
                     [점검] 은 내장 서버 핸들러를 직접 불러(모델 0턴) 포트·
                     버전·레이어 수를 전사에 한 줄로 적는다(설계 5-4 (b))
    마커 안내 바     preset_bar.SkillMarkerBar. 프리셋 턴이 닫힐 때 첫
                     assistant 텍스트 블록의 첫 줄로 스킬 호출을 판정한다
                     (설계 6-2). 슬래시가 stdin 경로에서 먹는지는 미측(D02)이고
                     이 판정이 그것을 우회한다
    헤더 1줄         터미널 Claude Code 동시 사용 경고(설계 8). 탐지할 수 없는
                     상황이라 상시 표시다

S7 이 더한 것
    [1] 헤더 브랜드  BrandLink. 흰 패널 로고 타일 + 'UPWISE' 글자. 전체가 한
                     클릭 영역이고 누르면 기본 브라우저로 upwise.co.kr 을 연다
                     (설계 7-1 [1]). 모달을 쓰지 않는 외부 링크 경로다.
    팔레트 적용      theme.apply_dock_theme 으로 독 내용 위젯에만 qss 를 건다.
                     QGIS 전역 스타일시트를 건드리지 않는다(설계 7-3).
                     주 버튼, 승인 바, 카드, 보조 텍스트가 토큰을 받는다.

0.2.0 이 더한 것 셋(설계 docs/2 3-3, 7-2)
    포스처 배지 3값  읽기 전용 / 수집 / 변경 허용. posture.POSTURE_LABELS 가 정본
    수집 전환 확인   PostureConfirmBar. 읽기 전용에서 수집 버튼을 누르면 묻고,
                     승인하면 C 로 재spawn 한 뒤 프리셋을 주입한다. **재전송하지
                     않는다** - 수집은 대상과 영역을 인자로 받는다
    소프트 경고 표시  게이트의 soft 항목(수집 서버 미연결)은 입력을 막지 않고
                     배지 툴팁과 전제조건 바에만 나온다

0.2.1 이 더한 것 둘(설계 docs/2 8, 5-4)
    키 설정 패널     헤더의 [키 설정] 토글이 독 안의 **비모달** KeyPanel 을
                     여닫는다. 모달도 QFileDialog 도 쓰지 않는다. 키 저장/삭제
                     뒤에 전제조건을 다시 읽어 수집 버튼과 전제조건 바를 갱신
                     한다 - 키가 없으면 "키가 설정되지 않았습니다" 가 뜬다
    레다크션 소유     독이 Redactor 하나를 소유하고 (1) 전사 위젯과 (2) 백엔드
                     로그북(jsonl + 진단)에 같은 객체를 넘긴다. 로그북은 spawn
                     마다 새로 열리므로 레다크터를 백엔드에 붙여 두어야
                     재spawn(취소·상승·cwd 변경) 뒤에도 치환이 이어진다

0.2.3 이 더한 것 하나 (사용자 요청)
    전사 내보내기    헤더의 [내보내기] 버튼 하나로 지금 전사를 마크다운
                     파일에 쓴다. **QFileDialog 를 쓰지 않는다**(설계 3-5
                     금지 목록) - 경로는 고정이고(`<프로필>/upwise_chat/
                     workspace/exports/`) 결과는 ExportNoticeBar 가 알린다.
                     쓰기 직전에 본문 전체를 레다크터에 통과시킨다. 레다크터가
                     붙기 **전에** 그려진 행은 치환되지 않은 채 전사 장부에
                     남아 있고(chat_view.set_redactor 비소급 규약), 내보내기는
                     그 행까지 디스크로 복제하기 때문이다.
    (칸 복사 버튼과 범위 드래그 선택은 ui/chat_view 가 맡는다.)

0.2.4 가 고친 것 하나 (핫픽스)
    복사 관문         0.2.3 의 복사 경로에는 위 관문이 없어서, 레다크터가
                     붙기 전에 그려진 행을 복사하면 키가 클립보드로
                     나갔다(V28-A89). 이제 모든 클립보드 쓰기가
                     chat_view._set_clipboard 의 같은 레다크터를 지나고,
                     막히면 ExportNoticeBar 가 그 사실을 알린다
                     (_on_copy_failed).

0.3.x UI 패스 2차 "구조·동작 배치" 가 더한 것 넷 (U5·U6·U10·U16)
    [5] 푸터        입력 영역 오른쪽 아래 "by UPWISE" 한 줄. 누르면 헤더 상표와
                    같은 곳을 연다. 헤더 타일과 중복 노출이지만 그 중복은
                    사용자 승인 사항이다(docs/6 U5).
    [1] 연결 표시    헤더에 상태점 + 현재 포트를 **상시** 띄운다. 멀티 QGIS
                    창에서 어느 창의 서버인지 가르는 유일한 단서다. 판정은
                    `EmbeddedServer.start_probe` 의 소켓 프로브이고 독은
                    그 결과만 읽는다 - 독이 소켓을 열지 않는다(설계 함정 1).
    [4]+키 패널     전사와 키 패널을 QSplitter 로 묶어 경계를 드래그로 옮길 수
                    있게 했다. 패널은 스크롤 영역 안이고, 열릴 때 내용 기준
                    최소 높이를 보장한다(U10, 사용자 피드백 2026-10-12).
    [1] 새 대화      헤더의 [새 대화] 가 화면을 비우고 백엔드를 **새 세션**으로
                    다시 띄운다(resume 없음). 포스처는 기본값 R 로 돌아간다 -
                    상승 영속의 의도적 예외이고 근거는 docs/5 4-2 에 있다.
                    U11 과의 차이는 세션까지 가는가 하나다.

0.3.x UI 패스 2차 "스타일 배치" 가 더한 것 하나 (U2 + U9)
    [1] 테마 컨트롤  헤더 셋째 줄의 3단 세그먼트(시스템/라이트/다크). 고른 값은
                     QgsSettings 에 남아 다음 적재에서 복원된다. **독 안에서만**
                     바뀐다 - QGIS 전역 스타일시트와 전역 팔레트를 건드리지
                     않는다(0.2.2 전역 무오염 실측 유지, docs/6 U2). 강제 모드의
                     면/글자색은 독 내용 위젯에 건 팔레트가 공급하고 그 팔레트는
                     Qt 상속으로 독 안쪽에만 내려간다(theme.dock_palette).
                     나머지 스타일 항목(말풍선 그라데이션·헤더 글로우·카드·
                     소프트 섀도)은 qss 와 theme 토큰이 맡아 이 파일에 코드가
                     없다 - 프리셋 카드의 그라데이션 테두리만 preset_bar 가
                     베이스 클래스로 받는다.

0.3.x UI 패스 2차가 더한 것 하나 (U11, 사용자 피드백 2026-10-12)
    화면 비우기       헤더의 [대화 지우기] 가 전사 화면만 비운다. 세션도 모델
                     맥락도 이미 쓴 파일도 건드리지 않는다 - 세션까지 새로
                     시작하는 것은 다른 기능(U16)이고 이 패스 범위가 아니다.
                     모달 확인을 쓸 수 없어 버튼이 두 번 누르기로 확인을
                     받는다(CLEAR_BUTTON_TEXT 주석). 같은 패스에서 [점검]
                     결과는 최신 1건만 남긴다(add_status_notice) - 무과금이라
                     사용자가 여러 번 누르고 그때마다 쌓이면 전사가 같은 사실의
                     사본으로 채워진다.

0.4.0 이 더한 것 넷 (사용자 요청 2026-10-15, UI 다듬기)
    입력 히스토리   입력창에서 위/아래 화살표로 보낸 메시지를 되부른다
                    (VS Code 채팅창 방식). 판정 로직은 InputHistory 가,
                    첫/마지막 줄과 키 가로채기는 HistoryTextEdit 가 맡는다.
    모델 선택       헤더 다섯째 줄의 4단 세그먼트(기본/Opus/Sonnet/Haiku).
                    값·문구·저장은 posture 가 정본이고(MODEL_CHOICE_*),
                    적용은 **다음 스폰부터**다 - 플래그는 세션에 붙어 다니지
                    않는다(설계 2-5, D01). 백엔드가 떠 있으면 그 사실을
                    공지 한 줄로 적는다.
    저장 안내 자동 숨김  성공한 내보내기 안내만 저절로 내려간다. 실패는
                    남는다(approval_bar.EXPORT_AUTO_HIDE_MS).
    버튼 문구       [내보내기] -> [대화 내보내기], [키 설정] -> [공공 API 키].
                    처음 보는 사용자에게 무엇을 하는 버튼인지 읽히게 한다.

권한 배지는 "권한 미확인" 에서 시작한다. **입력을 보내기 전에는 init 이 오지
않는다(D06 FAIL, S0 ln32/ln62-63/ln152-153).** 그래서 무과금 사전점검이 없고,
첫 턴의 init 에서 게이트 결과가 와서 배지를 갱신한다(설계 3-4).

S5 가 더한 것 네 가지.
    게이트 실패 차단  판정이 깨지면 입력을 막고 백엔드를 다시 띄운다(S5-1).
                      재시작이 끝나면 차단을 푼다 - 안 풀면 교착이다(init 은
                      턴을 보낸 뒤에만 온다).
    제외 안내 바      거부와 제외의 문구를 가른다(설계 3-5 표).
    cwd 변경          표시를 눌러 인라인으로 바꾸고 재spawn 한다(S5-3).
                      대화상자를 쓰지 않는다.
    상승 재전송        거부 바의 "허용하고 다시 요청" = W 포스처 재spawn +
                      `--resume` + 같은 요청 1회(S5-4, D23 측정 대상).

백엔드는 주입받는다. argv 조립(설계 5장)과 포스처가 S5 범위이므로, 독은
claude 실행 파일을 직접 찾지 않는다. `backend_factory` 를 받으면 첫 전송에서
그것으로 백엔드를 만들고, 없으면 입력 영역을 잠근 채로 전사만 그린다.

취소는 턴 중단이 아니라 백엔드 재시작이다(설계 2-5). 그렇게 표시한다.

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog, 중첩 이벤트 루프.
Qt import 는 전부 qgis.PyQt 셰임 경로로 한다(설계 7-4).

설계 정본: docs/1.mvp_design_v1.md 2-4, 2-5, 3-4, 3-5, 4-1 ~ 4-5, 7-1
"""

import collections
import os
import time

from qgis.PyQt.QtCore import QSize, Qt, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QTextCursor,
)

# NOTE(Claude): Qt6 에서 QShortcut 은 QtGui 로 옮겨갔다. 이 플러그인은 Qt5 에서만
# 검증됐고 metadata 에 supportsQt6 를 선언하지 않는다(설계 7-4, D16).
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..backend import detect as detect_mod
from ..backend import keystore as keystore_mod
from ..backend import logbook as logbook_mod
from ..backend import machine as machine_mod
from ..backend import posture as posture_mod
from ..backend import redact as redact_mod
from ..backend import skillbundle as skillbundle_mod
from ..backend import transcript as transcript_mod
from . import theme as theme_mod
from .approval_bar import (
    DenialRetryBar,
    ExclusionNoticeBar,
    ExportNoticeBar,
    StaleCwdBar,
    build_bar,
)
from .bottom_nav import NAV_CHAT, NAV_KEYS, NAV_STATS, BottomNav
from .charts import StatsPane
from .chat_view import ChatView
from .key_panel import KeyPanel
from .preset_bar import PostureConfirmBar, PrereqBar, PresetRow, SkillMarkerBar

# QGIS 는 독의 위치와 표시 상태를 objectName 으로 저장하고 복원한다.
# 이름이 비어 있으면 세션 간 복원이 되지 않고 Qt 경고가 뜬다.
DOCK_OBJECT_NAME = "UpwiseChatDock"

DOCK_TITLE = "UPWISE Chat"

# 독 루트 레이아웃 여백(px). Qt 기본 여백은 독 안에서 과하게 넓다.
LAYOUT_MARGIN = 8

# 독 루트 영역 사이 간격(px). 0.2.2: 6 -> 8. 영역(헤더/바/전사/입력)이 여섯
# 겹으로 쌓이므로 간격이 좁으면 어디서 어디까지가 한 영역인지 안 읽힌다.
LAYOUT_SPACING = 8

# 헤더 로고 타일의 표시 높이(논리 px). 설계 7-2 는 독 헤더를 24-32 px 로 두고,
# S7a 미리보기도 28 px 를 대표값으로 재서 이 값을 쓴다.
BRAND_TILE_HEIGHT = 28

# @2x 자산 배율. 자산은 56 px 로 넣고 devicePixelRatio 2 로 표시 치수를 반으로
# 접는다. HiDPI 에서 또렷하고 1x 에서는 Qt 가 스무스 축소한다(설계 7-2).
BRAND_TILE_SCALE = 2

# 헤더 네이비 면의 내부 여백(px). 로고 타일이 면에 붙지 않게 한다.
HEADER_PADDING = 8

# 로고 타일과 글자 사이 간격(px).
BRAND_SPACING = 6

# 전사 내보내기 버튼(0.2.3). 저장 위치를 묻지 않는다 - QFileDialog 가 금지
# 목록이라(설계 3-5) 고정 경로에 쓰고 경로를 바로 알린다.
#
# 0.4.0(사용자 요청): 버튼 문구를 "내보내기" -> "대화 내보내기" 로 늘렸다.
# 처음 보는 사용자에게 "내보내기" 만으로는 **무엇을** 내보내는지가 안 읽힌다
# (레이어인가 대화인가). 같은 줄의 [대화 지우기] 와 어휘도 맞는다.
EXPORT_BUTTON_TEXT = "대화 내보내기"
EXPORT_BUTTON_TIP = (
    "지금까지의 대화 전체를 마크다운 파일로 저장합니다. 저장 위치는 QGIS 프로필의 "
    "upwise_chat/workspace/exports 이고, 저장 뒤 경로를 알려 줍니다."
)
# U15(0.3.x UI 패스 2차): 버튼 툴팁(위)은 이미 "대화" 를 쓰고 있었고 빈 상태
# 툴팁만 "전사" 였다. 같은 버튼이 두 어휘로 말하면 안 된다.
EXPORT_EMPTY_TIP = "저장할 대화가 아직 없습니다"

# 내보내기 실패 사유 문구. 레다크션이 깨지면 **쓰지 않는다** - 치환을 못 한
# 본문을 디스크에 복제하는 것이 실패보다 나쁘다(설계 docs/2 5-4).
#
# U15: 사용자에게는 "레다크션" 이 아니라 그 일이 무엇인지로 말한다. 상수
# 이름과 설계 용어는 그대로다(approval_bar 의 같은 결정과 짝).
EXPORT_REDACT_FAIL = "민감정보 가림 처리에 실패해 저장을 멈췄습니다"

# 대화 지우기 버튼(U11, 0.3.x UI 패스 2차).
#
# 왜 두 번 누르기인가
#     실수 방지 확인이 1회 필요한데 모달이 금지다(설계 3-5: QMessageBox,
#     QDialog.exec() 금지). 확인 바를 새로 만드는 것보다 버튼 자신이 상태를
#     한 단 바꾸는 것이 싸고, 확인 문구가 누른 손가락 바로 아래에 뜬다.
#     두 번째 누름이 안 오면 CLEAR_CONFIRM_MS 뒤에 혼자 원래대로 돌아간다 -
#     확인 상태로 굳어 있으면 다음에 무심코 한 번 눌렀을 때 바로 지워진다.
CLEAR_BUTTON_TEXT = "대화 지우기"
CLEAR_CONFIRM_TEXT = "정말 지울까요?"
CLEAR_BUTTON_TIP = (
    "화면에 쌓인 대화를 비웁니다. 지금 세션과 모델이 기억하는 맥락, 이미 저장한 "
    "파일은 그대로입니다."
)
CLEAR_CONFIRM_TIP = "한 번 더 누르면 화면을 비웁니다. 잠시 기다리면 취소됩니다."
CLEAR_EMPTY_TIP = "비울 대화가 아직 없습니다"
CLEAR_BUSY_TIP = "응답을 받는 중에는 비우지 않습니다. 턴이 끝나면 눌러 주세요."

# 확인 상태가 저절로 풀리는 시간(ms). 4초는 "한 번 더" 를 읽고 누를 시간이면서
# 자리를 뜬 사이 확인 상태로 남지 않을 만큼 짧은 값으로 잡았다.
CLEAR_CONFIRM_MS = 4000

# 비운 뒤 전사에 남기는 한 줄. 화면이 통째로 비면 "세션도 끊겼나" 로 읽히므로
# 무엇이 그대로인지를 그 자리에 적는다(U11 이 U16 과 다른 점).
NOTICE_CLEARED = "화면을 비웠습니다. 지금 세션과 저장된 기록은 그대로입니다."

# 새 대화 버튼(U16, 0.3.x UI 패스 2차). 확인 기전은 U11 과 같다 - 두 번 누르기
# 뒤 CLEAR_CONFIRM_MS 자동 해제. 모달이 금지라(설계 3-5) 같은 선택을 두 번째로
# 반복하는 것이고, 확인 상태는 버튼마다 따로 선다(한쪽을 세워 두고 다른쪽을
# 누르면 그 누름이 실수로 실행되면 안 된다).
NEW_BUTTON_TEXT = "새 대화"
NEW_CONFIRM_TEXT = "정말 새로 시작할까요?"
NEW_BUTTON_TIP = (
    "화면을 비우고 대화를 처음부터 다시 시작합니다. 모델이 기억하던 맥락이 사라지고 "
    "권한은 읽기 전용으로 돌아갑니다. 이미 저장한 파일과 기록은 그대로입니다."
)
NEW_CONFIRM_TIP = (
    "한 번 더 누르면 새로 시작합니다. 지금까지의 맥락은 돌릴 수 없습니다. "
    "잠시 기다리면 취소됩니다."
)
NEW_BUSY_TIP = "응답을 받는 중에는 다시 시작하지 않습니다. 턴이 끝나면 눌러 주세요."

# 새 대화 결과 공지. 무엇이 사라지고 무엇이 남는지를 그 자리에 적는다 -
# U11 공지와 짝이고, 둘의 차이가 사용자에게 이 두 줄로만 드러난다.
NOTICE_NEW_SESSION = (
    "새 대화를 시작했습니다. 이전 맥락은 이어지지 않고 권한은 읽기 전용으로 "
    "돌아갔습니다. 저장된 기록은 그대로입니다."
)
NOTICE_NEW_SESSION_IDLE = (
    "화면을 비웠습니다. 백엔드가 아직 떠 있지 않으므로 다음 전송이 새 대화로 "
    "시작됩니다."
)
NOTICE_NEW_SESSION_FAILED = (
    "새 대화를 시작하지 못했습니다. 백엔드를 다시 띄우는 데 실패했습니다."
)

# 키 설정 토글 버튼(0.2.1). 체크 상태가 패널 가시성과 1:1 이다.
# U2 테마 세그먼트. 문구·툴팁·값은 theme 쪽이 정본이다(저장 키와 같은 자리에
# 있어야 값이 갈라지지 않는다). 여기 상수는 **묶음 툴팁** 하나뿐이다.
THEME_SEG_TIP = "이 창의 밝기만 바꿉니다. QGIS 테마는 그대로입니다."

# 0.4.0(사용자 요청): "키 설정" -> "공공 API 키". 처음 보는 사용자가 이 버튼을
# Claude 로그인 자리로 읽는 일이 있었다(0.4.0 미로그인 가드와 같은 배치에서
# 나온 혼동이다). 패널 머리글(key_panel.PANEL_HEADER "공공 API 키")과 같은
# 말을 써서 누르기 전과 누른 뒤가 같은 이름이 되게 한다.
KEYS_BUTTON_TEXT = "공공 API 키"
KEYS_BUTTON_TIP = (
    "공공 데이터 수집에 쓰는 API 키를 넣는 칸을 엽니다. Claude 로그인과는 "
    "별개입니다. 독 안에서 열리고 QGIS 조작을 막지 않습니다."
)

# 헤더 펼침 토글(사용자 실기 피드백 2026-10-16: "배너 내용은 최소화").
# 한 단어인 이유는 폭이다 - 접힌 상태에서 상시 줄에 남는 유일한 버튼이고,
# QPushButton 은 글자 폭 아래로 줄지 않으므로 그 글자 폭이 그대로 첫 줄의
# 고정분에 더해진다. 값·저장 키는 theme 쪽이 정본이다(테마 모드와 같은 자리).
HEADER_TOGGLE_TEXT = "메뉴"
HEADER_TOGGLE_TIP = (
    "독 머리의 버튼과 선택 칸을 펼치거나 접습니다. 접으면 대화 영역이 그만큼 "
    "넓어집니다."
)

# 상시 아이콘 줄(0.4.2, 사용자 실기 피드백 2026-10-17: "사전 설정과 관련된
# api 키 같은건 메뉴 안에 말고 메뉴 버튼 옆에 둬도 될 것 같습니다").
#
# 왜 **아이콘 전용**인가 (글자 버튼이면 못 올린다)
#     QPushButton 의 minimumSizeHint 는 글자 폭이라 상시 줄에 글자 버튼을
#     더하면 독 최소 폭이 그 글자 폭만큼 오른다(README 5 V34-A03). 넷의
#     글자 폭 합은 약 400 px 이고 게이트는 480 px 다 - 글자로는 못 올린다.
#     `ToolButtonIconOnly` 인 QToolButton 은 sizeHint 가 아이콘 상자로만
#     정해져서 `setText` 로 붙여 둔 문구가 폭에 들어가지 않는다(실측:
#     아이콘 16 px + qss padding 0 = 19 px/개, 넷이 76 px).
#
# 문구는 **기존 상수를 그대로 쓴다**(새 문구를 만들지 않는다). 버튼에
# 붙여 둔 `setText` 는 화면에 안 보여도 살아 있어서 두 가지를 한다 -
# (1) 확인 상태 전이(`_refresh_clear_button` 등)가 그대로 돌고
# (2) 접근성 이름·하네스 조회가 같은 문자열을 읽는다.
HEADER_ACTION_ICON_PX = 16

# 아이콘 사이 간격(px). 0 인 이유는 폭이다 - 넷 사이에 8 px 을 주면 24 px 이
# 상시 줄에 더 붙는다. 넷을 한 덩이(`UpwiseChatHeaderActions`)로 묶어
# 바깥 줄에는 간격 하나만 내도록 했다.
#
# **0.5.4 에서도 0 이다.** 0.5.3 의 캡션 넷이 붙어 읽히는 결함(사용자 신고
# 2026-10-19)을 이 상수로 고치지 않았다. 세 후보를 같은 축에서 쟀더니
# (하네스 73) 이 상수를 6 으로 올리는 안은 간격 6 px 에 **독 최소 폭
# +18 px** 이고, 캡션 라벨 좌우 qss padding 3 px 은 같은 간격 6 px 에 독
# 최소 폭이 **불변**이었다 - 캡션에 걸린 `setMinimumWidth(1)` 이 최소 폭을
# 1 로 고정해 padding 이 희망 폭에만 더해지기 때문이다. 그래서 가로 간격은
# style.qss 의 `#UpwiseChatActionCaption` padding 이 들고 있다.
#
# 이 상수를 올리려는 다음 회차는 그쪽 주석의 측정표를 먼저 본다.
HEADER_ACTION_SPACING = 0

# 아이콘 넷에 붙는 **문자 설명**(0.5.3, 사용자 지시 2026-10-19).
#
# 아이콘만으로는 뜻이 안 읽힌다는 실기 피드백이고, 네 단어는 사용자가 예시로
# 준 것(`api`, `new`, `save`, `delete`)을 그대로 쓴다. 순서는 버튼 순서와
# 1:1 이다 - 공공 API 키 / 새 대화 / 대화 내보내기 / 대화 지우기.
#
# **버튼 `text` 가 아니라 별 라벨이다.** `new`·`clear` 의 `text` 는 두 번
# 누르기 확인 상태에서 `NEW_CONFIRM_TEXT`·`CLEAR_CONFIRM_TEXT` 로 바뀌므로
# (`_refresh_new_button`·`_refresh_clear_button`), 그 text 를 화면에 띄우는
# 배치(`ToolButtonTextUnderIcon`)는 확인 상태에서 버튼 폭이 그 문장 폭으로
# 뛴다 - README 5 "UI 게이트는 가장 넓어지는 상태를 재야 한다" 의 축이다.
# 캡션은 값이 변하지 않는 QLabel 이라 그 축이 생기지 않고, 버튼은 그대로
# `ToolButtonIconOnly` 로 남는다(하네스 50·51 의 단정이 그대로 산다).
HEADER_ACTION_CAPTIONS = ("api", "new", "save", "delete")

# 아이콘과 캡션 사이 간격(px). 0 이다 - 세로로 쌓는 배치라 간격이 그대로
# 헤더 높이에 더해지고, 헤더 세로를 줄이라는 것이 0.5.1 피드백의 본 축이었다.
HEADER_ACTION_CAPTION_SPACING = 0

# 캡션 라벨의 최소 폭(px). 1 이다(0 은 Qt 가 무시한다).
#
# 근거는 폭 예산이다. 캡션을 "줄지 않는 것" 으로 두면 그 글자 폭이 그대로
# 독 최소 폭에 올라간다(README 5 "Qt 최소 폭은 줄지 않는 것들이 정한다").
# 실측(하네스 69, 실 글꼴 계보): 최소 폭을 안 걸면 독 최소 폭 341 -> 400
# (임계 480 아래이긴 하다), 1 로 걸면 **341 그대로**이고 캡션은 자기 글자
# 폭(sizeHint)을 그대로 받아 깔린다. 좁혀질 때만 글자가 잘리고, 그것은
# `conn_label`·`chip_label` 이 이미 쓰는 것과 같은 처방이다.
HEADER_ACTION_CAPTION_MIN_W = 1

# 공지 묶음 접기(같은 피드백의 "경고 메시지 등도 접을 수 있게").
# 접힌 줄은 **건수만** 말한다 - 안내가 있다는 사실을 숨기지 않으면서 줄 수를
# 1 로 묶는 가장 짧은 표현이다. 안내가 0 건이면 이 줄도 뜨지 않는다.
NOTICE_TOGGLE_TEXT = "안내 %d건"
NOTICE_TOGGLE_TIP = "머리말 안내를 펼치거나 접습니다."

# U9 모델 선택 세그먼트(0.4.0, 사용자 요청). 값·문구는 posture 쪽이 정본이다
# (저장 키와 argv 조립이 같은 모듈에 있어야 둘이 안 갈라진다). 여기 상수는
# **묶음 툴팁** 하나뿐 - 테마 세그먼트(THEME_SEG_TIP)와 같은 배치다.
MODEL_SEG_TIP = "이 창이 쓸 Claude 모델입니다. 다음 새 대화부터 적용됩니다."

# 백엔드가 떠 있는 중에 모델을 바꿨을 때의 공지 한 줄. 플래그는 세션에 붙어
# 다니지 않으므로(설계 2-5, D01 실측) 지금 도는 자식에는 적용되지 않는다 -
# 그 사실을 말하지 않으면 사용자는 바로 바뀐 줄 안다.
NOTICE_MODEL_NEXT_SPAWN = "모델을 %s 로 바꿨습니다. 다음 새 대화부터 적용됩니다."

# "by UPWISE" 푸터(U5). 헤더 상표와 같은 주소를 연다(theme.BRAND_URL).
FOOTER_TEXT = "by UPWISE"
FOOTER_TIP = theme_mod.BRAND_TOOLTIP

# 연결 표시(U6). 포트는 **상시** 보인다 - QGIS 창을 여러 개 띄우면 각 창이 자기
# 임시 포트를 쓰므로(embedded.PORT_SETTING_KEY 기본 0), 어느 창의 서버에 터미널
# 이나 외부 클라이언트가 붙었는지 가릴 단서가 포트 번호뿐이다.
#
# 글자는 짧게 둔다. 긴 사유는 툴팁으로 보낸다 - 0.2.2 에서 줄지 않는 헤더 라벨이
# 독 최소 폭을 694 px 까지 밀어 올린 자리가 바로 여기다.
CONN_TEXT_PENDING = "포트 %s 확인 중"
CONN_TEXT_OK = "포트 %s 연결됨"
CONN_TEXT_NO_ANSWER = "포트 %s 응답 없음"
CONN_TEXT_DOWN = "포트 %s 끊김"
CONN_TEXT_FOREIGN = "포트 %s 점유 확인"
CONN_TEXT_OFF = "서버 꺼짐"

CONN_TIP_PENDING = "내장 QGIS 서버에 아직 물어보지 않았습니다."
CONN_TIP_OK = "내장 QGIS 서버가 이 포트에서 응답합니다."
CONN_TIP_NO_ANSWER = (
    "포트는 열려 있는데 응답이 없습니다. QGIS 가 긴 작업 중일 수 있습니다. "
    "계속 이러면 QGIS 를 다시 시작하세요."
)
CONN_TIP_DOWN = (
    "이 포트를 듣는 것이 없습니다. 내장 서버가 내려갔습니다. 플러그인을 다시 "
    "켜거나 QGIS 를 다시 시작하세요."
)
CONN_TIP_FOREIGN = (
    "응답이 오지만 이 플러그인의 서버가 아닙니다. 서버가 내려간 뒤 다른 "
    "프로그램이 같은 포트 번호를 차지한 것으로 보입니다. 터미널이나 외부 AI "
    "클라이언트가 들고 있는 옛 주소를 그대로 쓰지 마세요."
)
CONN_TIP_OFF = "내장 QGIS 서버가 꺼져 있습니다."

# 프로브 판정값(U6). `backend.embedded.PROBE_*` 와 **같은 문자열**이어야 한다.
#
# 왜 그 모듈을 import 하지 않는가
#     `backend/embedded.py` 는 qgis.core 와 mcpserver 서버 모듈을 끌고 온다.
#     독은 QGIS 자원을 소유하지 않는 쪽이고(backend_factory·set_self_check 와
#     같은 이음매), 하네스는 독만 띄워 UI 분기를 재야 한다. 그래서 값만 거울로
#     둔다. 두 벌이 조용히 어긋나는 위험은 하네스 47 이 **집합 동일성**으로
#     막는다 - 주석의 약속이 아니라 게이트다.
CONN_VERDICT_OK = "OK"
CONN_VERDICT_DOWN = "DOWN"
CONN_VERDICT_NO_ANSWER = "NO_ANSWER"
CONN_VERDICT_FOREIGN = "FOREIGN"
CONN_VERDICT_OFF = "OFF"

# 포트를 모를 때 글자에 넣는 자리표시. 0 을 그대로 쓰면 "포트 0" 으로 읽힌다.
CONN_PORT_UNKNOWN = "-"

# 연결 프로브 주기(ms). 5초는 사용자가 상태 변화를 "실시간" 으로 느끼는 범위
# 안에서 가장 긴 값으로 잡았다. 매 틱의 비용은 loopback 왕복 1회이고 그것도
# 백그라운드 스레드에서 돈다 - 렌더 틱(50 ms 예산)에 들어가는 일은 결과 dict
# 하나를 읽어 라벨을 고치는 것뿐이다.
CONN_PROBE_MS = 5000

# 줄지 않는 헤더 라벨 금지(0.2.2 교훈). 1 px 로 둔다 - Qt 의 qSmartMinSize 는
# minimumSize().width() > 0 일 때만 sizeHint 를 덮으므로 0 은 효과가 없다
# (chat_view.WRAP_LABEL_MIN_W 와 같은 근거).
CONN_LABEL_MIN_W = 1

# 상태 칩 최소 폭(px, 0.5.1). CONN_LABEL_MIN_W·BADGE_LABEL_MIN_W 와 같은
# 근거다 - 접이식이 한 줄이 되면서 칩이 그 줄의 폭을 정할 수 있는 자리로
# 왔다. 칩 문면은 init 이 보고한 모델 이름을 담아 길어지므로(권한 배지와
# 같은 축) 상한을 박아 문면 길이와 독 최소 폭을 끊는다. 줄바꿈이 있어
# 글자는 잘리지 않는다.
CHIP_LABEL_MIN_W = 1

# 키 패널 높이(U10). 사용자 피드백: 열린 영역이 너무 좁고 늘릴 수 없었다.
#
# 원인은 KeyPanel 자체가 아니라 독 레이아웃이었다. 전사가 stretch 를 독점해
# 공간이 모자라면 Qt 가 non-stretch 위젯을 minimumSizeHint 까지 눌렀고, 조절
# 수단(스플리터)이 없었다. 조치는 셋이다 - 스플리터, 내부 스크롤, 그리고
# 열릴 때의 최소 높이 보장.
#
# 상한을 두는 이유: 제공자가 늘면 sizeHint 가 독 높이를 넘고, 그러면 전사가
# 보이지 않는다. 그 경우는 패널 안쪽 스크롤로 푼다.
KEY_PANEL_MIN_H = 160
KEY_PANEL_MAX_H = 320

# 스플리터가 전사에 남겨 두는 최소 높이(px). 그 아래로는 드래그해도 줄지
# 않는다 - 전사가 0 이 되면 사용자가 되돌릴 손잡이를 못 찾는다.
CHAT_MIN_H = 120

# 줄지 않는 라벨이 독의 최소 폭을 밀어 올린다(0.2.2 실측: 독 최소 폭이
# 694 px 이었고 그 대부분이 cwd 전체 경로와 상태 칩이었다). cwd 는 폭에 맞춰
# 앞을 줄이고(PathButton), 칩은 자기 줄로 내려 줄바꿈하게 했다.
CWD_LABEL_MIN_W = 120

# PathButton 이 글자에 쓸 수 없는 좌우 여유(px). qss 가 padding 0 을 주지만
# 버튼 프레임 여유가 남아 있어 그만큼 뺀다.
PATH_BUTTON_PADDING_PX = 10


def brand_tile_pixmap(logical_height=BRAND_TILE_HEIGHT):
    """헤더 로고 타일 pixmap 하나 (설계 7-2).

    @2x 자산을 읽어 devicePixelRatio 를 걸어 돌려준다. 자산 높이가 기대와
    다르면 스무스 축소로 맞춘다 - 자산을 바꿔도 헤더 높이가 흔들리지 않게
    하기 위함이다.

    Args:
        logical_height: 화면에 보일 논리 높이(px).

    Returns:
        QPixmap: 자산이 없으면 isNull() 인 pixmap. 호출자가 판단한다.
    """
    path = theme_mod.asset_path(theme_mod.LOGO_ASSET_RELPATH)
    pix = QPixmap(str(path))
    if pix.isNull():
        return pix
    want = int(logical_height) * BRAND_TILE_SCALE
    if pix.height() != want:
        pix = pix.scaledToHeight(want, Qt.SmoothTransformation)
    pix.setDevicePixelRatio(float(BRAND_TILE_SCALE))
    return pix


def tint_pixmap(pixmap, color):
    """pixmap 의 불투명한 획을 한 색으로 칠한 사본 (0.4.2).

    알파는 그대로 두고 색만 바꾼다(`CompositionMode_SourceIn`). 그래서
    아이콘의 모양과 가장자리 부드러움은 원본 그대로이고 색만 헤더 짝으로
    간다 - 자체 그린 아이콘을 들이지 않는 이유가 이것이다(모양은 Qt 가
    들고 있고 우리는 색만 정한다).

    Args:
        pixmap: 원본 QPixmap.
        color: 칠할 색 문자열(theme 의 토큰 값).

    Returns:
        QPixmap: 칠한 사본. 원본은 바뀌지 않는다.
    """
    out = QPixmap(pixmap.size())
    out.setDevicePixelRatio(pixmap.devicePixelRatio())
    # 투명으로 깔지 않으면 메모리 쓰레기가 그대로 보인다.
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), QColor(color))
    painter.end()
    return out


class BrandLink(QWidget):
    """헤더의 로고 타일과 'UPWISE' 글자. 전체가 한 클릭 영역이다(설계 7-1 [1]).

    타일만으로는 28 px 에서 상표를 읽기 어렵고, 글자만으로는 로고가 사라진다.
    그래서 둘을 한 위젯에 넣고 영역 전체에 손 커서와 툴팁을 붙인다.

    왜 QPushButton 이 아닌가
        버튼 모양(테두리, 눌림 효과)이 헤더 네이비 면 위에서 상표를 액자처럼
        가둔다. 링크의 성질은 커서와 툴팁으로 충분히 드러난다.

    시그널 하나를 낸다.

        clicked()  왼쪽 버튼을 위젯 안에서 눌러 안에서 뗐을 때.
    """

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        """타일과 글자를 올리고 커서, 툴팁을 붙인다."""
        super().__init__(parent)
        self.setObjectName("UpwiseChatBrand")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(theme_mod.BRAND_TOOLTIP)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(BRAND_SPACING)

        self.tile_label = QLabel(self)
        self.tile_label.setObjectName("UpwiseChatBrandTile")
        pix = brand_tile_pixmap()
        if not pix.isNull():
            self.tile_label.setPixmap(pix)
        row.addWidget(self.tile_label)

        self.wordmark_label = QLabel(theme_mod.WORDMARK_TEXT, self)
        self.wordmark_label.setObjectName("UpwiseChatBrandWordmark")
        row.addWidget(self.wordmark_label)

    def mouseReleaseEvent(self, event):
        """클릭 판정. 누른 뒤 밖으로 끌어 놓으면 열지 않는다.

        press 가 아니라 release 에서 내는 이유는 그것이 플랫폼 공통의 "클릭"
        정의이고, 실수로 누른 것을 끌어서 취소할 수 있어야 하기 때문이다.
        """
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def tile_pixmap(self):
        """타일에 걸린 pixmap. 하네스가 실치수를 잰다."""
        return self.tile_label.pixmap()

    def wordmark_text(self):
        """글자 라벨 문구."""
        return self.wordmark_label.text()

# 워치독 표시 갱신 주기(ms). 침묵 판정 자체는 상태머신이 하고(설계 4-5) 여기서는
# 남은 시간 카운트다운을 1초마다 다시 쓴다. 드레인(50 ms)과 별개의 타이머다.
WATCHDOG_TICK_MS = 1000

# 입력 영역 높이 상한(줄). 긴 텍스트를 붙여 넣어도 전사 영역을 먹지 않게 한다.
INPUT_MAX_LINES = 6

# 진단용 stderr 보관 줄 수. 전사에 섞지 않는다(설계 4-2 stderr 행).
STDERR_TAIL_MAX = 200

# 진행 중 표시(0.2.2). 점 개수만 1초마다 바뀐다.
BUSY_TEXT = "응답 받는 중%s"
BUSY_DOTS_MAX = 3

# ----- 0.6.1 채팅 큐잉·끼어들기 UI 배선 -----
#
# UI 큐를 만들지 않는다. CLI 가 자기 큐를 들고 있고(실측), 턴 중 stdin 에 쓰면
# CLI 가 쌓아 두고 턴이 끝나면 **스스로** 다음 턴으로 실행한다. 그래서 여기에
# 타이머·대기 리스트·재전송 루프가 없다 - 있으면 같은 메시지를 두 번 보낸다.

# 대기 건수 꼬리. `busy_label` 한 라벨이 "도는 중" 과 "대기 N건" 을 함께
# 말한다. 새 상시 위젯을 더하지 않는 이유는 독 최소 폭이다 - 상시 줄에 글자
# 위젯을 더할 때마다 최소 폭이 그 글자 폭만큼 오른다(README 5, BADGE_OK_FMT
# 주석의 같은 실측).
BUSY_QUEUE_SUFFIX = " (대기 %d건)"

# 그 라벨의 최소 폭(px). 1 인 이유는 BADGE_LABEL_MIN_W 와 **같은 실측**이다.
#
# 0.6.1 첫 판에서 이 값을 안 박았고, 대기 꼬리가 붙은 문면("응답 받는 중...
# (대기 99건)")의 라벨 최소 폭이 323 px 로 뛰어 독 최소 폭이 341 -> 530 px 가
# 됐다(하네스 106 W2-busy_queue 실측, 임계 480 초과). QLabel 은 줄바꿈이
# 없으면 최소 폭이 **글자 전체 폭**이라 문면이 길어질 때마다 독이 그만큼
# 안 좁아진다.
#
# 1 로 박으면 좁은 독에서 꼬리가 잘린 채 보인다. 잘려도 정보가 사라지지
# 않는 이유는 **대기 안내 바가 같은 숫자를 자기 줄에 적기 때문**이다(그쪽
# 라벨은 줄바꿈이 있어 폭을 안 밀고, 그 줄은 대기가 있을 때만 뜬다).
BUSY_LABEL_MIN_W = 1

# 그 라벨의 툴팁. 턴 중 입력이 열렸다는 사실과 중단 단축키를 **폭 비용 0** 인
# 자리에 적는다. 단축키 안내를 상시 라벨로 만들면 위와 같은 비용이 든다.
BUSY_TIP = (
    "턴이 도는 중에도 입력할 수 있습니다. 보낸 글은 CLI 큐에 쌓이고\n"
    "이번 턴이 끝나면 다음 턴으로 자동 실행됩니다.\n"
    "Ctrl+Shift+Enter 는 대기 메시지를 지금 보냅니다.\n"
    "Esc 는 지금 턴만 중단합니다(대기 메시지는 그대로 이어집니다)."
)

# 대기 안내 바. busy 이고 대기가 있을 때만 보인다 - 상시 위젯이 아니다.
QUEUE_BAR_TEXT = (
    "대기 %d건이 차례를 기다립니다. 이번 턴이 끝나면 자동으로 실행됩니다."
)

# 대기 바의 버튼(0.6.1). "대기 취소" 에서 **회수**로 바꿨다.
#
# 왜 삭제 전용 조작을 없앴는가
#     Claude Code 대화형 화면에는 "대기 전부 삭제" 가 없다. 있는 것은 입력창
#     첫 줄 Up 으로 **되가져오기**이고, 되가져온 글은 고쳐서 다시 보내거나
#     비워서 버린다. 삭제만 되는 버튼은 사용자가 쓴 글을 돌려주지 않는다.
#     취소 요청(`cancel_async_message`) 자체는 회수의 내부 단계로 그대로
#     쓴다 - 없어진 것은 UI 이고 요청이 아니다.
#
# 글자 길이가 "대기 취소" 보다 짧아야 한다(독 최소 폭 게이트). 2자다.
QUEUE_RECALL_TEXT = "회수"
QUEUE_RECALL_TIP = (
    "대기 중인 메시지를 입력창으로 되가져옵니다(Up).\n"
    "고쳐서 다시 보내거나 비워서 버릴 수 있습니다."
)

# 큐 전송 공지. 사용자가 턴 중에 보낸 글이 **지금 실행되는 것이 아니라는**
# 사실을 그 자리에 적는다. 적지 않으면 응답이 안 온다고 읽는다.
NOTICE_QUEUED = "메시지를 큐에 넣었습니다. 이번 턴이 끝나면 실행됩니다."

# 끼어들기 공지 3종.
#
# 중단된 턴은 `error_during_execution`·`is_error=true`·`result=null` 로 오는데
# **백엔드 오류가 아니다**(실측: 그 뒤 같은 프로세스가 다음 메시지를 정상
# 처리했다). 그래서 오류 문면을 쓰지 않는다.
NOTICE_INTERRUPTED = "턴을 중단했습니다."
NOTICE_INTERRUPT_SENT = "턴 중단을 요청했습니다. 영수증을 받으면 보냅니다."
NOTICE_INTERRUPT_UNSUPPORTED = (
    "이 백엔드는 턴 중단을 지원하지 않습니다. [취소](백엔드 재시작)를 쓰세요."
)

# ----- 0.6.1 Claude Code 대화형 화면과 같은 세 조작의 공지 -----
#
# 키 대응은 Claude Code 와 한 칸씩 밀려 있다(우리 전송키가 Ctrl+Enter 라서).
# 구조는 같다 - 전송키 = 큐잉 / Ctrl+Shift+Enter = 지금 보내기 / Esc = 끊기 /
# 첫 줄 Up = 회수.

# Esc·[취소] 의 끊기. **대기 메시지를 지우지 않는다** - 스트리밍 중 plain
# interrupt 뒤 대기 메시지가 살아서 다음 턴으로 실행된 것이 실측이다
# (docs/10 2 절 V50-03 대조군, 이전 V46-06 과 일치).
NOTICE_STOP_SENT = "턴 중단을 요청했습니다. 대기 메시지는 다음 턴으로 이어집니다."

# 끊기의 폴백 공지. 제어 요청을 보낼 수 없을 때(능력 없음·라이터 닫힘)
# 백엔드 재시작 경로로 내려간다. 맥락은 `--resume` 으로 이어지지만 프로세스가
# 바뀌므로 CLI 큐가 사라진다 - 그 차이를 적는다.
NOTICE_STOP_FALLBACK = (
    "턴 중단을 보낼 수 없어 백엔드를 재시작했습니다. 대기 메시지는 사라집니다."
)

# sendNow 영수증 분기 2종. 값의 뜻은 `process.interrupt_turn_send_now`
# docstring 에 등급과 함께 적혀 있다.
#
# `delivering` 은 `[스키마]` 다 - 우리 왕복에서 본 값은 `stopped` 하나이고
# (V50-02) 이 문면이 실제로 뜨는 회차는 아직 관측되지 않았다.
NOTICE_SEND_NOW_DELIVERING = "대기 메시지를 지금 전달합니다."
NOTICE_SEND_NOW_NOTHING = "보낼 글도 대기 메시지도 없습니다."

# sendNow 영수증의 "턴을 멈췄다" 값. 영수증 3종 중 **이것만 실측**이고
# (V50-02, r1 L30) 나머지 둘은 `[스키마]` 다. 그래서 이 값 하나만 상수로
# 두고 나머지는 "멈추지 않았다" 로 뭉쳐 읽는다 - 값마다 다른 처분을 지어내지
# 않는다는 규약이다.
SEND_NOW_STOPPED = "stopped"

# 회수 2종.
NOTICE_RECALLED = "대기 %d건을 입력창으로 되가져왔습니다."
NOTICE_RECALL_RACE = (
    "되가져온 메시지가 이미 실행에 들어갔습니다. 입력창의 글은 그대로 두었습니다."
)

BADGE_UNKNOWN = "권한 미확인"

# 통과 배지 문면(0.4.2, 사용자 결정 2026-10-17).
#
# 전 문면은 `권한 확인 (<권한모드> · <포스처> · 도구 N)` 이었고 **첫 턴 init 이
# 오는 순간** 상시 줄에서 가장 긴 가변 요소가 됐다 - 같은 계보 실측으로 라벨
# 최소 폭이 102 px(미확인)에서 595~714 px(통과)로 뛴다. 하네스는 기동 직후만
# 재고 있어서 그 상태가 게이트에 한 번도 안 걸렸다.
#
# 줄이는 기준은 "사용자가 상태를 가르는 데 쓰는가" 다. 포스처와 도구 수는
# 남긴다 - 지금 무엇을 할 수 있는지가 그 둘로 갈린다. 내부 권한 모드
# 이름(acceptEdits 등)은 CLI 어휘라 툴팁으로 내린다. 머리말 "권한 확인" 과
# 포스처 라벨은 **문자열 그대로 유지**한다(하네스 09 E1 이 앞머리를, 23 G4 가
# 포스처 라벨 셋을 읽는다).
BADGE_OK_FMT = "권한 확인 · %s · 도구 %d"

# 그 배지의 툴팁. 배지에서 내린 권한 모드가 여기 남는다 - 정보를 지운 것이
# 아니라 옮긴 것이다. 끝줄은 0.2.0 부터 쓰던 문장 그대로다.
BADGE_OK_TIP_FMT = "권한 모드 %s · 포스처 %s · 도구 %d\n기동 자기점검 전 항목 통과"

# 배지 라벨 최소 폭(px). 1 인 이유는 CONN_LABEL_MIN_W 와 같다 - 이 라벨은
# 줄바꿈이 없어 최소 폭이 **글자 전체 폭**이고, 그러면 배지 문면이 길어질
# 때마다 독 최소 폭이 같이 오른다(README 5 "Qt 최소 폭은 줄지 않는 것들이
# 정한다"). 1 로 박으면 문면이 아무리 길어도 독 최소 폭은 안 움직이고,
# 좁은 독에서는 뒤가 잘린 채 보인다. 잘린 전문은 툴팁에 있다.
#
# 고정 최대 폭이나 elide 를 쓰지 않은 이유: 둘 다 **자리가 있는데도** 글자를
# 지운다. 여기서 막아야 하는 것은 "자리가 없을 때 독이 안 좁아지는 것" 이고
# 그것은 최소 폭만으로 끝난다. (elide 의 말줄임표 U+2026 은 저장소 금지
# 문자이기도 하다.)
BADGE_LABEL_MIN_W = 1
CWD_PREFIX = "작업 폴더: "
CWD_UNSET = "(미지정)"

PLACEHOLDER_NO_BACKEND = "백엔드가 연결되지 않았습니다."
PLACEHOLDER_READY = "메시지를 입력하고 Ctrl+Enter 로 보냅니다."
# 게이트가 깨진 동안의 placeholder. 입력을 아예 막는 이유를 그 자리에 쓴다.
PLACEHOLDER_GATE_BLOCKED = "권한 점검이 어긋나 전송을 막았습니다. 백엔드를 다시 띄웁니다."

# 게이트 실패 공지. 설계 3-4 는 입력을 열지 않는 것까지 요구하고, 사용자에게는
# 왜 막혔는지가 보여야 한다.
NOTICE_GATE_BLOCKED = (
    "기동 자기점검이 어긋났습니다(%s). 이 턴의 결과를 버리고 백엔드를 "
    "다시 띄웁니다. 그동안 전송이 막힙니다."
)
NOTICE_GATE_BLOCKED_FINAL = (
    "기동 자기점검이 다시 어긋났습니다(%s). 자동 재시작을 멈춥니다. "
    "QGIS 를 다시 시작하거나 claude CLI 설정을 확인하세요."
)
NOTICE_ELEVATED = "변경 허용 포스처로 올려 같은 요청을 다시 보냅니다."
NOTICE_ELEVATE_FAILED = "포스처 상승에 실패했습니다. 읽기 포스처를 유지합니다."

# 수집 포스처 전환 공지(0.2.0, 설계 docs/2 3-3). 재전송하지 않는다 - 수집은
# 대상과 영역을 인자로 받으므로 사용자가 적어 보내야 한다(설계 6-1 과 같은 근거).
NOTICE_POSTURE_SWITCHED = "%s 포스처로 바꾸고 백엔드를 다시 띄웠습니다."
NOTICE_POSTURE_SWITCH_FAILED = "%s 포스처 전환에 실패했습니다. 지금 포스처를 유지합니다."
NOTICE_POSTURE_CANCELLED = "포스처 전환을 취소했습니다."
NOTICE_CWD_CHANGED = "작업 폴더를 바꾸고 백엔드를 다시 띄웠습니다: %s"
NOTICE_CWD_FAILED = "작업 폴더 변경에 실패했습니다: %s"
NOTICE_PROJECT_CHANGED = (
    "QGIS 프로젝트가 %s 으로 바뀌었습니다. 이전 프로젝트의 레이어 설명은 더 이상 "
    "맞지 않습니다."
)
# 다음 사용자 메시지 앞에 붙이는 한 줄. 모델이 들고 있는 레이어 지식이 무효가
# 됐음을 알려야 한다(설계 8).
PREFIX_PROJECT_CHANGED = "(프로젝트가 %s 으로 바뀌었습니다)"

# 헤더 상시 1줄(설계 8 "독과 터미널 세션 동시 사용" 행). 탐지할 방법이 없다.
# MCP 소켓이 단일 직렬이고 브리지가 둘이면 경합한다(F11).
TERMINAL_NOTICE = "터미널 Claude Code 와 동시에 QGIS 를 조작하지 마세요."

# 백엔드 기동 실패 전제조건 항목(설계 7-1 [2] 의 "기동 실패"). 로그인 상태를
# 탐지하지 않으므로(D07) 사용자에게 터미널 확인을 안내하는 것이 전부다.
PREREQ_BACKEND_DEAD = (
    "백엔드가 종료되었습니다 (rc=%s). 터미널에서 claude 를 한 번 실행해 "
    "로그인 상태를 확인하세요."
)

# 마커 판정 공지(설계 6-2). 성공은 전사에 한 줄, 실패는 바까지 띄운다.
NOTICE_MARKER_OK = "스킬 응답을 확인했습니다: %s"

# 자체 점검 제공자가 안 꽂혔을 때(0.3.0). 하네스가 독만 띄우는 구성이 그렇다.
NOTICE_CHECK_UNWIRED = "내장 서버 점검을 쓸 수 없습니다 - 플러그인이 꽂히지 않았습니다."

# [점검] 결과 공지의 교체 묶음 이름(U11). 같은 이름끼리만 교체되므로
# (ChatView.add_status_notice) 다른 공지와 섞이지 않는다.
SELF_CHECK_NOTICE_KEY = "self_check"


class PathButton(QPushButton):
    """경로를 폭에 맞춰 왼쪽부터 줄이는 평평한 버튼 (0.2.2).

    왜 QFontMetrics.elidedText 를 쓰지 않는가
        Qt 의 생략은 U+2026(말줄임표) 한 글자를 넣는다. 이 저장소는 그 문자를
        금지한다(02.projects/CLAUDE.md 인코딩 규칙). 그래서 ASCII `...` 로
        직접 줄인다. 잘라 내는 쪽은 **앞**이다 - 경로는 뒤쪽이 중요하다.

    왜 라벨이 아니라 버튼인가
        누르면 작업 폴더를 바꾸는 자리다(S5-3). 대화상자를 쓰지 않으므로
        인라인 편집 행을 여는 방아쇠가 이 위젯이다.
    """

    ELLIPSIS = "..."

    def __init__(self, text="", parent=None):
        """전체 문구를 기억한 채로 만든다."""
        super().__init__(text, parent)
        self._full_text = text
        self._prefix = ""

    def set_path_text(self, prefix, path):
        """머리말과 경로를 받아 기억하고 폭에 맞춰 그린다.

        Args:
            prefix: "작업 폴더: " 같은 머리말. 줄이지 않는다.
            path: 경로(또는 "(미지정)").

        Returns:
            str: 실제로 그린 문구.
        """
        self._prefix = str(prefix or "")
        self._full_text = self._prefix + str(path or "")
        return self._apply_elide()

    def full_text(self):
        """줄이기 전 전체 문구. 검증 하네스가 읽는다."""
        return self._full_text

    def _apply_elide(self):
        """지금 폭에 맞춰 문구를 줄여 넣는다.

        Returns:
            str: 넣은 문구.
        """
        metrics = self.fontMetrics()
        avail = max(0, self.width() - PATH_BUTTON_PADDING_PX)
        text = self._full_text
        if avail <= 0 or metrics.width(text) <= avail:
            self.setText(text)
            return text
        tail = text[len(self._prefix):]
        head = self._prefix + self.ELLIPSIS
        # 뒤에서부터 한 글자씩 늘려 가며 들어가는 만큼만 남긴다.
        keep = 0
        for n in range(1, len(tail) + 1):
            if metrics.width(head + tail[-n:]) > avail:
                break
            keep = n
        shown = head + tail[-keep:] if keep else head
        self.setText(shown)
        return shown

    def resizeEvent(self, event):  # noqa: N802 - Qt 가 요구하는 고정 이름
        """폭이 바뀌면 줄이기를 다시 계산한다."""
        super().resizeEvent(event)
        self._apply_elide()


class InputHistory(object):
    """보낸 입력을 위/아래 화살표로 되부르는 목록 (0.4.0, 사용자 요청).

    VS Code 채팅창과 같은 규약이다.

        위     더 **과거**로 간다. 처음 들어갈 때 지금 쓰던 초안을 보관한다.
        아래   더 **최신**으로 간다. 가장 최신을 지나면 보관한 초안을 되돌린다.
        타이핑 탐색을 접는다. 그 순간의 내용이 새 초안이다.

    위젯과 분리한 이유
        첫/마지막 줄 판정과 커서 이동은 Qt 의 일이고, "어디까지 거슬러
        올라갔는가" 는 Qt 가 모르는 상태다. 섞어 두면 하네스가 키 이벤트를
        합성해야만 이 규칙을 잴 수 있다. 분리하면 진리표로 잰다.

    무엇이 목록에 들어가는가
        **실제로 전송된 것만** 들어간다. 그래서 쌓는 지점이 `send_message` 의
        `backend.send()` **성공 뒤**다(0.4.0 가드 C 가 가로채는 대화형 전용
        슬래시는 그 앞에서 끊기므로 자연히 빠진다).

        재개 세션의 과거 사용자 행은 들어갈 것이 없다. 이 독은 `--resume`
        으로 CLI 세션만 잇고 전사는 메모리에 있으며, `--replay-user-messages`
        로 돌아오는 replay 행은 **렌더하지 않는 것이 설계 4-2 의 결정**이다
        (chat_view.add_user_message docstring). 그래서 "복원된 과거 사용자
        행" 이라는 것이 이 독에는 존재하지 않고, 전송 기록과 전사의 user 행은
        같은 집합이다. 둘 중 전송 기록을 고른 이유는 그쪽이 레다크션 치환
        **전** 원문이라 되불렀을 때 그대로 다시 보낼 수 있기 때문이다.
    """

    def __init__(self, limit=None):
        """빈 목록으로 시작한다.

        Args:
            limit: 보관 상한. None 이면 무제한이다.
        """
        self._items = []
        self._limit = limit
        # 탐색 위치. None 이면 탐색 중이 아니다(= 지금 보이는 것이 초안).
        self._index = None
        self._draft = ""

    def items(self):
        """보관 중인 입력 목록(오래된 것이 앞). 하네스가 읽는다."""
        return list(self._items)

    def index(self):
        """지금 탐색 위치. 탐색 중이 아니면 None."""
        return self._index

    def draft(self):
        """탐색에 들어갈 때 보관한 초안."""
        return self._draft

    def browsing(self):
        """지금 히스토리를 훑는 중인가."""
        return self._index is not None

    def reset(self):
        """탐색 상태를 접는다. 사용자가 타이핑하면 여기로 온다."""
        self._index = None
        self._draft = ""

    def add(self, text):
        """보낸 입력 하나를 쌓는다.

        연속 중복은 접는다 - 같은 요청을 두 번 보내는 일은 흔하고, 그때마다
        쌓이면 위 화살표를 같은 수만큼 눌러야 그 앞으로 간다.

        Args:
            text: 보낸 원문.

        Returns:
            bool: 실제로 쌓았는가(연속 중복이면 False).
        """
        text = text or ""
        if not text.strip():
            self.reset()
            return False
        if self._items and self._items[-1] == text:
            self.reset()
            return False
        self._items.append(text)
        if self._limit is not None and len(self._items) > self._limit:
            del self._items[0:len(self._items) - self._limit]
        self.reset()
        return True

    def older(self, current):
        """위 화살표. 더 과거 입력을 돌려준다.

        Args:
            current: 지금 입력창 내용. 탐색 시작이면 이것이 초안이 된다.

        Returns:
            str 또는 None. None 이면 되부를 것이 없다(위젯은 평소 동작).
        """
        if not self._items:
            return None
        if self._index is None:
            self._draft = current or ""
            self._index = len(self._items) - 1
        elif self._index > 0:
            self._index -= 1
        else:
            # 가장 오래된 것에 이미 닿았다. 그 자리에 머문다 - 한 번 더
            # 눌렀다고 목록을 되감으면 어디쯤인지 감각이 끊긴다.
            return None
        return self._items[self._index]

    def newer(self):
        """아래 화살표. 더 최신 입력, 끝을 지나면 초안을 돌려준다.

        Returns:
            str 또는 None. None 이면 탐색 중이 아니다(위젯은 평소 동작).
        """
        if self._index is None:
            return None
        if self._index < len(self._items) - 1:
            self._index += 1
            return self._items[self._index]
        draft = self._draft
        self.reset()
        return draft


class HistoryTextEdit(QPlainTextEdit):
    """위/아래 화살표로 보낸 입력을 되부르는 입력창 (0.4.0, 사용자 요청).

    화살표를 가로채는 조건이 둘이다.

        위    커서가 **첫 줄**에 있고, 되부를 과거 입력이 있을 때
        아래  커서가 **마지막 줄**에 있고, 탐색 중일 때

    둘 다 아니면 가로채지 않고 Qt 의 평소 커서 이동으로 넘긴다. 여러 줄을
    쓰는 입력창이므로 줄 사이 이동을 빼앗으면 못 쓴다.

    수정자(Shift/Ctrl/Alt)가 눌린 화살표는 손대지 않는다. Shift+Up 은 선택
    확장이고 그것을 히스토리로 바꾸면 사용자가 고른 범위가 사라진다.

    0.6.1 가 더한 두 훅 (Claude Code 대화형 화면과 같은 구조)
        on_recall_queued  첫 줄 Up 에서 **먼저** 불린다. 대기 메시지가 있으면
            그것을 입력창으로 되가져오고(True), 없으면 아무것도 하지 않아
            (False) 평소 히스토리 탐색으로 넘어간다. 순서가 중요하다 -
            대기가 있을 때 Up 이 히스토리로 가면 되가져오기에 닿을 키가 없다.
        on_escape  Esc 에서 불린다. 턴이 도는 중이면 끊고(True) 아니면
            아무것도 하지 않아(False) **Qt 의 평소 Esc 로 넘어간다.**
            넘기지 않으면 QGIS 지도 도구의 Esc 를 입력창이 삼킨다.

    둘 다 기본값 None 이고, 그때 이 위젯은 0.4.0 과 똑같이 동작한다 -
    독이 붙이지 않은 환경(하네스 주입구)에서 키가 죽지 않게 하기 위함이다.
    """

    def __init__(self, parent=None, history=None):
        """입력창 하나와 그 히스토리를 묶는다.

        Args:
            parent: 부모 위젯.
            history: InputHistory. None 이면 새로 만든다(하네스 주입구).
        """
        super().__init__(parent)
        self.history = history if history is not None else InputHistory()
        # 0.6.1 훅. 독이 생성 뒤에 꽂는다. 생성 인자로 받지 않는 이유는
        # 위젯이 독을 모르게 두려는 것이다(순환 참조 금지).
        self.on_recall_queued = None
        self.on_escape = None
        # 되부르기로 내용을 바꾸는 중인가. textChanged 는 사람의 타이핑과
        # 프로그램의 쓰기를 구분하지 못하므로, 이 깃발이 없으면 되부른 순간
        # 탐색이 스스로 접힌다.
        self._applying = False
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self):
        """사람이 친 변경이면 탐색을 접는다."""
        if not self._applying:
            self.history.reset()

    def apply_history_text(self, text):
        """되부른 문구를 넣고 커서를 끝에 둔다.

        Args:
            text: 넣을 문구.

        Returns:
            str: 넣은 문구.
        """
        self._applying = True
        try:
            self.setPlainText(text or "")
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)
        finally:
            self._applying = False
        return self.toPlainText()

    def at_first_line(self):
        """커서가 문서 첫 줄에 있는가."""
        return self.textCursor().blockNumber() == 0

    def at_last_line(self):
        """커서가 문서 마지막 줄에 있는가."""
        return (self.textCursor().blockNumber()
                == self.document().blockCount() - 1)

    def recall_older(self):
        """위 화살표 동작. 되부를 것이 없으면 False."""
        text = self.history.older(self.toPlainText())
        if text is None:
            return False
        self.apply_history_text(text)
        return True

    def recall_newer(self):
        """아래 화살표 동작. 탐색 중이 아니면 False."""
        text = self.history.newer()
        if text is None:
            return False
        self.apply_history_text(text)
        return True

    def _call_hook(self, hook):
        """훅 하나를 부르고 가로챘는지만 돌려준다.

        훅이 터져도 키 입력을 멈추지 않는다 - 훅은 편의 기능이고 입력창은
        그것 없이도 글자를 받아야 한다.

        Args:
            hook: callable 또는 None.

        Returns:
            bool: 가로챘는가.
        """
        if hook is None:
            return False
        try:
            return bool(hook())
        except Exception:  # noqa: BLE001 - 훅 실패가 입력을 막지 않는다
            return False

    def keyPressEvent(self, event):  # noqa: N802 - Qt 가 요구하는 고정 이름
        """화살표 둘과 Esc 만 조건부로 가로채고 나머지는 그대로 넘긴다."""
        if event.modifiers() == Qt.NoModifier:
            key = event.key()
            if key == Qt.Key_Escape:
                # 턴이 도는 중일 때만 가로챈다. 아니면 super() 로 넘어가
                # QGIS 쪽 Esc 가 살아 있는다.
                if self._call_hook(self.on_escape):
                    return
            elif key == Qt.Key_Up and self.at_first_line():
                # 되가져오기가 히스토리보다 **먼저**다(클래스 docstring).
                if self._call_hook(self.on_recall_queued):
                    return
                if self.recall_older():
                    return
            elif key == Qt.Key_Down and self.at_last_line():
                if self.recall_newer():
                    return
        super().keyPressEvent(event)


def _mmss(seconds):
    """초를 mm:ss 로. 상태 바와 워치독 카운트다운이 쓴다."""
    try:
        total = int(max(0, seconds))
    except (TypeError, ValueError):
        return "--:--"
    return "%02d:%02d" % (total // 60, total % 60)


class UpwiseChatDock(QDockWidget):
    """채팅 독 하나. 백엔드 하나와 상태머신 하나를 소유한다(설계 2-1).

    시그널 하나만 밖으로 낸다.

        denial_retry_requested()  거부 재시도 바의 "허용하고 다시 요청".
            포스처 상승은 재spawn 이라 S5 가 받아서 처리한다. 받는 쪽이
            붙기 전에는 버튼이 비활성이다.
    """

    denial_retry_requested = pyqtSignal()

    def __init__(self, parent=None, backend_factory=None):
        """독을 만들고 위젯을 세운다. 백엔드는 띄우지 않는다.

        Args:
            parent: 보통 QGIS 메인 윈도우.
            backend_factory: callable() -> backend.process.BackendProcess.
                None 이면 입력 영역이 잠긴 채로 전사만 그린다. 백엔드 spawn
                시점은 첫 전송이다(설계 2-1: 플러그인 활성화만으로 띄우지 않는다).
        """
        super().__init__(DOCK_TITLE, parent)
        self.setObjectName(DOCK_OBJECT_NAME)
        # 독을 왼쪽/오른쪽에만 붙인다. 채팅은 세로로 긴 레이아웃이라
        # 상단/하단 영역에서는 전사 영역이 읽을 수 없게 눌린다.
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._backend_factory = backend_factory
        self.backend = None
        self.machine = machine_mod.TurnMachine(on_note=self._on_machine_note)
        # 레다크터는 독이 소유한다(0.2.1, 설계 docs/2 5-4). 전사와 로그북이
        # **같은 객체**를 써야 "레다크션 n건" 이 세 지점 합계가 된다. 목록은
        # refresh_keys_state() 가 채운다 - 생성 시점에는 비어 있다.
        self.redactor = redact_mod.Redactor()

        self._stderr_tail = collections.deque(maxlen=STDERR_TAIL_MAX)
        self._stderr_count = 0
        self._cwd = ""
        self._gate = None
        self._denial_dismissed = set()
        # "계속 기다리기" 를 누른 시점의 침묵 길이. 그보다 120 s 더 조용해지면
        # 다시 띄운다. 영구 침묵 무시를 만들지 않는다(설계 4-5).
        self._silence_ack_s = 0.0
        self._cancel_elapsed_ms = None
        self._last_batch_n = 0
        # 사용량 차트가 집어 간 이벤트 수. 차트가 비어 있을 때 "신호가 안
        # 왔다" 와 "왔는데 못 읽었다" 를 가르는 유일한 값이다.
        self._usage_events = 0
        self._cost_events = 0
        # 상승 재전송(S5-4)이 다시 보낼 원문. 전송 시점에 기억한다.
        self._last_user_text = ""
        self._exclusion_dismissed = set()
        self._gate_blocked = False
        self._gate_failed_checks = []
        # 소프트 경고 항목(0.2.0). 입력을 막지 않지만 사용자에게 보여야 한다.
        self._gate_warn_checks = []
        self._posture_name = posture_mod.POSTURE_R
        self._elevate_count = 0
        # 진행 중 표시의 점 개수(0.2.2). 워치독 틱이 돌린다.
        self._busy_dots = 0

        # ----- 0.6.1 끼어들기 상태 -----
        #
        # "중단 후 전송" 은 두 단계다. interrupt 를 보내고 **영수증을 받은
        # 뒤에** 보낸다 - 시간으로 재지 않는다(추측 금지). 그 사이 보낼 글을
        # 여기 들고 있는다. 빈 문자열이면 대기 중인 끼어들기가 없다.
        self._interrupt_text = ""
        # 우리가 보낸 interrupt 의 request_id. 영수증 짝짓기에 쓴다.
        self._interrupt_request_id = ""
        # 영수증을 받았는가. 제어 응답 콜백이 세우고, 드레인 끝에서 전송하며
        # 내린다. **콜백에서 바로 보내지 않는 이유**: 콜백은 `_inspect` 안
        # (배치 드레인 중)에서 불리고, 그 시점에 상태머신은 아직 그 배치를
        # 먹지 않았다. 그 자리에서 보내면 턴 경계가 뒤집힌다.
        self._interrupt_acked = False
        # 끼어들기·대기취소 요청 수. 하네스가 읽는 창구다.
        self._interrupt_requests = 0
        self._queue_cancel_requests = 0
        # "중단됨" 공지를 이미 적은 턴 번호. 턴당 한 번이다(미로그인 공지와
        # 같은 근거 - 같은 턴을 다시 보고 또 적지 않는다).
        self._interrupted_notice_turns = set()

        # ----- 0.6.1 Claude Code 동형 조작 상태 -----
        #
        # 우리가 보낸 sendNow 요청의 request_id. 영수증의 `send_now` 값으로
        # 분기하려면 **어느 요청의 영수증인가**를 알아야 하고, plain 끊기와
        # 섞으면 두 분기가 서로의 영수증을 먹는다. 그래서 따로 든다.
        self._send_now_request_id = ""
        # 우리가 보낸 plain 끊기 요청의 request_id. 공지를 한 번만 적기 위한
        # 창구이고 전송 보류와 무관하다(그쪽은 `_interrupt_request_id`).
        self._stop_request_id = ""
        # 끊기·지금보내기·회수 요청 수. 하네스가 읽는 창구다.
        self._stop_requests = 0
        self._send_now_requests = 0
        self._recall_requests = 0

        # uuid -> (본문, 말풍선 라벨). **발급 순서를 지킨다**(dict 삽입 순서).
        #
        # 왜 독이 드는가
        #     회수는 본문과 말풍선 둘을 같이 써야 한다 - 본문은 입력창에
        #     되돌려 넣고 말풍선은 전사에서 걷어낸다. 상태머신은 위젯을 모르고
        #     전사는 uuid 를 모른다. 둘을 묶는 자리가 전송 지점인 독이다.
        self._sent_messages = collections.OrderedDict()
        # 지금 흐리게 그려 둔 말풍선의 uuid 집합.
        self._dim_uuids = set()
        # 그 uuid 가 lifecycle `queued` 로 관측된 적이 있는가. 흐림을 거두는
        # 조건이 "started 를 봤다" 또는 "queued 였다가 사라졌다" 이고, 후자를
        # 판정하려면 **전에 큐에 있었다**는 사실이 필요하다. 이 집합이 없으면
        # queued 줄이 도착하기 전의 빈 lifecycle 을 "정산됨" 으로 오독한다.
        self._dim_seen_queued = set()
        # 회수해 놓고 아직 운명이 갈리지 않은 uuid -> 본문. CLI 가 이미
        # 꺼냈으면(started·result) 그 메시지는 **실행된 것**이므로 말풍선을
        # 되돌려 놓는다 - 경합을 지어낸 규칙으로 덮지 않는다.
        self._recalled = collections.OrderedDict()
        # U11 대화 지우기 확인 상태. 서 있으면 다음 누름이 실제로 비운다.
        # 위젯보다 먼저 세운다 - _update_controls 가 이 값을 읽는다.
        self._clear_armed = False
        # U16 새 대화 확인 상태. 지우기와 **따로** 선다(NEW_BUTTON_TEXT 주석).
        self._new_armed = False
        # U16 새 세션 횟수. 하네스가 읽는다.
        self._new_session_count = 0

        # U6 연결 프로브. 독은 소켓을 열지 않고 결과만 들고 있는다.
        # `set_port_probe` 가 꽂히기 전에는 "확인 중" 으로 남는다 - 포트를
        # 모르는 상태를 "끊김" 으로 적으면 거짓말이다.
        self._port_probe = None
        self._last_probe = None
        self._probe_inflight = False

        # S6. 전제조건 탐지 결과는 플러그인이 소유하고 독은 읽기만 한다
        # (독이 claude 실행 파일을 직접 찾지 않는 것과 같은 이유다).
        self._prereq = None
        # 어느 턴이 어느 프리셋에서 났는가. 마커 판정을 프리셋 턴에만 걸기
        # 위함이다 - 평소 대화에까지 "스킬이 호출되지 않았습니다" 를 붙이면
        # 안내가 소음이 된다.
        self._preset_turns = {}
        self._judged_turns = set()
        self._marker_verdicts = []
        self._marker_dismissed = set()
        # 백엔드 사망 종료코드. 전제조건 바의 "기동 실패" 항목이 읽는다.
        self._backend_rc = None

        # 미로그인 공지를 이미 띄운 턴 번호(0.4.0, 가드 B). 미로그인이면
        # **매 턴** 같은 result 가 오므로 턴마다 같은 공지가 쌓인다. 턴당
        # 한 번으로 묶는다 - 거부 바가 턴당 하나인 것과 같은 근거다.
        self._login_notice_turns = set()

        # 내장 서버 자체 점검 제공자(0.3.0, 설계 5-4 (b)). 플러그인이
        # `EmbeddedServer.self_check` 를 꽂는다. 독이 서버 객체를 직접 들지
        # 않는 이유는 backend_factory 와 같다 - 독은 QGIS 자원을 소유하지
        # 않고, 하네스가 가짜 점검자를 넣어 UI 분기만 재야 한다.
        self._self_check = None
        # 마지막 점검 결과(하네스가 읽는다). 토큰 값은 들어가지 않는다.
        self._last_self_check = None

        # U2 테마 모드(독 내부 한정). **위젯을 세우기 전에** 읽는다 - 세그먼트
        # 컨트롤이 생성 시점에 고른 칸을 켜야 하고, 그 값을 아래 테마 적용이
        # 그대로 쓴다.
        self.theme_mode = theme_mod.read_theme_mode()

        # 모델 선택(0.4.0). 테마와 같은 이유로 위젯보다 먼저 읽는다.
        self.model_choice = posture_mod.read_model_choice()

        # 헤더 펼침 상태(사용자 실기 피드백 2026-10-16). 테마·모델과 같은
        # 이유로 위젯보다 먼저 읽는다 - 토글 버튼이 생성 시점에 자기 체크
        # 상태를 가져야 한다.
        self.header_expanded = theme_mod.read_header_expanded()

        # 공지 묶음 펼침 상태. 이쪽은 **저장하지 않는다** - 공지는 그때그때
        # 판정되는 사실이고, 지난 세션에 접었다는 이유로 이번 세션에 새로
        # 발화한 안내까지 접어 두면 발화의 의미가 사라진다.
        self._notice_expanded = False

        # 사용자가 이번 세션에 손으로 접었는가. 접었으면 새 안내가 떠도
        # 자동으로 펼치지 않는다 - 접은 결정을 매번 되돌리면 접기 자체가
        # 동작하지 않는 것과 같다.
        self._notice_user_collapsed = False

        # 입력 히스토리(0.4.0). 입력창보다 먼저 만든다 - `_build_input` 이
        # 이 객체를 위젯에 넘긴다. 독이 소유하는 이유는 전송 지점이 독의
        # `send_message` 라서다(위젯은 자기가 보낸 것을 모른다).
        self.input_history = InputHistory()

        # 내보내기 작업 폴더 대체 경로(0.2.3). 빈 값이면 프로필에서 해석한다.
        # 검증 하네스가 임시 폴더를 넣는 자리다 - 하네스는 QGIS 가 아니라
        # python 앱으로 뜨므로 프로필 경로가 제품과 다르고(S2 실측), 테스트가
        # 사용자 프로필에 파일을 쌓게 두지 않는다. 제품 경로는 이 값을
        # 건드리지 않는다(backend_factory 주입과 같은 성격의 이음매다).
        self.export_workspace_override = ""

        self.body = self._build_body()
        self.setWidget(self.body)
        # 팔레트 적용은 위젯이 다 선 다음이다(설계 7-3). 내용 위젯에만 건다 -
        # QDockWidget 자체에 걸면 Qt 가 제목 줄까지 스타일시트로 그린다.
        # U2: 저장된 모드를 넘긴다. "시스템" 이면 0.2.2 와 같은 휘도 판정이다.
        self.theme_dark = theme_mod.apply_dock_theme(self.body, self.theme_mode)
        # 0.5.3: 팝업 목록은 독 서브트리 밖이라 위 한 줄이 닿지 않는다.
        self._apply_combo_popup_theme(self.theme_dark)

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(WATCHDOG_TICK_MS)
        self._watchdog_timer.timeout.connect(self._on_watchdog_tick)
        self._watchdog_timer.start()

        # U11 확인 상태를 되돌리는 타이머. 혼자 풀리게 두는 이유는
        # CLEAR_CONFIRM_MS 주석에 적었다.
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.setInterval(CLEAR_CONFIRM_MS)
        self._clear_timer.timeout.connect(self._disarm_clear)

        # U16 새 대화 확인 타이머. 같은 기전, 다른 상태다.
        self._new_timer = QTimer(self)
        self._new_timer.setSingleShot(True)
        self._new_timer.setInterval(CLEAR_CONFIRM_MS)
        self._new_timer.timeout.connect(self._disarm_new)

        # U6 연결 프로브 틱. 워치독 틱과 따로 두는 이유는 주기가 다르고
        # (1 s 대 5 s) 프로브는 **비동기**라서다 - 틱에서 시작만 하고 결과는
        # 나중에 다른 슬롯으로 들어온다.
        self._probe_timer = QTimer(self)
        self._probe_timer.setInterval(CONN_PROBE_MS)
        self._probe_timer.timeout.connect(self._on_probe_tick)
        self._probe_timer.start()

        self._update_controls()
        self._update_status()
        # U6: 프로브가 꽂히기 전의 표시를 먼저 그린다.
        self._refresh_conn_label()
        # 프리셋은 비활성 + 이유 툴팁에서 시작한다. 전제조건이 붙기 전에
        # 누를 수 있게 두지 않는다(설계 7-1 [3]).
        self.refresh_prerequisites()
        # 미로그인 soft 사전검사(0.4.0, 가드 A). **독 기동 시 1회**다 -
        # 사용자가 터미널에서 /login 하는 동안 독이 떠 있을 수 있으므로
        # [새 대화] 에서도 다시 판정한다(new_session 의 같은 호출).
        self.refresh_login_notice()

    # ------------------------------------------------------------------
    # 위젯 구성
    # ------------------------------------------------------------------

    def _build_body(self):
        """독 내용 위젯을 만들어 돌려준다."""
        body = QWidget(self)
        body.setObjectName("UpwiseChatDockBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(
            LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN
        )
        layout.setSpacing(LAYOUT_SPACING)

        layout.addWidget(self._build_header(body))

        # [2] 전제조건 바와 [3] 프리셋 행(설계 7-1). 둘 다 헤더 바로 아래다.
        self.prereq_bar = PrereqBar(body)
        layout.addWidget(self.prereq_bar)

        # 키 설정 패널(0.2.1). 기본은 숨김이고 헤더 토글이 연다.
        #
        # U10: 레이아웃에 직접 붙이지 않고 **전사와 같은 스플리터**에 넣는다
        # (아래 `_build_split`). 0.2.1 은 전제조건 바 바로 아래였고, 그 자리는
        # "키가 설정되지 않았습니다" 를 읽은 손이 바로 닿는다는 이유였다.
        # 스플리터로 옮기면서 그 이유를 지키려고 패널을 전사 **위** 칸에 둔다 -
        # 읽는 순서(전제조건 -> 키 -> 대화)가 유지되고, 드래그 손잡이는 요구된
        # 대로 패널과 전사 사이에 생긴다.
        self.key_panel = KeyPanel(body)
        self.key_panel.keys_changed.connect(self._on_keys_changed)

        self.preset_row = PresetRow(body)
        self.preset_row.preset_clicked.connect(self._on_preset_clicked)
        self.preset_row.check_requested.connect(self._on_self_check)
        layout.addWidget(self.preset_row)

        # 포스처 확인 바(0.2.0). 프리셋 행 바로 아래다 - 누른 버튼과 묻는 글이
        # 붙어 있어야 무엇에 대한 확인인지 읽힌다.
        self.posture_bar = PostureConfirmBar(body)
        self.posture_bar.confirmed.connect(self._on_posture_confirmed)
        self.posture_bar.cancelled.connect(self._on_posture_cancelled)
        layout.addWidget(self.posture_bar)

        self.chat_view = ChatView(body)
        self.chat_view.setObjectName("UpwiseChatTranscript")
        # 레다크션 적용 지점 2(설계 docs/2 5-4). 전사는 콜러블만 들고 있는다.
        self.chat_view.set_redactor(self.redactor)
        # 0.2.4 복사 관문. 전사가 클립보드 쓰기를 막으면 그 사실을 사용자에게
        # 알린다 - 내보내기 실패(E7)와 같은 비모달 바 패턴이다.
        self.chat_view.copy_failed.connect(self._on_copy_failed)
        # U10: 전사와 키 패널이 한 스플리터를 나눠 쓴다. stretch 는 스플리터가
        # 받는다 - 늘어나는 영역은 여전히 이 한 칸뿐이다.
        layout.addWidget(self._build_split(body), 1)

        # 통계 칸(차트 2종). 전사 **아래**이고 스플리터 **밖**이다.
        #
        # 스플리터에 세 번째 칸으로 넣지 않는 이유는 둘이다. ① 스플리터의
        # 칸 수를 하네스가 `split_count` 로 읽고 `_resize_key_panel` 이
        # `setSizes([키, 전사])` 로 두 칸을 전제한다 - 칸을 늘리면 그 둘이
        # 조용히 어긋난다. ② 차트는 드래그로 키울 대상이 아니라 자기 내용
        # 높이면 되는 칸이다. 기본은 숨김이고 바텀 내비 [통계] 가 연다.
        self.stats_pane = StatsPane(body)
        layout.addWidget(self.stats_pane)

        self.denial_bar = DenialRetryBar(body)
        self.denial_bar.retry_requested.connect(self._on_denial_retry)
        self.denial_bar.keep_denied.connect(self._on_denial_keep)
        layout.addWidget(self.denial_bar)

        # 제외 바는 거부 바와 따로 있다. 둘이 같은 턴에 날 수 있고 문구와
        # 버튼이 달라야 한다(설계 3-5 표).
        self.exclusion_bar = ExclusionNoticeBar(body)
        self.exclusion_bar.dismissed.connect(self._on_exclusion_dismissed)
        layout.addWidget(self.exclusion_bar)

        # 마커 안내 바(설계 6-2). 거부/제외와 다른 축이라 바를 따로 둔다 -
        # 여기서 막힌 것은 권한이 아니라 슬래시 명령의 해석(D02)이다.
        self.marker_bar = SkillMarkerBar(body)
        self.marker_bar.fallback_requested.connect(self._on_marker_fallback)
        self.marker_bar.dismissed.connect(self._on_marker_dismissed)
        layout.addWidget(self.marker_bar)

        # 프로젝트 전환 stale 바(설계 8). cwd 변경과 같은 재spawn 경로를 쓴다.
        self.stale_bar = StaleCwdBar(body)
        self.stale_bar.restart_requested.connect(self._on_stale_restart)
        self.stale_bar.dismissed.connect(self.stale_bar.hide_bar)
        layout.addWidget(self.stale_bar)

        # 내보내기 안내 바(0.2.3). 저장 결과를 알리는 자리다. 다른 바들과 같은
        # 자리에 두는 것이 중요하다 - 사용자가 안내를 찾는 곳이 한 군데여야 한다.
        self.export_bar = ExportNoticeBar(body)
        self.export_bar.open_requested.connect(self._on_export_open)
        self.export_bar.dismissed.connect(self.export_bar.hide_bar)
        layout.addWidget(self.export_bar)

        # 바텀 내비(docs/6 2절 보류분). 안내 바들 **아래**, 입력 영역
        # **위**다 - 본문 영역의 바닥이라는 자리를 지키면서 입력줄과 겹치지
        # 않는다. 자기 줄이라 폭 중립이다(bottom_nav 모듈 docstring).
        self.bottom_nav = BottomNav(body)
        self.bottom_nav.selected.connect(self._on_nav_selected)
        layout.addWidget(self.bottom_nav)

        layout.addWidget(self._build_input(body))
        layout.addWidget(self._build_status(body))
        return body

    def _on_nav_selected(self, key):
        """바텀 내비에서 칸을 골랐다. 칸 하나만 남긴다.

        키 패널은 **헤더 토글을 경유해서** 연다. 패널 가시성과 설정·전제조건
        갱신이 그 경로에 묶여 있고(`_on_keys_toggled`), 여기서 패널을 직접
        `setVisible` 하면 두 경로가 갈라져 토글 상태와 화면이 어긋난다.

        Args:
            key: bottom_nav 의 NAV_* 값.

        Returns:
            str: 적용한 칸 키.
        """
        want_keys = key == NAV_KEYS
        want_stats = key == NAV_STATS
        button = getattr(self, "keys_button", None)
        if button is not None and button.isChecked() != want_keys:
            # 토글의 `toggled` 가 `_on_keys_toggled` 를 부른다.
            button.setChecked(want_keys)
        self.show_stats(want_stats)
        # 고른 칸을 **마지막에 다시 박는다**. 위 두 줄이 각자 내비 표시를
        # 맞추는 코드를 들고 있어서(키 토글은 "통계가 닫혀 있으면 대화",
        # show_stats 는 그 반대) [통계] 를 누른 순간의 중간 상태가 표시를
        # 대화로 되돌린다(실측: 하네스 93 D4 FAIL). 사용자가 고른 것이
        # 이긴다.
        nav = getattr(self, "bottom_nav", None)
        if nav is not None:
            nav.set_current(key)
        return key

    def show_stats(self, visible):
        """통계 칸을 여닫는다.

        열 때만 수집 통계를 다시 훑는다 - 닫힌 칸을 위해 디스크를 읽을
        이유가 없고, 드레인마다 읽으면 렌더 틱 예산을 먹는다.

        Args:
            visible: 띄울 것인가.

        Returns:
            bool: 띄웠는가.
        """
        pane = getattr(self, "stats_pane", None)
        if pane is None:
            return False
        if visible:
            self.refresh_collect_stats()
        pane.setVisible(bool(visible))
        nav = getattr(self, "bottom_nav", None)
        if nav is not None and not visible and nav.current() == NAV_STATS:
            # 통계를 닫는 경로가 내비 밖에도 있다(키 토글). 가리키는 칸을
            # 화면과 맞춘다.
            nav.set_current(NAV_KEYS if self.keys_button.isChecked()
                            else NAV_CHAT)
        return bool(visible)

    def refresh_collect_stats(self):
        """수집 통계 차트를 산출물 폴더에서 다시 읽는다.

        Returns:
            int: 총 수집 회차 수.
        """
        pane = getattr(self, "stats_pane", None)
        if pane is None:
            return 0
        try:
            workspace = self.export_workspace()
        except Exception as exc:  # noqa: BLE001 - 통계 때문에 독이 멈추지 않는다
            self._on_machine_note("collect_stats_failed", repr(exc))
            return 0
        return pane.collect_card.refresh_from(workspace)

    def _build_split(self, parent):
        """키 패널과 전사를 한 세로 스플리터에 넣는다 (U10).

        세 가지를 함께 푼다.

            1. **드래그 조절**  스플리터 손잡이가 패널과 전사 사이에 생긴다.
               전에는 전사가 stretch 를 독점해 패널이 눌렸고 되돌릴 손잡이가
               없었다.
            2. **내부 스크롤**  패널을 `QScrollArea` 에 넣는다. 제공자가 늘거나
               독이 낮아도 패널 내용이 잘리지 않고 안쪽에서 스크롤된다.
               가로 스크롤은 끈다 - 최소 폭 347 px 요구는 줄바꿈으로 지키고,
               가로 스크롤을 켜면 그 요구가 조용히 풀린다.
            3. **최소 높이**  열릴 때 `_resize_key_panel` 이 내용 기준 높이를
               보장한다. 여기서 바로 정하지 않는 이유는 열기 전의 sizeHint 가
               숨은 위젯의 값이라서다.

        Args:
            parent: 부모 위젯.

        Returns:
            QSplitter: 본문 레이아웃에 들어갈 스플리터.
        """
        split = QSplitter(Qt.Vertical, parent)
        split.setObjectName("UpwiseChatBodySplit")
        # 손잡이를 끝까지 밀어 한쪽을 0 으로 접는 것을 막는다. 전사가 0 이 되면
        # 사용자가 되돌릴 손잡이를 화면에서 못 찾는다.
        split.setChildrenCollapsible(False)

        self.key_scroll = QScrollArea(split)
        self.key_scroll.setObjectName("UpwiseChatKeyScroll")
        self.key_scroll.setFrameShape(QFrame.NoFrame)
        # 내용 위젯이 스크롤 영역 폭을 따라간다. 이것을 안 켜면 패널이
        # sizeHint 폭으로 고정되어 좁은 독에서 가로로 잘린다.
        self.key_scroll.setWidgetResizable(True)
        self.key_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.key_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.key_scroll.setWidget(self.key_panel)
        # `QScrollArea.setWidget` 은 내용 위젯을 **보이게 만든다**(PyQt5 실측:
        # 숨긴 위젯의 isHidden 이 setWidget 뒤 False 가 된다). KeyPanel 은
        # 숨은 상태로 생성되는 계약이고(KeyPanel.__init__ 마지막 줄) 그 상태를
        # 하네스가 `key_panel_visible` 로 읽는다. 그래서 여기서 다시 세운다 -
        # 안 하면 적재 직후 "패널이 열려 있다" 고 보고된다.
        self.key_panel.setVisible(False)
        self.key_scroll.setVisible(False)
        split.addWidget(self.key_scroll)

        split.addWidget(self.chat_view)
        self.chat_view.setMinimumHeight(CHAT_MIN_H)
        # 남는 높이는 전사가 받는다. 키 패널은 자기 내용만큼만 쓴다.
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        self.body_split = split
        return split

    def _resize_key_panel(self):
        """키 패널 칸에 내용 기준 높이를 준다 (U10).

        `sizeHint` 를 그대로 쓰지 않고 상한을 두는 이유는 제공자가 늘면 그 값이
        독 높이를 넘어 전사를 밀어내기 때문이다. 넘치는 만큼은 스크롤이 받는다.

        Returns:
            int: 패널 칸에 준 높이(px).
        """
        want = int(self.key_panel.sizeHint().height())
        want = max(KEY_PANEL_MIN_H, min(want, KEY_PANEL_MAX_H))
        self.key_scroll.setMinimumHeight(want)
        # 지금 높이를 모르면(아직 안 보임) 전사 최소 높이를 더해 비율만 준다.
        total = int(self.body_split.height()) or (want + CHAT_MIN_H)
        chat = max(CHAT_MIN_H, total - want)
        self.body_split.setSizes([want, chat])
        return want

    def _build_header(self, parent):
        """[1] 헤더. 상시 1줄 + 접이식 영역 + 접이식 공지 묶음(설계 7-1, 3-4, 8).

        S7: 네이비 면(qss `#UpwiseChatHeader`) 위에 로고 타일 + 'UPWISE' 글자를
        왼쪽에 둔다. 설계 7-1 [1] 의 설정/진단 아이콘은 MVP 범위가 아니다
        (설정 UI 를 만들지 않는다, 설계 7-4 마지막 줄).

        왜 접는가 (사용자 실기 피드백 2026-10-16, 0.4.0)
            "배너에 추가된 기능들이 너무 여러 줄이라 채팅창이 좁아졌다. 배너
            내용은 최소화하고, 경고 메시지 등도 접을 수 있게." 0.4.0 까지 헤더는
            여섯 줄 이상을 상시로 차지했고, 그 줄들은 독의 **세로**를 먹어 전사가
            보이는 높이를 줄였다. 폭은 하네스 47 W 군이 재고 있었지만 높이를 재는
            게이트는 없었다 - 그래서 늘어난 줄이 조용히 쌓였다.

        줄 구성 (접힘이 기본)

            상시   상표 타일 + 상태점 + 권한 배지
                   + 아이콘 넷([공공 API 키] [새 대화] [대화 내보내기]
                     [대화 지우기]) + [메뉴] 토글
            접이식 **한 줄** - 연결 표시(포트) + 상태 칩 + 테마 드롭다운
                   + 모델 드롭다운 (0.5.1)
            공지   접힘 = "안내 N건" 한 줄, 펼침 = 터미널·공존·미로그인 라벨

        왜 넷이 상시로 올라왔나 (사용자 실기 피드백 2026-10-17, 0.4.1)
            "메뉴를 열면 마찬가지로 여러줄로 나오는데 ... 사전 설정과 관련된
            api 키 같은건 메뉴 안에 말고 메뉴 버튼 옆에 둬도 될 것 같습니다
            (api키, 대화 내보내기/지우기 등)." 그래서 독 수준 행동 넷을
            아이콘 전용 버튼으로 상시 줄에 올렸고, 접이식 영역은 다섯 줄에서
            **네 줄**로 줄었다([대화 내보내기]+[대화 지우기] 줄이 통째로
            사라지고 연결 줄에서 버튼 둘이 빠졌다). 글자 버튼으로 올리지
            않는 이유는 HEADER_ACTION_ICON_PX 주석에 있다.

        왜 접이식이 한 줄이 됐나 (사용자 실기 피드백 2026-10-17, 0.5.0)
            "메뉴를 눌러서 나오는 하위 메뉴도 한 줄로 해주세요." 네 줄이
            한 줄로 접혔다 - 두 세그먼트가 드롭다운이 되면서 가로 폭이
            제자리에 들어왔다. 산술은 `_build_more_row` docstring 에 있다.

        접는 단위는 **컨테이너**다. 위젯도 시그널도 objectName 도 그대로 두고
        부모만 바꿨다 - 배선을 다시 짜면 회귀 면이 넓어지고, 이 변경이 고치려는
        것은 배선이 아니라 차지하는 줄 수다.

        경고 줄을 접어도 되는가
            0.4.0 까지 이 docstring 은 "경고 줄은 접거나 끄지 않는다" 였다.
            바뀐 것은 **끄기가 아니라 접기**다. 접힌 상태에서도 "안내 N건" 한
            줄이 남아 안내가 있다는 사실은 화면에 있고, 터미널 동시 사용 경고가
            탐지 불가라는 근거(설계 8 표)는 그 줄을 **지우지** 않는 근거이지
            여섯 줄로 펼쳐 둘 근거가 아니다.

        폭
            접으면 접이식 영역이 레이아웃에서 빠지므로(숨은 위젯은
            minimumSizeHint 에 들어가지 않는다) 독 최소 폭이 내려간다. 게이트
            (<=480 px)는 **펼친 상태에서도** 지켜져야 한다 - 접기로 게이트를
            피하면 펼친 사용자의 화면이 미검증으로 남는다. 두 상태의 실측값은
            하네스 47 W1·50 D3·51 이 재고, 그 로그가 정본이다 - 여기 숫자를
            추정으로 적지 않는다.
        """
        header = QWidget(parent)
        header.setObjectName("UpwiseChatHeader")
        outer = QVBoxLayout(header)
        outer.setContentsMargins(
            HEADER_PADDING, HEADER_PADDING, HEADER_PADDING, HEADER_PADDING
        )
        outer.setSpacing(2)

        chip_row = QWidget(header)
        row = QHBoxLayout(chip_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.brand_link = BrandLink(chip_row)
        self.brand_link.clicked.connect(self._on_brand_clicked)
        row.addWidget(self.brand_link)

        # 상태점(U6)은 접이식 영역이 아니라 **상시 줄**에 남는다. 연결됐는지는
        # 접은 상태에서도 한눈에 보여야 하는 사실이고, 점은 8 px 면이라 줄의
        # 폭을 거의 먹지 않는다. 포트 글자(conn_label)는 접이식 안이다 -
        # 그쪽은 멀티 QGIS 창을 구분할 때만 읽는다.
        #
        # 글자가 아니라 qss 가 그리는 8 px 원이다 - 원 글리프는 이 저장소의
        # cp949 규칙 밖이다(02.projects/CLAUDE.md 인코딩 표).
        self.conn_dot = QLabel("", chip_row)
        self.conn_dot.setObjectName("UpwiseChatConnDot")
        theme_mod.set_state(self.conn_dot, theme_mod.STATE_UNKNOWN)
        row.addWidget(self.conn_dot)

        row.addStretch(1)

        # 폭 수정(2026-10-13): 첫 줄에는 **버튼을 두지 않는다**. 상표 타일과 배지만 남긴다.
        #
        # 이유는 폭이다. QPushButton 의 minimumSizeHint 는 글자 폭이라 버튼은
        # 줄지 않는다. 그래서 한 줄에 모인 버튼의 글자 폭은 그대로 독의 최소
        # 폭이 된다. 0.2.2 가 694 -> 347 로 내린 것이 바로 이 줄을 비운
        # 작업이었고, 그 뒤 0.2.3 의 [내보내기]와 U11 의 [대화 지우기]가 다시
        # 이 줄로 들어와 637 px 까지 되돌아갔다(오프스크린 실측).
        #
        # 그래서 독 수준 행동 버튼 넷을 **두 줄로 나눈다**.
        #   둘째 줄  연결 표시 + [키 설정] + [새 대화]
        #   셋째 줄  [내보내기] + [대화 지우기]
        # 어느 줄도 첫 줄(상표 136 + 배지 133)보다 넓지 않고, 그래서 헤더는
        # 독 최소 폭의 제약에서 빠진다 - 남는 제약은 프리셋 격자다(실측 300 px).
        # 넷을 한 줄에 모으면 글자 폭 합이 다시 400 px 을 넘는다.
        self.badge_label = QLabel(BADGE_UNKNOWN, chip_row)
        self.badge_label.setObjectName("UpwiseChatGateBadge")
        # 0.4.2: 이 라벨이 독 최소 폭을 정하지 못하게 박는다(BADGE_LABEL_MIN_W
        # 주석). 문면 축약과 **따로** 필요한 장치다 - 축약한 문면도 357 px 이라
        # 이것이 없으면 첫 턴 뒤 독 최소 폭이 임계를 넘는다.
        self.badge_label.setMinimumWidth(BADGE_LABEL_MIN_W)
        self.badge_label.setToolTip(
            "첫 턴의 init 에서 권한 점검 결과가 옵니다. 보내기 전에는 알 수 없습니다."
        )
        # 0.2.2: 배지 3상태를 색으로도 가른다(설계 docs/2 3-3 의 3값과 같은 축).
        # 글자만으로는 훑어볼 때 "확인" 과 "실패" 가 같은 주황 테두리로 보였다.
        theme_mod.set_state(self.badge_label, theme_mod.STATE_UNKNOWN)
        row.addWidget(self.badge_label)

        # 상시 아이콘 넷(0.4.2). [메뉴] **왼쪽**에 둔다 - 토글은 이 줄의
        # 성격을 바꾸는 유일한 버튼이라 끝자리가 맞고, 넷은 토글과 배지
        # 사이에서 한 덩이로 읽힌다.
        row.addWidget(self._build_header_actions(chip_row))

        # 펼침 토글. [공공 API 키] 토글과 **같은 qss 규칙**을 받는다
        # (`#UpwiseChatKeysButton` 선택자 목록에 이름을 더했을 뿐이다) -
        # 새 색도 새 토큰도 만들지 않는다(docs/6 3절).
        #
        # 시그널은 `setChecked` 뒤에 잇는다. 먼저 이으면 저장된 상태를 세우는
        # 그 한 번이 슬롯을 때리고, 슬롯이 아직 없는 `self.header_more` 를
        # 만진다.
        self.header_toggle = QPushButton(HEADER_TOGGLE_TEXT, chip_row)
        self.header_toggle.setObjectName("UpwiseChatHeaderToggle")
        self.header_toggle.setCheckable(True)
        self.header_toggle.setToolTip(HEADER_TOGGLE_TIP)
        self.header_toggle.setChecked(bool(self.header_expanded))
        self.header_toggle.toggled.connect(self._on_header_toggled)
        row.addWidget(self.header_toggle)
        outer.addWidget(chip_row)

        # 접이식 영역. 아래 한 줄이 여기 들어간다. 컨테이너 하나를
        # 숨겼다 보이는 구조인 이유는 docstring 에 적었다 - 위젯과 시그널을
        # 그대로 두고 부모만 바꾼다.
        self.header_more = QWidget(header)
        self.header_more.setObjectName("UpwiseChatHeaderMore")
        more = QVBoxLayout(self.header_more)
        more.setContentsMargins(0, 0, 0, 0)
        more.setSpacing(2)

        # 접이식 영역은 **한 줄**이다(0.5.1, 사용자 실기 피드백 2026-10-17).
        # 네 줄을 한 줄로 접는 근거와 폭 산술은 `_build_more_row` docstring 에
        # 있다.
        more.addWidget(self._build_more_row(self.header_more))
        outer.addWidget(self.header_more)

        outer.addWidget(self._build_notice_box(header))
        # 저장된 접힘 상태를 위젯에 세운다. 토글의 `setChecked` 로는 모자라다 -
        # 시그널을 아직 안 이었을 때(기본값이 접힘이라 체크 변화가 없을 때)
        # 컨테이너 가시성이 Qt 기본값 그대로 남는다.
        self._apply_header_expanded()
        self._apply_notice_expanded()
        return header

    def _build_notice_box(self, parent):
        """머리말 공지 묶음. 접힘 = "안내 N건" 한 줄, 펼침 = 라벨 그대로.

        세 라벨을 **안쪽 컨테이너**(`notice_list`)에 넣고 그 컨테이너만
        숨긴다. 라벨 자신의 `setVisible` 은 "이 안내가 켜졌는가" 를 말하는
        값이고(공존·미로그인이 탐지 결과로 그것을 바꾼다), 접힘은 "지금
        펼쳐 보이는가" 라서 축이 다르다. 한 축으로 둘을 표현하면 접었다
        펴는 순간 꺼져 있던 안내까지 켜진다.

        Args:
            parent: 헤더 위젯.

        Returns:
            QWidget: 공지 묶음 컨테이너.
        """
        self.notice_box = QWidget(parent)
        self.notice_box.setObjectName("UpwiseChatNoticeBox")
        box = QVBoxLayout(self.notice_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)

        # 접힌 줄. 왼쪽 정렬인 이유는 이것이 버튼이 아니라 **줄의 머리말**로
        # 읽혀야 해서다 - 헤더의 행동 버튼들은 오른쪽에 모여 있다.
        toggle_row = QWidget(self.notice_box)
        toggle_layout = QHBoxLayout(toggle_row)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(6)
        self.notice_toggle = QPushButton(NOTICE_TOGGLE_TEXT % 0, toggle_row)
        # [공공 API 키]·[메뉴] 토글과 같은 qss 규칙이다. 새 색이 없다.
        self.notice_toggle.setObjectName("UpwiseChatNoticeToggle")
        self.notice_toggle.setCheckable(True)
        self.notice_toggle.setToolTip(NOTICE_TOGGLE_TIP)
        self.notice_toggle.setChecked(bool(self._notice_expanded))
        self.notice_toggle.toggled.connect(self._on_notice_toggled)
        toggle_layout.addWidget(self.notice_toggle)
        toggle_layout.addStretch(1)
        box.addWidget(toggle_row)

        self.notice_list = QWidget(self.notice_box)
        self.notice_list.setObjectName("UpwiseChatNoticeList")
        notices = QVBoxLayout(self.notice_list)
        notices.setContentsMargins(0, 0, 0, 0)
        notices.setSpacing(2)

        self.terminal_notice_label = QLabel(TERMINAL_NOTICE, self.notice_list)
        self.terminal_notice_label.setObjectName("UpwiseChatTerminalNotice")
        self.terminal_notice_label.setWordWrap(True)
        # 명시로 켠다. Qt 는 **한 번도 보인 적 없는** 자식에 WA_WState_Hidden
        # 을 남기므로, 묶음이 접힌 채로 떠 있으면 이 라벨의 `isHidden()` 이
        # 참이 된다. 그러면 "안내를 껐다" 와 "묶음을 접었다" 가 한 값으로
        # 섞인다 - 하네스 14 D·27 이 그 값을 "상시 경고가 살아 있는가" 로
        # 읽고 있다.
        self.terminal_notice_label.setVisible(True)
        notices.addWidget(self.terminal_notice_label)

        # 공존 안내 1줄(0.3.0, 설계 2-5 조치 2). 같은 QGIS 에 상류 플러그인
        # (T1)이 적재돼 있을 때만 보인다. 터미널 경고와 **다른 줄**인 이유는
        # 사실이 다르기 때문이다 - 터미널 경고는 탐지 불가라 상시이고, 이쪽은
        # 탐지로 판정된다. **비활성 사유가 아니다**: 기능은 다 돈다.
        self.coexist_notice_label = QLabel("", self.notice_list)
        self.coexist_notice_label.setObjectName("UpwiseChatTerminalNotice")
        self.coexist_notice_label.setWordWrap(True)
        self.coexist_notice_label.hide()
        notices.addWidget(self.coexist_notice_label)

        # 미로그인 soft 안내 1줄(0.4.0, 가드 A). 공존 안내와 **같은 자리·
        # 같은 성격**이다 - 미충족이 아니라 경고라서 전제조건 바에 올리지
        # 않는다. 다만 근거가 더 약하다: 공존은 탐지로 판정되지만 이쪽은
        # 자격 파일 1개와 환경변수 1개만 본 **추정**이다. 그래서 문구가
        # "확인되지 않습니다" 이고 전송은 막지 않는다(detect 주석 참조).
        #
        # 이 안내만 **발화 시 자동 펼침** 대상이다(refresh_login_notice).
        # 터미널·공존은 정적 상설 안내라 기본 접힘이다.
        self.login_notice_label = QLabel("", self.notice_list)
        self.login_notice_label.setObjectName("UpwiseChatTerminalNotice")
        self.login_notice_label.setWordWrap(True)
        self.login_notice_label.hide()
        notices.addWidget(self.login_notice_label)

        box.addWidget(self.notice_list)
        return self.notice_box

    # ------------------------------------------------------------------
    # 헤더 접기 / 공지 접기
    # ------------------------------------------------------------------

    def _sync_toggle(self, button, checked):
        """토글 버튼의 체크 상태를 시그널 없이 맞춘다.

        시그널을 막는 이유는 되먹임이다. 적용 함수가 버튼을 세우고 그
        `toggled` 가 다시 적용 함수를 부르면, 프로그램이 접은 것이 사용자가
        접은 것으로 기록된다(공지 묶음의 `_notice_user_collapsed`).

        Args:
            button: QPushButton (checkable).
            checked: 세울 값.
        """
        if button is None or button.isChecked() == bool(checked):
            return
        blocked = button.blockSignals(True)
        button.setChecked(bool(checked))
        button.blockSignals(blocked)

    def _apply_header_expanded(self):
        """지금 상태를 접이식 영역과 토글 버튼에 반영한다.

        Returns:
            bool: 펼쳐진 상태인가.
        """
        expanded = bool(self.header_expanded)
        more = getattr(self, "header_more", None)
        if more is not None:
            more.setVisible(expanded)
        self._sync_toggle(getattr(self, "header_toggle", None), expanded)
        return expanded

    def _on_header_toggled(self, checked):
        """[메뉴] 토글. 사용자가 누른 경로다.

        Args:
            checked: 눌린 뒤의 체크 상태.

        Returns:
            bool: 펼쳐진 상태인가.
        """
        return self.set_header_expanded(checked)

    def set_header_expanded(self, expanded):
        """헤더 접이식 영역을 펼치거나 접고 그 상태를 저장한다.

        저장 실패(QGIS 밖, INI 쓰기 실패)에도 화면은 바꾼다 - 테마 모드와
        같은 처분이다(`set_theme_mode`).

        Args:
            expanded: 펼칠 것인가.

        Returns:
            bool: 펼쳐진 상태인가.
        """
        self.header_expanded = bool(expanded)
        theme_mod.write_header_expanded(self.header_expanded)
        return self._apply_header_expanded()

    def _notice_labels(self):
        """공지 묶음 안의 라벨들. 순서는 화면 순서다.

        Returns:
            list: QLabel 목록. 아직 안 세워졌으면 빈 목록이다.
        """
        names = ("terminal_notice_label", "coexist_notice_label",
                 "login_notice_label")
        out = []
        for name in names:
            label = getattr(self, name, None)
            if label is not None:
                out.append(label)
        return out

    def notice_count(self):
        """지금 켜져 있는 머리말 안내 건수.

        묶음이 접혔는지는 보지 않는다 - 접힌 줄이 말해야 하는 것은 "안내가
        몇 건 있는가" 이지 "몇 건이 지금 그려져 있는가" 가 아니다.

        Returns:
            int: 켜진 안내 수.
        """
        count = 0
        for label in self._notice_labels():
            if label.isHidden() or not label.text():
                continue
            count += 1
        return count

    def _apply_notice_expanded(self):
        """공지 묶음의 접힘 상태와 건수 표시를 지금 사실에 맞춘다.

        Returns:
            bool: 펼쳐진 상태인가.
        """
        box = getattr(self, "notice_box", None)
        if box is None:
            return False
        expanded = bool(self._notice_expanded)
        count = self.notice_count()
        self.notice_toggle.setText(NOTICE_TOGGLE_TEXT % count)
        self.notice_list.setVisible(expanded)
        self._sync_toggle(self.notice_toggle, expanded)
        # 안내가 0 건이면 묶음 자체를 감춘다. "안내 0건" 은 줄만 먹고
        # 아무 사실도 전하지 않는다.
        box.setVisible(count > 0)
        return expanded

    def set_notice_expanded(self, expanded, by_user=False):
        """공지 묶음을 펼치거나 접는다.

        Args:
            expanded: 펼칠 것인가.
            by_user: 사용자가 직접 조작한 경로인가. 사용자가 접었으면 이번
                세션 동안 새 안내가 발화해도 자동으로 펼치지 않는다.

        Returns:
            bool: 펼쳐진 상태인가.
        """
        self._notice_expanded = bool(expanded)
        if by_user and not self._notice_expanded:
            self._notice_user_collapsed = True
        return self._apply_notice_expanded()

    def _on_notice_toggled(self, checked):
        """공지 묶음 토글. 사용자가 누른 경로다.

        Args:
            checked: 눌린 뒤의 체크 상태.

        Returns:
            bool: 펼쳐진 상태인가.
        """
        return self.set_notice_expanded(checked, by_user=True)

    def _tinted_icon(self, standard_icon, size):
        """표준 아이콘을 헤더의 색 짝으로 칠한 QIcon 하나 (0.4.2).

        왜 칠하는가
            QStyle 표준 아이콘은 **밝은 바탕**을 전제로 그려져 있다. 네이비
            헤더(theme.NAVY) 위에 그대로 얹으면 어두운 획이 묻힌다 - 알파
            합성 뒤 실측으로 [새 대화] 아이콘(SP_BrowserReload)은 잉크
            픽셀의 52% 만 대비 3.0(WCAG 1.4.11 비문자 임계)을 넘었다. 한
            색으로 칠하면 같은 아이콘이 82% 로, 나머지 셋은 97~99% 로
            오른다(2026-10-17 실측).

        색은 **헤더가 이미 쓰는 짝 두 개**다 - 평상시 액센트, 눌렸거나
        마우스가 올라왔을 때 네이비. qss 의 `#UpwiseChatHeaderToggle:checked`
        가 쓰는 반전과 같은 짝이라 새 색이 없다. 꺼진 상태는 칩 회색이고
        이것도 `#UpwiseChatExportButton:disabled` 가 쓰던 값이다.

        Qt 가 모드·상태마다 다른 그림을 고르므로(QIcon.On = 체크됨,
        Active = 마우스가 올라옴) 색 전환에 우리 코드가 끼지 않는다.

        Args:
            standard_icon: `QStyle.SP_*` 값.
            size: 아이콘 변 길이(px).

        Returns:
            QIcon: 상태별 그림을 담은 아이콘.
        """
        base = self.style().standardIcon(standard_icon).pixmap(size, size)
        icon = QIcon()
        for mode, state, color in (
                (QIcon.Normal, QIcon.Off, theme_mod.ACCENT),
                (QIcon.Active, QIcon.Off, theme_mod.NAVY),
                (QIcon.Normal, QIcon.On, theme_mod.NAVY),
                (QIcon.Active, QIcon.On, theme_mod.NAVY),
                (QIcon.Disabled, QIcon.Off, theme_mod.CHIP_FG),
                (QIcon.Disabled, QIcon.On, theme_mod.CHIP_FG)):
            icon.addPixmap(tint_pixmap(base, color), mode, state)
        return icon

    def _icon_action(self, parent, text, tip, standard_icon,
                     checkable=False):
        """상시 줄에 올리는 아이콘 전용 버튼 하나 (0.4.2).

        `setText` 를 **버리지 않는다.** `ToolButtonIconOnly` 라 화면에는 안
        나오지만 문구는 살아 있고, 그 덕에 확인 상태 전이(두 번 누르기)가
        문구를 바꾸는 기존 코드 그대로 돌고 하네스도 같은 문자열을 읽는다.
        접근성 이름에도 같은 문구를 건다 - 아이콘만 남으면 스크린 리더가
        읽을 것이 없다.

        아이콘은 `QStyle` 표준 아이콘이다. 새 PNG 를 넣지 않는 이유는 배포
        zip 필터와 패키지 크기를 건드리지 않으려는 것이고(README 5 Z3),
        표준 아이콘은 사용자의 Qt 스타일을 그대로 따라 테마가 바뀌어도
        같이 바뀐다.

        Args:
            parent: 부모 위젯.
            text: 기존 버튼 문구 상수. 툴팁이 아니라 **문구**다.
            tip: 기본 툴팁.
            standard_icon: `QStyle.SP_*` 값.
            checkable: 체크 상태를 쓰는 버튼인가(키 패널 토글, 확인 상태).

        Returns:
            QToolButton: 만든 버튼. objectName 은 **부르는 쪽**이 건다 -
                qss 이름이 호출 지점에 보여야 어느 규칙을 받는지 읽힌다.
        """
        button = QToolButton(parent)
        button.setText(text)
        button.setAccessibleName(text)
        button.setToolTip(tip)
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        button.setIcon(self._tinted_icon(standard_icon,
                                         HEADER_ACTION_ICON_PX))
        button.setIconSize(QSize(HEADER_ACTION_ICON_PX, HEADER_ACTION_ICON_PX))
        # autoRaise 가 없으면 네 버튼이 각자 테두리 상자를 그려 줄이 시끄럽다.
        button.setAutoRaise(True)
        button.setCursor(Qt.PointingHandCursor)
        if checkable:
            button.setCheckable(True)
        return button

    def _caption_cell(self, parent, button, caption):
        """아이콘 버튼 하나와 그 아래 문자 설명을 한 칸으로 묶는다 (0.5.3).

        왜 아래인가
            옆에 두는 배치와 둘 다 쟀다(하네스 69, 실 글꼴 계보). 캡션을
            줄지 않게 두면 아래는 독 최소 폭 400(여유 80), 옆은 476
            (여유 4)이다. 여유 4 px 은 쓸 수 없다 - 같은 프로젝트에서
            여유 7 px 안(README 4 ⓑ 473 px)을 "너무 빠듯해" 기각한 선례가
            있다. 아래 배치의 대가는 헤더 세로 +8 px 이고, 그쪽이 폭보다
            싸다(헤더는 접힘 상태로 기동한다).

        Args:
            parent: 아이콘 넷을 담은 상자.
            button: `_icon_action` 이 만든 버튼.
            caption: 버튼 아래에 쓸 문자 설명.

        Returns:
            QWidget: 버튼과 캡션을 담은 칸.
        """
        cell = QWidget(parent)
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(HEADER_ACTION_CAPTION_SPACING)
        lay.addWidget(button, 0, Qt.AlignHCenter)

        label = QLabel(caption, cell)
        label.setObjectName("UpwiseChatActionCaption")
        label.setAlignment(Qt.AlignCenter)
        # 캡션에는 툴팁을 **달지 않는다.** 버튼 툴팁은 상태마다 바뀌는데
        # (`CLEAR_CONFIRM_TIP`·`CLEAR_BUSY_TIP`·`NEW_BUSY_TIP` 등
        # `_refresh_clear_button`·`_refresh_new_button` 이 갈아 끼운다)
        # 생성 시점 값을 베껴 두면 확인 상태·바쁜 상태에서 **캡션과 버튼이
        # 서로 다른 말을 한다**. 같은 뜻을 가진 문자열을 두 군데 두지 않는
        # 것이 이 패키지의 규약이기도 하다(README 5 "모델 대면 문자열은 한
        # 쌍으로 묶여 있다" 와 같은 축). 툴팁은 바로 위 아이콘이 들고 있다.
        # 폭 예산(HEADER_ACTION_CAPTION_MIN_W 주석). sizePolicy 는 건드리지
        # 않는다 - `QSizePolicy.Ignored` 를 같이 걸면 qSmartMinSize 가
        # sizeHint 기여를 0 으로 만들어 캡션이 어느 폭에서도 아이콘 폭으로
        # 깔린다(69 1회차 실측: 어느 독 폭에서나 19 px).
        label.setMinimumWidth(HEADER_ACTION_CAPTION_MIN_W)
        lay.addWidget(label, 0, Qt.AlignHCenter)
        return cell

    def _build_header_actions(self, parent):
        """상시 줄의 아이콘 넷 (0.4.2, 사용자 실기 피드백 2026-10-17).

        넷을 **한 컨테이너**로 묶는 이유는 폭이다. 상시 줄에 위젯을 하나
        더할 때마다 줄 간격(8 px)이 하나씩 붙으므로, 넷을 따로 붙이면
        간격만 32 px 이 는다. 묶으면 바깥에 간격 하나(8 px)만 내고 안쪽은
        0 이다(HEADER_ACTION_SPACING).

        순서는 기존 두 줄의 읽는 순서를 그대로 이은다.
            [공공 API 키]  설정 성격. 누르면 패널이 열린다(체크 상태 = 열림)
            [새 대화]      맥락을 끊는다. 두 번 누르기 확인(U16)
            [대화 내보내기] 저장
            [대화 지우기]  화면을 비운다. 두 번 누르기 확인(U11).
                           되돌릴 수 없으므로 끝자리다(U11 의 결정)

        확인 상태(두 번 누르기)를 아이콘에서 어떻게 보이나
            **체크 상태**로 보인다. 아이콘 버튼은 글자가 없어 "정말
            지울까요?" 를 화면에 띄울 자리가 없으므로, qss 의 `:checked`
            면(액센트 반전)이 그 자리를 대신한다. 툴팁도 확인 문구로 바뀌지만
            그쪽은 **마우스를 올려야** 보이므로 주 표시로 삼지 않았다.
            문구 자체는 `setText` 로 그대로 들어 있어 전이 코드와 하네스는
            바뀌지 않았다.

        문자 설명(0.5.3, 사용자 지시 2026-10-19)
            넷은 이제 아이콘 **아래 캡션**을 하나씩 달고 있다
            (`_caption_cell`, 단어는 `HEADER_ACTION_CAPTIONS`). 아이콘만
            으로는 뜻이 안 읽힌다는 실기 피드백이고, 아이콘 자체를 바꾸는
            길은 이미 기각됐다(README 4 ⓐ - 표준 아이콘이 null 이면 버튼이
            글자 폭으로 떨어져 독 최소 폭 495 px).

            캡션은 버튼 `text` 가 아니라 별 QLabel 이다 - 이유는
            `HEADER_ACTION_CAPTIONS` 주석에 있다(확인 상태의 text 가
            폭으로 들어오는 것을 막는다).

        Args:
            parent: 상시 줄 위젯.

        Returns:
            QWidget: 아이콘 넷을 담은 컨테이너.
        """
        box = QWidget(parent)
        box.setObjectName("UpwiseChatHeaderActions")
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(HEADER_ACTION_SPACING)

        # 공공 API 키 토글(0.2.1). 체크 상태가 패널 가시성과 1:1 이다.
        # 표준 아이콘에 열쇠가 없어 네트워크 자원(SP_DriveNetIcon)을 쓴다 -
        # 이 키들이 여는 것이 공공 데이터 **망**이고, 열쇠 글리프를 쓰려면
        # 새 PNG 자산이 필요하다(배포 필터 축, README 5 Z3).
        self.keys_button = self._icon_action(
            box, KEYS_BUTTON_TEXT, KEYS_BUTTON_TIP,
            QStyle.SP_DriveNetIcon, checkable=True)
        self.keys_button.setObjectName("UpwiseChatKeysButton")
        self.keys_button.toggled.connect(self._on_keys_toggled)
        row.addWidget(self._caption_cell(box, self.keys_button,
                                         HEADER_ACTION_CAPTIONS[0]))

        # 새 대화(U16). 맥락을 처음부터 다시 돌린다 - 그래서 재시작 기호다.
        # 나머지 셋은 내보내기와 같은 qss 이름을 받는다(새 색을 만들지 않는다).
        self.new_button = self._icon_action(
            box, NEW_BUTTON_TEXT, NEW_BUTTON_TIP,
            QStyle.SP_BrowserReload, checkable=True)
        self.new_button.setObjectName("UpwiseChatExportButton")
        self.new_button.clicked.connect(self._on_new_clicked)
        row.addWidget(self._caption_cell(box, self.new_button,
                                         HEADER_ACTION_CAPTIONS[1]))

        # 전사 내보내기(0.2.3). 저장 기호를 그대로 쓴다.
        self.export_button = self._icon_action(
            box, EXPORT_BUTTON_TEXT, EXPORT_BUTTON_TIP,
            QStyle.SP_DialogSaveButton)
        self.export_button.setObjectName("UpwiseChatExportButton")
        self.export_button.clicked.connect(self._on_export_clicked)
        row.addWidget(self._caption_cell(box, self.export_button,
                                         HEADER_ACTION_CAPTIONS[2]))

        # 대화 지우기(U11). 휴지통이고, 되돌릴 수 없으므로 오른쪽 끝이다.
        self.clear_button = self._icon_action(
            box, CLEAR_BUTTON_TEXT, CLEAR_BUTTON_TIP,
            QStyle.SP_TrashIcon, checkable=True)
        self.clear_button.setObjectName("UpwiseChatExportButton")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        row.addWidget(self._caption_cell(box, self.clear_button,
                                         HEADER_ACTION_CAPTIONS[3]))
        return box

    def _build_more_row(self, parent):
        """접이식 영역의 **한 줄** (0.5.1, 사용자 실기 피드백 2026-10-17).

        무엇이 들어가나
            왼쪽  연결 표시(포트) + 상태 칩 - 둘 다 **상태**다
            오른쪽 테마 드롭다운 + 모델 드롭다운 - 둘 다 **설정**이다

        상시 줄과 같은 배치다(상표는 왼쪽, 버튼은 오른쪽). 상태를 왼쪽에
        모으고 고르는 것을 오른쪽에 모으면 두 줄이 같은 규칙으로 읽힌다.

        왜 세그먼트에서 드롭다운으로 바꿨나
            네 줄을 한 줄로 접으라는 요구를 세그먼트로는 **폭이 못 받친다.**
            같은 계보 실측으로 테마 3칸은 190 px, 모델 4칸은 361 px 이고
            (라틴 문자 Sonnet·Haiku 가 한글보다 넓다), 둘을 한 줄에 모으면
            그 합이 그대로 펼친 상태의 독 최소 폭으로 올라간다 - 버튼은
            글자 폭 아래로 줄지 않는다(README 5 Qt 최소 폭 함정). 임계는
            480 px 이라 세그먼트 한 줄 안은 처음부터 불가능하다.

            드롭다운은 **고른 값 하나의 폭**만 차지한다. 같은 계보 실측으로
            테마 81 px + 모델 132 px 이고, 두 라벨(최소 폭 1 px)과 간격을
            더해도 이 줄은 상시 줄보다 좁다 - 그래서 펼쳐도 독 최소 폭이
            오르지 않는다. 실측값은 하네스 47 W1·51 D4·D11 로그가 정본이다.

            잃은 것은 "선택지가 눌리기 전에도 다 보인다" 하나다(0.2.2 가
            세그먼트를 고른 이유). 값·문구·툴팁·저장 창구·배타성은 그대로다 -
            배타 선택은 QButtonGroup 대신 QComboBox 가 구조로 집행한다.
            QComboBox 팝업은 모달이 아니고 중첩 이벤트 루프를 돌리지 않는다
            (설계 3-5 의 금지 목록은 QMessageBox·QDialog.exec·QFileDialog·
            QProgressDialog 다).

        Args:
            parent: 접이식 컨테이너.

        Returns:
            QWidget: 접이식 영역의 한 줄.
        """
        row = QWidget(parent)
        row.setObjectName("UpwiseChatMoreRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 연결 표시(U6). 포트 글자는 멀티 QGIS 창을 구분할 때만 읽으므로
        # 접이식 안이다 - 상시 줄에는 8 px 상태점만 남는다.
        self.conn_label = QLabel("", row)
        self.conn_label.setObjectName("UpwiseChatConn")
        self.conn_label.setWordWrap(True)
        # 줄지 않는 헤더 라벨을 만들지 않는다(CONN_LABEL_MIN_W 주석).
        self.conn_label.setMinimumWidth(CONN_LABEL_MIN_W)
        self.conn_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        theme_mod.set_state(self.conn_label, theme_mod.STATE_UNKNOWN)
        # 늘림 인자로 남는 폭을 두 라벨이 받는다. 늘림 없이 빈 칸
        # (`addStretch`)에 남는 폭을 주면 줄바꿈 라벨이 sizeHint 폭(수십 px)
        # 에 머물러 글자가 여러 줄로 접히고, 그만큼 **헤더가 세로로 높아진다**
        # (실측: 그 배치에서 펼친 헤더 233 px). 한 줄로 접는 변경이 세로를
        # 늘리면 피드백의 본 축을 거꾸로 가는 것이다.
        layout.addWidget(self.conn_label, 1)

        # 상태 칩(0.2.2). 행동이 아니라 **상태 표시**라 상시 줄에 남길
        # 셋(상표·상태점·배지)보다 한 단 덜 급하다.
        #
        # 0.5.1: 자기 줄을 잃고 연결 표시 옆으로 왔다. 그래서 상한을
        # 박는다(CHIP_LABEL_MIN_W) - 칩 문면은 init 이 보고한 모델 이름을
        # 담아 길어지고, 상한이 없으면 그 길이가 이 줄의 최소 폭이 되어
        # 0.4.1 의 권한 배지와 같은 결함이 다시 생긴다(README 4 폭 게이트
        # 기각 항목). 줄바꿈이 있으므로 글자는 잘리지 않는다.
        self.chip_label = QLabel("모델 -  ·  도구 -  ·  MCP -", row)
        self.chip_label.setObjectName("UpwiseChatChip")
        self.chip_label.setWordWrap(True)
        self.chip_label.setMinimumWidth(CHIP_LABEL_MIN_W)
        self.chip_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # 칩이 연결 표시보다 긴 문면이라 늘림을 2로 둔다(연결 1 : 칩 2).
        layout.addWidget(self.chip_label, 2)

        # 드롭다운 둘은 늘림 0 이라 고른 값의 폭에 머문다. 빈 칸을 따로
        # 두지 않는다 - 남는 폭은 위 두 라벨이 받는다.
        layout.addWidget(self._build_theme_combo(row))
        layout.addWidget(self._build_model_combo(row))
        return row

    def _build_theme_combo(self, parent):
        """테마 3값 드롭다운을 만들어 돌려준다 (U2 + U9, 0.5.1 에서 드롭다운).

        값 셋이 배타적이라는 전제는 0.2.2 와 같다 - 체크박스 하나로는
        "시스템을 따른다" 를 표현할 수 없다. 바뀐 것은 그 배타성을 무엇이
        집행하는가뿐이다(QButtonGroup -> QComboBox). 문구·툴팁·저장 창구는
        theme 모듈 상수를 그대로 쓴다.

        Args:
            parent: 접이식 한 줄.

        Returns:
            QComboBox: 테마 드롭다운.
        """
        box = QComboBox(parent)
        box.setObjectName("UpwiseChatThemePick")
        box.setToolTip(THEME_SEG_TIP)
        box.setCursor(Qt.PointingHandCursor)
        for mode in theme_mod.THEME_MODES:
            # 값을 userData 로 들고 다닌다. 표시 문구로 되찾으면 문구가
            # 바뀔 때 조용히 깨진다.
            box.addItem(theme_mod.THEME_MODE_LABELS[mode], mode)
            box.setItemData(box.count() - 1, theme_mod.THEME_MODE_TIPS[mode],
                            Qt.ToolTipRole)
        self.theme_pick = box
        # 선택을 **먼저** 세우고 시그널을 뒤에 잇는다. 먼저 이으면 초기값을
        # 세우는 그 한 번이 슬롯을 때려 저장까지 돈다.
        self._refresh_theme_pick()
        # `activated` 는 사용자가 고른 경우에만 온다. `currentIndexChanged` 는
        # 코드가 인덱스를 세울 때도 와서 _refresh 와 서로를 때린다.
        box.activated.connect(
            lambda index: self.set_theme_mode(box.itemData(index)))
        return box

    def set_theme_mode(self, mode):
        """독 안의 테마를 바꾸고 저장한다 (U2).

        QGIS 전역 스타일시트도 전역 팔레트도 건드리지 않는다 - 바뀌는 것은 독
        내용 위젯과 그 자식뿐이다(theme.apply_dock_theme 의 계약).

        Args:
            mode: theme.THEME_MODES 중 하나. 그 밖이면 기본값으로 접는다.

        Returns:
            str: 적용된 모드.
        """
        resolved = theme_mod.normalize_theme_mode(mode)
        self.theme_mode = resolved
        # 저장 실패(QGIS 밖, INI 쓰기 실패)에도 표시는 바꾼다. 이번 세션에서
        # 보이는 것과 다음 세션에서 복원되는 것이 다를 수 있을 뿐이다.
        theme_mod.write_theme_mode(resolved)
        self.theme_dark = theme_mod.apply_dock_theme(self.body, resolved)
        # 0.5.3: 팝업 목록도 같이 따라온다. 이 한 줄이 없으면 다크로 바꿔도
        # 드롭다운 목록만 밝은 면에 흐린 글자로 남는다(2026-10-19 실기).
        self._apply_combo_popup_theme(self.theme_dark)
        self._refresh_theme_pick()
        return resolved

    def _apply_combo_popup_theme(self, dark):
        """테마·모델 드롭다운의 **팝업 목록**에 테마 팔레트를 건다 (0.5.3).

        왜 따로 거는가
            팝업 목록은 콤보의 자식이되 **자기 창**(`QComboBoxPrivateContainer`)
            에 얹힌 뷰다. `theme.apply_dock_theme` 가 거는 것은 독 내용
            위젯의 스타일시트와 팔레트이고, 팝업은 그 서브트리 밖이라
            둘 다 닿지 않는다. qss 로 가리킬 수도 없다 - 선택자 규약이
            objectName·동적 속성으로 제한돼 있다(후손 선택자 금지,
            하네스 48 V25).

            그래서 남은 길이 팔레트와 **뷰 자기 스타일시트**이고, 그것이
            기존 테마 아키텍처의 방식이다(`dock_palette` 와 같은 층).

        무엇이 고쳐지나
            2026-10-19 실기 실측: 비선택 항목 글자가 #cbd5e1 on #f0f0f0
            = **대비 1.30**, 라이트·다크 동일, 다크 테마 미반영. 콤보
            자신의 qss `color`(`chip_fg`)가 팝업 뷰에 상속되는데 면은
            사용자 Qt 스타일의 밝은 회색이었다.

            **고치는 것은 면 하나다.** 항목 글자색은 조상 콤보 qss 의
            `color` 로 고정이고 어느 하류 경로로도 못 바꾼다(조건 격자
            실측 - `theme.popup_palette` docstring). 그래서 면을 헤더
            네이비로 두고 대비 11.946 을 얻는다. 색·근거는 전부
            `theme.popup_palette`·`theme.popup_qss` 에 있고 새 색은 없다.

        Args:
            dark: 다크로 그리는가.

        Returns:
            int: 팔레트를 건 콤보 수. 0 이면 아직 안 세워진 것이다.
        """
        pal = theme_mod.popup_palette(bool(dark))
        qss = theme_mod.popup_qss(bool(dark))
        done = 0
        for box in (getattr(self, "theme_pick", None),
                    getattr(self, "model_pick", None)):
            if box is None:
                continue
            # `view()` 는 팝업 뷰를 **만들어서라도** 돌려준다 - 사용자가
            # 아직 한 번도 열지 않은 상태에서도 색이 선다.
            view = box.view()
            if view is None:
                continue
            # ID 선택자로 조상 qss 를 이기려면 이름이 있어야 한다
            # (theme.popup_qss docstring).
            view.setObjectName(theme_mod.POPUP_VIEW_OBJECT_NAME)
            # 스타일시트를 먼저, 팔레트를 뒤에 건다(README 5 순서 함정 -
            # QStyleSheetStyle polish 가 팔레트를 되돌린다).
            view.setStyleSheet(qss)
            view.setPalette(pal)
            viewport = view.viewport()
            if viewport is not None:
                # 뷰포트는 기본이 투명이라 팔레트만 걸면 아래 창 색이
                # 비친다. 자기 면을 칠하게 켜 둔다.
                viewport.setAutoFillBackground(True)
                viewport.setPalette(pal)
            container = view.window()
            if container is not None and container is not view:
                container.setPalette(pal)
                container.setAutoFillBackground(True)
            done += 1
        return done

    def _refresh_theme_pick(self):
        """드롭다운의 고른 값을 지금 모드에 맞춘다.

        Returns:
            str: 드롭다운이 가리키는 모드.
        """
        box = self.theme_pick
        index = box.findData(self.theme_mode)
        if index >= 0 and box.currentIndex() != index:
            # `setCurrentIndex` 는 `activated` 를 내지 않는다(그쪽은 사용자
            # 조작 전용)이므로 되돌아오는 호출이 없다.
            box.setCurrentIndex(index)
        return str(box.currentData() or "")

    def _build_model_combo(self, parent):
        """모델 선택 4값 드롭다운을 만들어 돌려준다 (0.4.0, 0.5.1 에서 드롭다운).

        값 넷이 배타적이라 테마와 같은 꼴이다(U9). 0.4.0 은 이것을 세그먼트로
        뒀고 그때의 반대 근거는 "콤보 박스는 이 패키지에 선례가 없다" 였다 -
        0.5.1 이 접이식을 한 줄로 접으면서 그 선례를 열었고, 두 컨트롤은
        같은 꼴이어야 하므로 둘을 같이 옮겼다. 문구·툴팁·CLI 인자 창구는
        posture 모듈 상수를 그대로 쓴다.

        모델 라벨은 라틴 문자라 한글보다 넓다 - 세그먼트 4칸이 361 px 이고
        그 값이 한 줄 압축을 막은 당사자다(`_build_more_row` docstring).

        Args:
            parent: 접이식 한 줄.

        Returns:
            QComboBox: 모델 드롭다운.
        """
        box = QComboBox(parent)
        box.setObjectName("UpwiseChatModelPick")
        box.setToolTip(MODEL_SEG_TIP)
        box.setCursor(Qt.PointingHandCursor)
        for choice in posture_mod.MODEL_CHOICES:
            box.addItem(posture_mod.MODEL_CHOICE_LABELS[choice], choice)
            box.setItemData(box.count() - 1,
                            posture_mod.MODEL_CHOICE_TIPS[choice],
                            Qt.ToolTipRole)
        self.model_pick = box
        # 테마 드롭다운과 같은 순서다 - 선택을 먼저 세우고 시그널을 뒤에 잇는다.
        self._refresh_model_pick()
        box.activated.connect(
            lambda index: self.set_model_choice(box.itemData(index)))
        return box

    def set_model_choice(self, choice):
        """모델 선택을 바꾸고 저장한다 (0.4.0).

        **지금 도는 백엔드는 바뀌지 않는다.** 플래그는 세션에 붙어 다니지
        않으므로(설계 2-5, D01 실측) 모델은 재spawn 시점의 argv 로만 정해진다.
        그래서 백엔드가 떠 있으면 공지 한 줄을 남긴다 - 안 남기면 사용자는
        이번 턴부터 바뀐 줄 안다.

        Args:
            choice: posture.MODEL_CHOICES 중 하나. 그 밖이면 기본값으로 접는다.

        Returns:
            str: 적용된 선택값.
        """
        resolved = posture_mod.normalize_model_choice(choice)
        changed = resolved != self.model_choice
        self.model_choice = resolved
        # 저장 실패(QGIS 밖, INI 쓰기 실패)에도 표시는 바꾼다. 테마와 같다.
        posture_mod.write_model_choice(resolved)
        self._refresh_model_pick()
        if changed and self.backend is not None:
            self.chat_view.add_notice(
                NOTICE_MODEL_NEXT_SPAWN
                % posture_mod.MODEL_CHOICE_LABELS[resolved])
        return resolved

    def _refresh_model_pick(self):
        """드롭다운의 고른 값을 지금 선택값에 맞춘다.

        Returns:
            str: 드롭다운이 가리키는 선택값.
        """
        box = self.model_pick
        index = box.findData(self.model_choice)
        if index >= 0 and box.currentIndex() != index:
            box.setCurrentIndex(index)
        return str(box.currentData() or "")

    def _build_input(self, parent):
        """[6] 입력 영역. 멀티라인 입력, 전송, 취소, cwd 표시(설계 7-1)."""
        area = QWidget(parent)
        layout = QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # cwd 표시는 입력 위다. 0.2.2 전에는 전송/취소와 같은 줄이어서 남는
        # 폭이 200 px 쯤이었고 경로가 낱말 중간에서 잘렸다. 자기 줄에 두면
        # 독 폭을 다 쓴다.
        self.cwd_label = PathButton(CWD_PREFIX + CWD_UNSET, area)
        self.cwd_label.setObjectName("UpwiseChatCwd")
        self.cwd_label.setFlat(True)
        self.cwd_label.setCursor(Qt.PointingHandCursor)
        self.cwd_label.setMinimumWidth(CWD_LABEL_MIN_W)
        self.cwd_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.cwd_label.setToolTip("클릭하면 작업 폴더를 바꿉니다(백엔드를 다시 띄웁니다)")
        self.cwd_label.clicked.connect(self._on_cwd_clicked)
        layout.addWidget(self.cwd_label)

        # 0.4.0: 위/아래 화살표 히스토리를 가진 입력창이다. 모양과 qss 이름은
        # 그대로이고(새 선택자를 만들지 않는다) 바뀐 것은 키 처리뿐이다.
        self.input_edit = HistoryTextEdit(area, history=self.input_history)
        self.input_edit.setObjectName("UpwiseChatInput")
        self.input_edit.setPlaceholderText(PLACEHOLDER_NO_BACKEND)
        # 줄 높이에서 상한을 잡는다. 글꼴 크기를 px 로 고정하지 않기 위해
        # 폰트 메트릭에서 계산한다(설계 7-3).
        line_h = self.input_edit.fontMetrics().lineSpacing()
        self.input_edit.setMaximumHeight(line_h * INPUT_MAX_LINES + 12)
        self.input_edit.textChanged.connect(self._update_controls)
        # 0.6.1 두 훅. 위젯이 독을 모르게 두려고 생성 뒤에 꽂는다
        # (HistoryTextEdit 클래스 docstring).
        self.input_edit.on_recall_queued = self.recall_queued
        self.input_edit.on_escape = self.stop_turn
        layout.addWidget(self.input_edit)

        row = QWidget(area)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        # 진행 중 표시(0.2.2). 워치독 행과 다른 축이다 - 워치독은 **너무
        # 오래** 걸릴 때 뜨고 이것은 **도는 동안** 뜬다. 새 타이머를 만들지
        # 않고 이미 도는 1초 워치독 틱에서 점만 돌린다.
        self.busy_label = QLabel("", row)
        self.busy_label.setObjectName("UpwiseChatBusy")
        theme_mod.set_role(self.busy_label, theme_mod.ROLE_BUSY)
        self.busy_label.setVisible(False)
        # 0.6.1: 턴 중 입력과 중단 단축키 안내는 이 툴팁 하나로 한다. 상시
        # 위젯을 더하지 않는 이유는 BUSY_TIP 주석에 있다(폭 비용).
        self.busy_label.setToolTip(BUSY_TIP)
        # 0.6.1: 대기 꼬리가 독 최소 폭을 밀지 못하게 박는다
        # (BUSY_LABEL_MIN_W 주석에 실측값이 있다).
        self.busy_label.setMinimumWidth(BUSY_LABEL_MIN_W)
        row_layout.addWidget(self.busy_label)
        row_layout.addStretch(1)

        self.send_button = QPushButton("전송", row)
        # 주 버튼. qss 가 이 이름으로 브랜드 오렌지를 건다(설계 7-3).
        self.send_button.setObjectName("UpwiseChatSendButton")
        self.send_button.setToolTip("Ctrl+Enter")
        # clicked 는 bool(checked) 를 넘긴다. send_message(text=...) 에 그대로
        # 연결하면 그 bool 이 보낼 텍스트 자리에 들어간다. 그래서 래퍼를 둔다.
        self.send_button.clicked.connect(self._on_send_clicked)
        row_layout.addWidget(self.send_button)

        # [취소] 의 뜻이 0.6.1 에 바뀌었다(사용자 지시 2026-10-25: Claude Code
        # 와 동일하게). **글자는 그대로 "취소"** 다 - 두 자를 넘기면 이 상시
        # 줄의 최소 폭이 그만큼 오르고, 그 줄은 독 최소 폭을 정하는 줄이다.
        # 바뀐 뜻은 툴팁이 적는다(폭 비용 0 인 자리).
        #
        # 전 동작(백엔드 재시작)은 지워지지 않았다 - `cancel()` 이 그대로
        # 남아 있고 침묵 워치독 바의 [취소] 와 끊기 폴백이 그것을 부른다.
        self.cancel_button = QPushButton("취소", row)
        self.cancel_button.setToolTip(
            "지금 턴을 중단합니다 (Esc).\n"
            "대기 메시지는 남아 바로 이어집니다."
        )
        self.cancel_button.clicked.connect(self._on_stop_clicked)
        row_layout.addWidget(self.cancel_button)
        layout.addWidget(row)

        # 대기 안내 바(0.6.1). busy 이고 대기가 있을 때만 보인다.
        #
        # **자기 줄에 둔다.** 전송·취소와 같은 줄에 버튼을 더하면 그 줄의 최소
        # 폭이 글자 폭만큼 오르고(QPushButton 은 sizeHint 아래로 줄지 않는다),
        # 임계 480 의 여유를 먹는다. 바는 build_bar 와 같은 두 줄 꼴이라 본문이
        # 줄바꿈으로 접히고 버튼 하나만 폭을 정한다.
        self.queue_row = QFrame(area)
        self.queue_row.setObjectName("UpwiseChatQueueBar")
        self.queue_row.setFrameShape(QFrame.NoFrame)
        # 0.6.1: 이 버튼이 **회수**다(전에는 "대기 취소"). 속성 이름은
        # `queue_cancel_button` 을 그대로 둔다 - 하네스가 읽는 창구 이름이고,
        # 취소 요청은 회수의 내부 단계로 그대로 쓰인다.
        self.queue_label, (self.queue_cancel_button,) = \
            build_bar(self.queue_row, [(QUEUE_RECALL_TEXT, "")])
        self.queue_cancel_button.setToolTip(QUEUE_RECALL_TIP)
        # clicked 는 bool 을 넘긴다. 슬롯을 직접 이으면 그 bool 이 첫 인자
        # 자리에 들어간다(이 파일의 _on_send_clicked 와 같은 함정).
        self.queue_cancel_button.clicked.connect(self._on_queue_cancel_clicked)
        self.queue_row.setVisible(False)
        layout.addWidget(self.queue_row)

        # cwd 인라인 편집 행(S5-3). 기본은 숨어 있고 cwd 표시를 누르면 열린다.
        # 대화상자를 띄우지 않으므로 떠 있는 동안에도 QGIS 조작이 된다.
        self.cwd_edit_row = QWidget(area)
        cwd_layout = QHBoxLayout(self.cwd_edit_row)
        cwd_layout.setContentsMargins(0, 0, 0, 0)
        self.cwd_edit = QLineEdit(self.cwd_edit_row)
        self.cwd_edit.setObjectName("UpwiseChatCwdEdit")
        self.cwd_edit.setPlaceholderText("폴더 경로를 붙여 넣고 적용을 누릅니다")
        self.cwd_edit.returnPressed.connect(self._on_cwd_apply)
        cwd_layout.addWidget(self.cwd_edit, 1)
        self.cwd_apply_button = QPushButton("적용", self.cwd_edit_row)
        self.cwd_apply_button.clicked.connect(self._on_cwd_apply)
        cwd_layout.addWidget(self.cwd_apply_button)
        self.cwd_cancel_button = QPushButton("취소", self.cwd_edit_row)
        self.cwd_cancel_button.clicked.connect(self._on_cwd_edit_cancel)
        cwd_layout.addWidget(self.cwd_cancel_button)
        self.cwd_edit_row.setVisible(False)
        layout.addWidget(self.cwd_edit_row)

        # "by UPWISE" 푸터(U5). 입력 영역의 마지막 줄, 오른쪽 끝이다.
        #
        # 헤더 상표와 같은 주소를 열므로 노출이 중복된다. 그 중복은 사용자가
        # 승인한 것이고(docs/6 U5), 두 자리의 역할이 다르다 - 헤더 타일은
        # 제품 정체, 푸터는 "이 창을 누가 만들었나" 다. 라벨이 아니라 평평한
        # 버튼인 이유는 cwd 줄과 같다 - 누를 수 있는 자리라는 것을 커서와
        # 호버 밑줄로 말한다(모달을 못 쓰므로 안내는 제자리에).
        footer_row = QWidget(area)
        footer_layout = QHBoxLayout(footer_row)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(0)
        footer_layout.addStretch(1)
        self.footer_link = QPushButton(FOOTER_TEXT, footer_row)
        self.footer_link.setObjectName("UpwiseChatFooter")
        self.footer_link.setFlat(True)
        self.footer_link.setCursor(Qt.PointingHandCursor)
        self.footer_link.setToolTip(FOOTER_TIP)
        self.footer_link.clicked.connect(self._on_footer_clicked)
        footer_layout.addWidget(self.footer_link)
        layout.addWidget(footer_row)

        # Ctrl+Enter 전송. 입력 위젯 안에서만 듣는다.
        self._send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.input_edit)
        self._send_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._send_shortcut.activated.connect(self.send_message)
        self._send_shortcut_enter = QShortcut(QKeySequence("Ctrl+Enter"), self.input_edit)
        self._send_shortcut_enter.setContext(Qt.WidgetWithChildrenShortcut)
        self._send_shortcut_enter.activated.connect(self.send_message)

        # Ctrl+Shift+Enter = "지금 보내기"(sendNow, 0.6.1).
        #
        # 1차 배선(7735db1)까지 이 조합은 "중단 후 전송" 이었다 - plain interrupt
        # 를 보내고 영수증을 기다린 뒤 글을 보내는 우리 자작 2단계였다. 이 회차는
        # 그 자리를 CLI 의 sendNow 요청으로 바꾼다(Claude Code 의 Ctrl+Enter 와
        # 같은 구조). 자작 2단계는 **sendNow 능력이 없을 때의 폴백**으로만
        # 남는다(`send_now` docstring).
        #
        # 버튼이 아니라 단축키인 이유는 폭이다 - 단축키는 **폭 비용이 0** 이고,
        # 상시 줄에 글자 버튼을 더하면 독 최소 폭이 그만큼 오른다. 아이콘
        # 버튼도 안전하지 않다(isNull 아이콘이 글자 폭으로 폴백해 19 -> 178 px
        # 가 된 선례가 있다).
        self._interrupt_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+Return"), self.input_edit)
        self._interrupt_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._interrupt_shortcut.activated.connect(self._on_interrupt_shortcut)
        self._interrupt_shortcut_enter = QShortcut(
            QKeySequence("Ctrl+Shift+Enter"), self.input_edit)
        self._interrupt_shortcut_enter.setContext(Qt.WidgetWithChildrenShortcut)
        self._interrupt_shortcut_enter.activated.connect(
            self._on_interrupt_shortcut)
        return area

    def _build_status(self, parent):
        """[7] 상태 바와 침묵 워치독 행(설계 7-1, 4-5)."""
        area = QWidget(parent)
        layout = QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.status_label = QLabel("", area)
        self.status_label.setObjectName("UpwiseChatStatus")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        # 침묵 워치독 행. 0.2.2: 주의 바와 같은 면/여백을 쓴다 - 같은 성격의
        # 안내인데 모양이 다르면 두 종류로 읽힌다.
        self.watchdog_row = QFrame(area)
        self.watchdog_row.setObjectName("UpwiseChatWatchdogBar")
        self.watchdog_row.setFrameShape(QFrame.NoFrame)
        self.watchdog_label, (self.wait_button, self.watchdog_cancel_button) = \
            build_bar(self.watchdog_row, [("계속 기다리기", ""), ("취소", "")])
        self.wait_button.clicked.connect(self._on_keep_waiting)
        self.watchdog_cancel_button.clicked.connect(self.cancel)
        self.watchdog_row.setVisible(False)
        layout.addWidget(self.watchdog_row)
        return area

    # ------------------------------------------------------------------
    # 백엔드 배선
    # ------------------------------------------------------------------

    def attach_backend(self, backend):
        """백엔드의 시그널 4개를 독에 연결한다.

        Args:
            backend: backend.process.BackendProcess.
        """
        self.backend = backend
        # 레다크션 적용 지점 1, 3(설계 docs/2 5-4). 로그북은 spawn 마다 새로
        # 열리므로 백엔드에 붙여 둔다 - start() 가 그것을 로그북에 넘긴다.
        # attach 가 start 보다 먼저 불린다(_ensure_backend 순서).
        backend.redactor = self.redactor
        backend.events_drained.connect(self._on_events)
        backend.stderr_line.connect(self._on_stderr)
        backend.backend_died.connect(self._on_died)
        backend.gate_result.connect(self._on_gate)
        # 제어 응답 콜백(0.6.1). 시그널을 새로 만들지 않는 이유는 설계 2-6 과
        # 같다(이벤트당 시그널 금지). `getattr` 로 받지 않고 바로 꽂는 이유는
        # 이 속성이 제품 BackendProcess 의 계약이기 때문이다 - 없으면 배선이
        # 끊긴 것이고 그것은 조용히 넘길 사실이 아니다. 단 하네스의 가짜
        # 백엔드가 이 속성을 안 가질 수 있으므로 설정 자체는 막지 않는다.
        try:
            backend.on_control_response = self._on_control_response
        except AttributeError:
            # 속성을 못 받는 객체(슬롯 전용 가짜)다. 끼어들기만 못 쓴다.
            self._on_machine_note("control_callback_unwired", "")
        self.machine.note_starting()
        self._update_controls()
        self._update_status()

    def detach_backend(self):
        """시그널을 끊는다. 독을 버리거나 백엔드를 바꿀 때 쓴다."""
        backend = self.backend
        if backend is None:
            return
        for signal, slot in (
            (backend.events_drained, self._on_events),
            (backend.stderr_line, self._on_stderr),
            (backend.backend_died, self._on_died),
            (backend.gate_result, self._on_gate),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                # 이미 끊긴 연결과 삭제된 수신자는 정리 경로의 정상 상황이다.
                pass

    def shutdown(self):
        """독을 버릴 때 호출한다. 백엔드를 트리 종료하고 타이머를 멈춘다.

        unload() 에서 백엔드까지 끝내는 것이 설계 7-1 의 요구다. 부모만 죽이면
        claude 가 띄운 MCP 브리지가 고아로 남는다(F11).
        """
        self._watchdog_timer.stop()
        # U6: 프로브 틱도 멈춘다. 독을 버린 뒤 틱이 돌면 이미 내려간 서버의
        # 기동자를 부른다. 도는 스레드 자체는 EmbeddedServer.stop 이 기다린다.
        self._probe_timer.stop()
        backend = self.backend
        self.detach_backend()
        self.backend = None
        if backend is not None:
            try:
                backend.stop("dock_shutdown")
            except Exception:  # noqa: BLE001 - 정리 경로는 끝까지 진행해야 한다
                pass

    # ------------------------------------------------------------------
    # 사용자 동작
    # ------------------------------------------------------------------

    def _on_brand_clicked(self):
        """헤더 브랜드를 눌렀다. 기본 브라우저로 upwise.co.kr 을 연다(설계 7-1).

        QDesktopServices 를 쓰는 이유는 QGIS 안에 브라우저 위젯을 띄우지 않고
        모달도 만들지 않는 유일한 외부 링크 경로이기 때문이다(설계 3-5).

        Returns:
            bool: 운영체제가 처리를 받아들였는가.
        """
        return bool(QDesktopServices.openUrl(QUrl(theme_mod.BRAND_URL)))

    def _on_footer_clicked(self):
        """"by UPWISE" 푸터를 눌렀다 (U5). 헤더 상표와 같은 경로를 쓴다.

        같은 일을 두 번 적지 않는다 - 외부 링크를 여는 유일한 허용 경로가
        `_on_brand_clicked` 에 적혀 있고(QDesktopServices, 모달 없음), 주소도
        거기서 쓰는 theme.BRAND_URL 하나다.

        Returns:
            bool: 운영체제가 처리를 받아들였는가.
        """
        return self._on_brand_clicked()

    def _on_export_clicked(self):
        """내보내기 버튼. clicked 의 bool 인자를 삼킨다(S4 실측 함정)."""
        self.export_transcript()

    def _on_export_open(self, path):
        """안내 바의 [폴더 열기]. 저장한 파일이 있는 폴더를 운영체제에 맡긴다.

        파일 자체가 아니라 폴더를 연다 - 같은 세션에서 여러 장을 내보내면
        사용자가 고를 것이 생기고, 마크다운 연결 프로그램이 없는 PC 에서
        파일을 열면 아무 일도 일어나지 않는다.

        Args:
            path: 저장한 파일 경로.

        Returns:
            bool: 운영체제가 처리를 받아들였는가.
        """
        folder = os.path.dirname(str(path))
        if not folder:
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))

    def export_workspace(self):
        """내보내기가 쓰는 작업 폴더 경로.

        수집 산출물과 같은 뿌리다(skillbundle.profile_env_paths 의 workspace).
        경로 해석에 실패해도 내보내기가 멈추지 않도록 홈 폴더로 떨어진다
        (logbook.qgis_profile_root 의 계약).

        Returns:
            str: workspace 폴더 경로.
        """
        if self.export_workspace_override:
            return str(self.export_workspace_override)
        root = logbook_mod.qgis_profile_root()
        return skillbundle_mod.profile_env_paths(root).get("workspace", "")

    def export_transcript(self):
        """전사를 마크다운 파일로 쓴다(0.2.3).

        모달도 파일 대화상자도 쓰지 않는다(설계 3-5). 경로는 고정이고
        (`<프로필>/upwise_chat/workspace/exports/transcript_<세션8자>_<시각>.md`)
        결과는 비모달 안내 바가 알린다.

        **쓰기 직전에 본문 전체를 레다크터에 통과시킨다**(설계 docs/2 5-4).
        행 글은 이미 렌더 시점에 치환됐지만, 레다크터가 붙기 전에 그려진 행은
        치환되지 않은 채 장부에 남아 있다(chat_view.set_redactor 비소급 규약).
        내보내기는 그 행까지 디스크로 복제하므로 이 한 번이 마지막 관문이다.
        치환이 실패하면 **쓰지 않는다** - 조용히 원문을 복제하지 않는다.

        Returns:
            str: 쓴 파일 경로. 실패하면 빈 문자열.
        """
        rows = self.chat_view.export_rows()
        session_id = getattr(self.backend, "session_id", None)
        path = transcript_mod.export_path(self.export_workspace(), session_id)
        body = transcript_mod.build_markdown(
            rows, self._export_meta(path, session_id, len(rows)))
        body = self._redacted_export(body)
        if body is None:
            self.export_bar.show_failed(EXPORT_REDACT_FAIL)
            return ""
        try:
            transcript_mod.write_markdown(path, body)
        except OSError as exc:
            # 쓰기 실패를 삼키면 사용자가 없는 파일을 찾는다.
            self.export_bar.show_failed("%r" % (exc,))
            return ""
        self.export_bar.show_saved(path)
        if self.backend is not None and self.backend.logbook is not None:
            # 감사 경로. 경로와 행 수만 남긴다 - 본문은 남기지 않는다.
            self.backend.logbook.diag(
                "transcript_export", "path=%s rows=%d chars=%d"
                % (path, len(rows), len(body)))
        return path

    def _on_clear_clicked(self):
        """[대화 지우기]. 첫 누름은 확인을 세우고 두 번째 누름이 비운다 (U11).

        **화면만** 비운다. 백엔드도 상태머신도 건드리지 않으므로 다음 메시지는
        같은 세션에서 이어진다(ChatView.clear_transcript 의 계약). 모달 확인을
        쓸 수 없어 버튼 자신이 확인 단계를 맡는다(CLEAR_BUTTON_TEXT 주석).

        Returns:
            bool: 실제로 비웠는가. 첫 누름(확인 세움)은 False 다.
        """
        if not self._clear_armed:
            return self._arm_clear()
        self._disarm_clear()
        n = self.chat_view.clear_transcript()
        # 빈 화면만 남기면 "세션도 끊겼나" 로 읽힌다. 무엇이 그대로인지 적는다.
        self.chat_view.add_notice(NOTICE_CLEARED)
        self._on_machine_note("transcript_cleared", "rows=%d" % n)
        self._update_controls()
        return True

    def _arm_clear(self):
        """지우기 확인을 세운다 (U11). 버튼 글자가 그대로 확인 문구다.

        Returns:
            bool: 항상 False - 이 누름은 아직 비우지 않았다.
        """
        self._clear_armed = True
        self._clear_timer.start()
        # U16 과 확인이 동시에 서 있지 않게 한다(_arm_new 와 짝).
        self._disarm_new()
        self._refresh_clear_button()
        return False

    def _disarm_clear(self):
        """지우기 확인을 되돌린다 (U11). 타이머 만료와 실행 직후에 부른다.

        Returns:
            bool: 항상 False - 확인이 서 있지 않다.
        """
        self._clear_armed = False
        self._clear_timer.stop()
        self._refresh_clear_button()
        return False

    def _refresh_clear_button(self):
        """지우기 버튼의 활성·글자·툴팁을 지금 상태에 맞춘다 (U11).

        턴이 도는 중에는 막는다. 비우기는 걷어낸 블록 키를 재생성 금지 목록에
        넣으므로(ChatView.clear_transcript) 스트리밍 중에 비우면 **그 턴의 남은
        출력이 화면에 다시 못 나타난다**. 사용자가 답을 잃는 경로라 턴 경계로
        미룬다. 이유는 툴팁이 말한다.

        Returns:
            bool: 지금 누를 수 있는가.
        """
        has_rows = self.chat_view.row_count() > 0
        backend = self.backend
        busy = bool(backend is not None and backend.is_busy())
        can_clear = has_rows and not busy
        if self._clear_armed and not can_clear:
            # 확인을 세운 뒤 조건이 깨졌다(턴 시작, 또는 이미 비었다).
            # 선 확인을 다음 기회로 끌고 가지 않는다.
            self._clear_armed = False
            self._clear_timer.stop()
        self.clear_button.setEnabled(can_clear)
        self.clear_button.setText(
            CLEAR_CONFIRM_TEXT if self._clear_armed else CLEAR_BUTTON_TEXT)
        # 0.4.2: 아이콘 버튼에서는 글자가 안 보이므로 확인 상태를 **체크
        # 면**으로 보인다(qss `:checked`). setChecked 는 toggled 만 내고
        # 우리가 이은 것은 clicked 라 되먹임이 없다.
        self.clear_button.setChecked(bool(self._clear_armed))
        if self._clear_armed:
            tip = CLEAR_CONFIRM_TIP
        elif busy:
            tip = CLEAR_BUSY_TIP
        elif not has_rows:
            tip = CLEAR_EMPTY_TIP
        else:
            tip = CLEAR_BUTTON_TIP
        self.clear_button.setToolTip(tip)
        return can_clear

    def _on_new_clicked(self):
        """[새 대화]. 첫 누름은 확인을 세우고 두 번째 누름이 새로 시작한다 (U16).

        U11([대화 지우기])과 갈리는 지점을 한 자리에 모아 둔다.

            화면      둘 다 비운다. U16 은 재생성 차단까지 푼다
                      (ChatView.reset_session_view).
            세션      U11 은 유지, U16 은 `--resume` 없이 새 session_id 로
                      다시 띄운다. 모델이 기억하던 맥락이 사라진다.
            포스처    U11 은 손대지 않고, U16 은 기본값 R 로 되돌린다.
                      상승 영속의 의도적 예외다(docs/5 4-2).
            파일      둘 다 건드리지 않는다. 이미 쓴 jsonl 과 내보낸 파일은
                      그대로 남는다 - 감사 경로다.

        Returns:
            bool: 실제로 새로 시작했는가. 첫 누름(확인 세움)은 False 다.
        """
        if not self._new_armed:
            return self._arm_new()
        self._disarm_new()
        return self.new_session()

    def new_session(self):
        """화면과 상태를 비우고 백엔드를 새 세션으로 띄운다 (U16).

        버튼과 따로 둔 이유는 확인 단계가 UI 의 일이고 리셋 자체는 독의 일이기
        때문이다. 하네스가 확인 두 번 누르기를 거치지 않고 이 경로만 재는
        것도 같은 이유로 가능해야 한다.

        순서가 중요하다. **화면을 먼저 비우고 백엔드를 다시 띄운다** - 반대로
        하면 새 백엔드의 첫 이벤트가 옛 화면에 섞이고, 실패했을 때 사용자는
        비워지지도 않은 화면에서 실패 공지를 읽는다.

        Returns:
            bool: 백엔드를 새 세션으로 띄웠는가. 백엔드가 아직 없으면 화면만
                비우고 False 다(다음 전송이 새 세션으로 뜬다).
        """
        rows = self.chat_view.reset_session_view()
        # 상태머신을 새로 세운다. 옛 턴을 들고 있으면 다음 드레인이 그 턴의
        # 블록을 다시 그리려 하고, 상태 바도 끝난 세션의 턴 번호를 센다.
        self.machine = machine_mod.TurnMachine(on_note=self._on_machine_note)
        # 턴 번호로 묶인 상태를 전부 비운다. 새 세션의 턴 1 이 옛 턴 1 의
        # 판정·닫음 이력을 물려받으면 안 된다.
        self._preset_turns = {}
        self._judged_turns = set()
        self._marker_verdicts = []
        self._marker_dismissed = set()
        self._denial_dismissed = set()
        self._exclusion_dismissed = set()
        # 턴 번호가 1 부터 다시 시작하므로 미로그인 공지 이력도 비운다.
        # 안 비우면 새 세션의 턴 1 이 옛 세션 턴 1 의 "이미 알렸다" 를
        # 물려받아 조용히 넘어간다(0.4.0, 가드 B).
        self._login_notice_turns = set()
        # 0.6.1: 큐·끼어들기 상태와 "중단됨" 공지 이력도 비운다. 턴 번호가
        # 1 부터 다시 시작하므로 이력을 들고 가면 새 세션의 턴 1 이 옛 턴 1 의
        # "이미 적었다" 를 물려받는다(위 미로그인 공지와 같은 근거).
        self._reset_queue_state()
        self._interrupted_notice_turns = set()
        # soft 안내도 다시 판정한다(가드 A). 하드 공지가 "터미널에서 /login
        # 한 뒤 새 대화" 라고 적었으므로, 그 조치를 마치고 돌아온 사용자에게
        # 낡은 경고가 그대로 붙어 있으면 안내가 자기 말을 뒤집는다.
        # 모든 분기에 걸리게 여기(공통 초기화)에 둔다.
        self.refresh_login_notice()
        self._last_user_text = ""
        self._silence_ack_s = 0.0
        self._cancel_elapsed_ms = None
        self._last_batch_n = 0
        # 누적 비용 문구가 "이번 대화" 를 말하므로 대화가 바뀌면 비운다.
        self._usage_events = 0
        self._cost_events = 0
        self.stats_pane.usage_card.reset()
        for bar in (self.denial_bar, self.exclusion_bar, self.marker_bar,
                    self.stale_bar, self.export_bar, self.posture_bar):
            bar.hide_bar()

        spec = posture_mod.posture_spec(posture_mod.POSTURE_R)
        backend = self.backend
        if backend is None:
            # 아직 안 떴다. 다음 spawn 이 R 로 뜨게 값만 맞춘다
            # (elevate_posture 의 같은 분기와 같은 근거 - 공장이 포스처를
            # 인자로 받는다).
            self._posture_name = spec.name
            self.chat_view.add_notice(NOTICE_NEW_SESSION_IDLE)
            self._on_machine_note("new_session", "rows=%d backend=none" % rows)
            self._update_controls()
            self._update_status()
            return False

        ok = backend.new_session(spec.name, spec.tools, spec.disallowed_tools,
                                 expect_allowed=spec.allowed_tools)
        if not ok:
            self.chat_view.add_notice(NOTICE_NEW_SESSION_FAILED)
            self._on_machine_note("new_session_failed", "rows=%d" % rows)
            self._update_controls()
            self._update_status()
            return False
        self._posture_name = spec.name
        self._new_session_count += 1
        # 게이트 차단 플래그도 새 세션 것으로 다시 받는다. 옛 세션에서 막혀
        # 있었다면 그 차단을 들고 가면 새 세션에서 영구히 못 보낸다.
        self._gate_blocked = False
        self._gate_failed_checks = []
        self._gate_warn_checks = []
        self._backend_rc = None
        self.machine.note_starting()
        self.chat_view.add_notice(NOTICE_NEW_SESSION)
        self._on_machine_note(
            "new_session",
            "rows=%d n=%d session=%s posture=%s"
            % (rows, self._new_session_count,
               getattr(backend, "session_id", None), spec.name))
        self.refresh_prerequisites()
        self._update_controls()
        self._update_status()
        return True

    def _arm_new(self):
        """새 대화 확인을 세운다 (U16).

        Returns:
            bool: 항상 False - 이 누름은 아직 시작하지 않았다.
        """
        self._new_armed = True
        self._new_timer.start()
        # 두 확인이 동시에 서 있으면 어느 쪽을 누르는지 헷갈린다. 한쪽을
        # 세우면 다른쪽은 내린다.
        self._disarm_clear()
        self._refresh_new_button()
        return False

    def _disarm_new(self):
        """새 대화 확인을 되돌린다 (U16).

        Returns:
            bool: 항상 False - 확인이 서 있지 않다.
        """
        self._new_armed = False
        self._new_timer.stop()
        self._refresh_new_button()
        return False

    def _refresh_new_button(self):
        """새 대화 버튼의 활성·글자·툴팁을 지금 상태에 맞춘다 (U16).

        턴이 도는 중에는 막는다. 돌고 있는 턴의 백엔드를 새 세션으로 바꾸면
        그 턴의 응답이 어디에도 도착하지 않는다(취소와 달리 맥락도 안 남는다).
        **비어 있어도 누를 수 있다** - 화면이 빈 것과 세션이 새것인 것은 다른
        사실이고, 맥락을 끊는 것이 이 버튼의 일이다(U11 과의 차이).

        Returns:
            bool: 지금 누를 수 있는가.
        """
        backend = self.backend
        busy = bool(backend is not None and backend.is_busy())
        can_start = not busy
        if self._new_armed and not can_start:
            # 확인을 세운 뒤 턴이 시작됐다. 선 확인을 끌고 가지 않는다.
            self._new_armed = False
            self._new_timer.stop()
        self.new_button.setEnabled(can_start)
        self.new_button.setText(
            NEW_CONFIRM_TEXT if self._new_armed else NEW_BUTTON_TEXT)
        # 0.4.2: 확인 상태를 체크 면으로 보인다(_refresh_clear_button 과 짝).
        self.new_button.setChecked(bool(self._new_armed))
        if self._new_armed:
            tip = NEW_CONFIRM_TIP
        elif busy:
            tip = NEW_BUSY_TIP
        else:
            tip = NEW_BUTTON_TIP
        self.new_button.setToolTip(tip)
        return can_start

    def _on_copy_failed(self, reason):
        """복사가 레다크션 관문에서 막혔다(0.2.4).

        내보내기 실패와 같은 바에 적는다 - 사용자가 안내를 찾는 자리가 한
        군데여야 한다(_build_body 의 바 배치 주석). 열 파일이 없으므로 열기
        버튼은 바가 스스로 잠근다.

        Args:
            reason: 전사가 보낸 사유(chat_view.COPY_REDACT_FAIL).

        Returns:
            bool: 바가 보이는가.
        """
        return self.export_bar.show_copy_failed(reason)

    def _redacted_export(self, body):
        """내보낼 본문을 레다크터에 통과시킨다.

        Args:
            body: 조립한 마크다운.

        Returns:
            str: 치환된 본문. 치환이 실패하면 None(호출자가 중단한다).
        """
        redactor = self.redactor
        if redactor is None:
            return body
        try:
            return redactor(body)
        except Exception:  # noqa: BLE001 - 실패를 원문 쓰기로 바꾸지 않는다
            return None

    def _export_meta(self, path, session_id, rows_n):
        """내보낸 파일 머리글에 적을 (이름, 값) 쌍.

        Args:
            path: 쓸 경로.
            session_id: 지금 세션 식별자.
            rows_n: 전사 행 수.

        Returns:
            list[tuple]: 머리글 불릿.
        """
        return [
            ("세션", session_id or "(백엔드 미기동)"),
            ("내보낸 시각", time.strftime("%Y-%m-%d %H:%M:%S")),
            ("작업 폴더", self._cwd or CWD_UNSET),
            ("포스처", posture_mod.POSTURE_LABELS.get(self._posture_name,
                                                      self._posture_name)),
            ("행", rows_n),
            ("파일", path),
        ]

    def _on_send_clicked(self):
        """전송 버튼. clicked 의 bool 인자를 삼키고 입력 위젯 내용을 보낸다."""
        self.send_message()

    def send_message(self, text=None):
        """입력을 보낸다. 턴 중이면 CLI 큐로 보낸다(0.6.1).

        0.6.0 까지는 턴 중 전송을 거부했다(설계 2-4 "큐에 2개를 쌓지
        않는다"). 그 제약을 푸는 근거는 **큐를 우리가 들지 않는다**는 실측
        이다 - 턴 중 stdin 에 쓰면 CLI 가 자기 큐에 쌓고 턴이 끝나면 스스로
        다음 턴으로 실행한다. 그래서 타이머도 대기 리스트도 재전송 루프도
        만들지 않는다. UI 가 하는 일은 "지금 보내고, 대기 중임을 적는" 둘뿐
        이다.

        능력이 없는 백엔드에서는 **현행대로 거부**된다. 거부 판단은 UI 가
        아니라 `process.send(allow_queue=True)` 가 한다 - 능력 플래그를 UI 에
        복사하면 두 곳이 갈라진다.

        Args:
            text: 보낼 문자열. None 이면 입력 위젯에서 가져온다.

        Returns:
            bool: 실제로 보냈는가.
        """
        body = self.input_edit.toPlainText() if text is None else text
        body = (body or "").strip()
        if not body:
            return False
        # 가드 C(0.4.0). 대화형 전용 슬래시는 CLI 로 보내지 않는다. 비대화형
        # 모드에서는 "/login isn't available in this environment" 만 돌아오고
        # (2026-10-15 실기), 그 답은 사용자에게 아무 조치도 알려주지 않는다.
        # 턴 하나를 과금하고 같은 막다른 길을 다시 보여 주느니 여기서 끊고
        # 실제 해법(터미널 /login + 새 대화)을 적는다.
        #
        # 0.4.2(2026-10-17 사용자 실기): 공지를 **상태로 가른다**. 0.4.1 까지
        # 이 자리는 가드 B 와 같은 "Claude Code 미로그인" 을 띄웠고, 그래서
        # 멀쩡히 로그인된 사용자가 `/login` 을 치면 거짓 단정을 봤다. 고르는
        # 일은 detect 가 한다 - 자격 탐지와 문구가 같은 모듈에 있어야 둘이
        # 갈라지지 않는다. **가로채기는 두 가지 모두에서 유지된다.**
        slash = detect_mod.interactive_only_slash(body)
        if slash:
            notice, found, reason = detect_mod.login_slash_notice()
            self.chat_view.add_notice(notice)
            self._on_machine_note(
                "login_slash_intercepted",
                "%s found=%s reason=%s" % (slash, found, reason))
            # 입력창은 비운다. 이 문자열은 어디로도 보낼 수 없으므로 남겨
            # 두면 사용자가 [전송] 을 다시 눌러 같은 공지를 쌓는다.
            if text is None:
                self.input_edit.clear()
            self._update_controls()
            self._update_status()
            return False
        backend = self._ensure_backend()
        if backend is None:
            return False
        # 턴이 도는 중인가. 이 값 하나가 "지금 실행" 과 "큐에 쌓임" 을 가른다.
        queued = bool(backend.is_busy())
        # 호출 모양을 **새 경로에서만** 바꾼다. 턴이 없을 때는 0.6.0 과
        # 똑같이 `send(body)` 한 인자로 부른다 - `send` 를 1인자로 구현한
        # 대역 백엔드(하네스 50·51 의 FakeBackend)가 평시 경로에서 그대로
        # 돌아야 한다. 섞어서 늘 kwargs 로 부르면 그쪽이 TypeError 로 죽는다
        # (실측: 하네스 50 D 군이 그렇게 떨어졌다).
        sent_ok = (backend.send(body, allow_queue=True) if queued
                   else backend.send(body))
        if not sent_ok:
            return False
        self._last_user_text = body
        # 0.4.0 입력 히스토리. **보낸 뒤**에 쌓는다 - 가로채기(가드 C)와
        # 전송 실패는 위에서 이미 빠져나갔으므로 여기 닿은 것만 실제 전송분
        # 이다(InputHistory docstring).
        self.input_history.add(body)
        # 0.6.1 uuid 짝짓기. 제품에서 켜지는 자리가 여기다 - 이 인자가 없으면
        # 합성 user 줄 필터와 uuid 짝짓기가 꺼진 채로 돈다(하네스 재생에서만
        # 켜져 있었다). 능력이 없으면 `last_sent_uuid` 가 빈 문자열이고
        # `note_sent(uuid=None)` 은 0.6.0 과 동작이 같다.
        msg_uuid = getattr(backend, "last_sent_uuid", "") or None
        if queued:
            # **턴을 열지 않는다.** `note_sent` 는 즉시 새 턴을 여는데, 도는
            # 턴이 있는 상태에서 열면 그 턴이 버려지고(current_turn 교체) 남은
            # 출력이 새 턴 말풍선으로 섞인다. 큐에 쌓인 메시지는 CLI 가
            # 실행을 시작할 때 스트림 이벤트로 턴이 열린다(녹화본 재생에서
            # 턴 2개가 전부 result 로 닫힌 것이 그 증거 - 하네스 105 C6).
            # 그래서 여기서는 uuid 등록만 한다.
            self.machine.note_issued_uuid(msg_uuid or "")
        else:
            self.machine.note_sent(body, uuid=msg_uuid)
        # 이 턴이 프리셋에서 났는지 기억한다(설계 6-2 마커 판정의 대상 선별).
        # 버튼이 아니라 **보낸 문장**으로 판정한다 - 사용자가 버튼으로 넣은 뒤
        # 손으로 고쳐 보낼 수 있고(자동 전송은 하나뿐이다), 터미널 습관대로
        # 슬래시 명령을 직접 타이핑할 수도 있다.
        preset = detect_mod.preset_for_text(body)
        turn = self.machine.current_turn
        # 큐 전송에서는 기록하지 않는다. 그때 `current_turn` 은 **도는 중인
        # 앞 턴**이고, 거기에 적으면 남의 턴에 프리셋 판정이 걸린다. 이 메시지
        # 의 턴 번호는 CLI 가 실행을 시작할 때 생기므로 전송 시점에는 없다.
        if preset and turn is not None and not queued:
            self._preset_turns[turn.turn_no] = preset
        # 사용자 말풍선은 전송 즉시 그린다. replay 이벤트는 렌더하지 않는다
        # (설계 4-2 user 행).
        #
        # 0.6.1: 전송 직후는 **흐린 상태**다(Claude Code 는 보낸·대기 메시지를
        # 모델이 그 메시지에 답하기 시작할 때까지 회색으로 보인다). 흐림을
        # 거두는 조건은 그 uuid 의 lifecycle `started` 또는 result 정산이고,
        # 판정은 `_refresh_bubble_dim` 이 한다.
        #
        # 능력 게이트: 수명 축을 믿을 수 없으면 **처음부터 보통 상태**다.
        # 흐림을 거둘 신호가 오지 않는 백엔드에서 흐리게 그리면 말풍선이
        # 영구히 흐리게 남는다.
        dim = bool(msg_uuid) and self._lifecycle_live()
        bubble = self.chat_view.add_user_message(body, dim=dim)
        if msg_uuid:
            # 본문과 말풍선을 uuid 로 묶어 둔다. 회수가 둘을 같이 쓴다.
            self._sent_messages[msg_uuid] = (body, bubble)
            if dim:
                self._dim_uuids.add(msg_uuid)
        if queued:
            # 큐에 쌓였다는 사실을 그 자리에 적는다. 적지 않으면 사용자는
            # 응답이 오지 않는다고 읽는다.
            self.chat_view.add_notice(NOTICE_QUEUED)
            self._on_machine_note("queued_send", "uuid=%s" % (msg_uuid or ""))
        if text is None:
            self.input_edit.clear()
        self._update_controls()
        self._update_status()
        return True

    def cancel(self):
        """취소. 턴을 "취소됨" 으로 마감하고 백엔드를 재시작한다(설계 2-5).

        Returns:
            bool: 재spawn 성공 여부. 백엔드가 없으면 False.
        """
        backend = self.backend
        if backend is None:
            return False
        t0 = time.perf_counter()
        self.machine.note_cancelled()
        self.chat_view.add_notice("요청을 취소했습니다. 백엔드를 재시작합니다.")
        ok = backend.request_cancel()
        if ok:
            self.machine.note_starting()
        else:
            self.machine.note_died(-1, "cancel respawn failed")
            self.chat_view.add_notice("백엔드 재시작에 실패했습니다.")
        self._cancel_elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self._silence_ack_s = 0.0
        self.watchdog_row.setVisible(False)
        # 트리를 죽이고 다시 띄웠으므로 CLI 큐도 함께 사라졌다. 대기 표시를
        # 남겨 두면 없는 큐를 가리킨다(0.6.1).
        self._reset_queue_state()
        self._update_controls()
        self._update_status()
        return ok

    # ------------------------------------------------------------------
    # 큐와 끼어들기 (0.6.1)
    # ------------------------------------------------------------------

    def _reset_queue_state(self):
        """대기·끼어들기 상태를 비운다(0.6.1).

        프로세스가 바뀌거나 세션이 바뀌는 모든 경로에서 부른다 - 취소, 사망,
        새 대화, 포스처 상승이다. 비우지 않으면 없어진 CLI 큐를 가리키는
        "대기 N건" 이 남고, 받을 수 없는 영수증을 기다리는 끼어들기가 남는다.

        상태머신의 `lifecycle` 은 여기서 손대지 않는다 - 새 TurnMachine 을
        세우는 경로(새 대화)는 그쪽이 알아서 비고, 재spawn 경로는 프로세스
        계층이 자기 집합을 비운다(process._spawn).

        Returns:
            bool: 끼어들기가 걸려 있던 상태를 지웠는가.
        """
        had = bool(self._interrupt_text or self._interrupt_request_id
                   or self._send_now_request_id or self._stop_request_id)
        self._interrupt_text = ""
        self._interrupt_request_id = ""
        self._interrupt_acked = False
        self._send_now_request_id = ""
        self._stop_request_id = ""
        # 0.6.1: 흐린 말풍선과 회수 대기를 함께 비운다.
        #
        # 흐림은 **보통 상태로 돌려 놓는다** - 프로세스가 사라졌으므로 흐림을
        # 거둘 신호가 영원히 오지 않고, 흐린 채로 두면 보낸 글이 영구히
        # "아직 시작 안 됨" 으로 보인다. 회수 대기는 버린다 - 그 uuid 의
        # 운명을 말해 줄 CLI 가 없다.
        for msg_uuid in list(self._dim_uuids):
            self._clear_dim(msg_uuid)
        self._dim_uuids = set()
        self._dim_seen_queued = set()
        self._recalled.clear()
        self._sent_messages.clear()
        self.queue_row.setVisible(False)
        self.queue_label.setText("")
        return had

    def _lifecycle_live(self):
        """백엔드가 큐 수명 축을 지금 믿어도 된다고 말하는가(0.6.1).

        창구가 없는 백엔드(구 대역·하네스 가짜)는 **0.6.1 처럼** True 로
        본다 - 없는 창구를 "능력 없음" 으로 읽으면 가짜 백엔드에서 큐 표시가
        통째로 꺼진다(`_queued_count` 와 같은 처분).

        Returns:
            bool
        """
        live = getattr(self.backend, "lifecycle_live", None)
        if callable(live):
            try:
                return bool(live())
            except Exception:  # noqa: BLE001 - 조회 실패로 표시를 끄지 않는다
                return True
        return self.backend is not None

    def _queued_count(self):
        """지금 차례를 기다리는 메시지 수.

        **원천은 상태머신의 lifecycle 집합 하나다.** `result.queued_turn_count`
        를 쓰지 않는다 - 네 result 전부 0 이었고 다음 메시지가 대기 중인
        시점의 result 도 0 이었다(실측). 그 필드로 그리면 영구 0 이다.

        런타임 하향(0.6.1 V47-A07)
            백엔드가 "큐 수명 축을 지금 믿을 수 없다" 고 말하면 0 이다 -
            init 광고에 그 능력이 없는 CLI 판본에서는 lifecycle 이 오지
            않거나 불완전하고, 그 집합으로 숫자를 그리면 근거 없는 수를
            보여 준다. 그 창구가 없는 백엔드(구 대역·하네스 가짜)는
            **0.6.0 처럼** 그대로 센다.

        Returns:
            int
        """
        backend = self.backend
        live = getattr(backend, "lifecycle_live", None)
        if callable(live) and not live():
            return 0
        try:
            return int(self.machine.outstanding_count())
        except AttributeError:
            # 0.6.0 상태머신(창구 없음). 큐 표시만 꺼진다.
            return 0

    def _queued_uuids(self):
        """대기 중인 메시지 uuid 들. 취소 요청이 이 목록을 돈다.

        Returns:
            tuple
        """
        try:
            return tuple(self.machine.queued_uuids())
        except AttributeError:
            return ()

    def _apply_busy_label(self):
        """진행 중 표시의 보임·글자·툴팁을 **한 자리에서** 조립한다(0.6.1).

        왜 한 자리인가
            0.6.0 까지 이 라벨의 글자를 `_update_controls` 와 워치독 틱 두
            곳이 각각 썼다. 거기에 대기 건수를 더하면 한쪽이 다른쪽의 꼬리를
            지운다(틱이 점만 돌리며 꼬리를 날리거나, 갱신이 점을 0 으로
            되돌린다). 그래서 조립을 이 함수로 모으고 두 곳은 이것만 부른다.

        Returns:
            tuple: (busy 인가, 대기 건수)
        """
        backend = self.backend
        busy = bool(backend is not None and backend.is_busy())
        waiting = self._queued_count()
        self.busy_label.setVisible(busy)
        if not busy:
            self._busy_dots = 0
            self.busy_label.setText("")
            return (False, waiting)
        text = BUSY_TEXT % ("." * self._busy_dots)
        if waiting:
            text += BUSY_QUEUE_SUFFIX % waiting
        self.busy_label.setText(text)
        return (True, waiting)

    def _refresh_queue_bar(self):
        """대기 안내 바를 지금 대기 건수에 맞춘다(0.6.1).

        대기가 0 이면 내린다. 상시 위젯이 아니므로 숨은 동안 레이아웃이
        이 줄을 세지 않고(Qt 는 숨은 항목을 건너뛴다) 독 최소 폭에도 안
        들어온다.

        Returns:
            int: 지금 대기 건수.
        """
        waiting = self._queued_count()
        if waiting:
            self.queue_label.setText(QUEUE_BAR_TEXT % waiting)
        else:
            self.queue_label.setText("")
        self.queue_row.setVisible(bool(waiting))
        self.queue_cancel_button.setEnabled(bool(waiting))
        return waiting

    def _on_queue_cancel_clicked(self):
        """대기 바의 [회수] 버튼. clicked 의 bool 인자를 삼킨다."""
        return bool(self.recall_queued())

    def cancel_queued(self, uuids=None):
        """대기 중인 메시지에 취소 요청을 보낸다(0.6.1).

        uuid 마다 한 발이다. 취소는 **메시지 단위** 요청이고(영수증이
        `cancelled` 를 메시지별로 돌려준다) 한 발로 묶는 형태는 측정되지
        않았다 - 측정 안 된 형태를 지어내지 않는다.

        도는 중인 턴은 건드리지 않는다. 그쪽을 멈추는 것은 끊기다.

        0.6.1: 이것은 더 이상 **사용자 조작이 아니다.** 회수
        (`recall_queued`)의 내부 단계다 - 삭제만 되는 조작은 사용자가 쓴
        글을 돌려주지 않으므로 UI 에서 걷었다(QUEUE_RECALL_TEXT 주석).
        공지는 적지 않는다. 그 자리의 공지는 회수가 적는다.

        Args:
            uuids: 취소할 uuid 들. None 이면 지금 대기 중인 전부다.

                **회수는 이 인자를 반드시 준다.** 본문을 모르는 uuid 를
                취소하면 입력창에 되돌릴 것이 없는 채로 그 메시지가
                사라진다 - 사용자가 쓴 글을 지우는 방향이다. 그래서 회수는
                본문을 아는 uuid 만 넘기고, 모르는 것은 큐에 남겨 둔다
                (그 메시지는 다음 턴에 정상 실행된다).

        Returns:
            int: 보낸 요청 수.
        """
        backend = self.backend
        if backend is None:
            return 0
        uuids = self._queued_uuids() if uuids is None else tuple(uuids)
        if not uuids:
            return 0
        # subtype 이름은 백엔드가 쥔다(docs/7 2-10 경계 6). UI 는 리터럴을
        # 들지 않고 등록용으로 읽기만 한다.
        subtype = getattr(backend, "cancel_queued_subtype", "")
        if not subtype:
            # 어댑터가 이 요청 이름을 모른다. 조용히 아무것도 하지 않는다.
            self._on_machine_note("queue_cancel_unsupported", "")
            return 0
        sent = 0
        for msg_uuid in uuids:
            request_id = backend.cancel_queued_message(msg_uuid)
            if not request_id:
                continue
            # 우리 요청으로 등록한다. 등록하지 않으면 영수증이 짝 없는
            # 응답으로 떨어진다(중단 판정의 근거가 이 등록이다).
            self.machine.note_control_sent(request_id, subtype)
            self._queue_cancel_requests += 1
            sent += 1
        if sent:
            self._on_machine_note("queue_cancel_sent", "n=%d" % sent)
        self._update_controls()
        self._update_status()
        return sent

    # ------------------------------------------------------------------
    # 회수 (0.6.1, Claude Code 의 첫 줄 Up)
    # ------------------------------------------------------------------

    def recall_queued(self):
        """대기 메시지를 입력창으로 되가져온다(0.6.1).

        Claude Code 대화형 화면의 "입력창 첫 줄에서 Up" 과 같은 조작이다.
        대기 메시지를 한 줄씩, **이미 쓴 글보다 앞에** 넣는다. 고쳐서 전송키를
        누르면 한 건으로 다시 큐잉되고, 비우면 버려진다.

        세 단계다
            1. 대기 uuid 마다 취소 요청 한 발(`cancel_queued`). 이것이
               "큐에서 꺼낸다" 의 전부다 - CLI 가 큐의 주인이다.
            2. 그 uuid 들의 **본문**을 발급 순서대로 입력창에 넣는다. 이미
               쓰던 글은 그 뒤에 붙는다.
            3. 대기 중이던 **말풍선을 전사에서 걷는다.** 보내지 않은 글이
               보낸 것으로 남지 않게 하기 위함이다.

        경합 (지어내지 않는다)
            취소 요청은 "already dequeued for execution 이면 no-op" 이다
            `[스키마]`(docs/10 3 절). 즉 우리가 회수했다고 믿은 메시지가 이미
            실행에 들어갔을 수 있다. 그 경우는 `_check_recall_race` 가
            lifecycle `started` 또는 result 의 이름 부르기로 **관측한 뒤에만**
            처분한다 - 말풍선을 되돌려 놓고 공지 한 줄을 적으며, 입력창의
            글은 지우지 않는다(사용자가 보고 있는 글이다).

        Returns:
            int: 되가져온 건수. 대기가 없으면 0 이고, 그때 호출자(첫 줄 Up)는
                평소 히스토리 탐색으로 넘어간다.
        """
        uuids = [u for u in self._queued_uuids() if u in self._sent_messages]
        if not uuids:
            # 대기가 없거나 본문을 모르는 uuid 뿐이다. 본문을 모르면 입력창에
            # 넣을 것이 없으므로 회수라고 부를 수 없다 - 아무것도 하지 않고
            # 히스토리에 자리를 넘긴다.
            return 0
        # 발급 순서를 쓴다. lifecycle 집합의 반복 순서는 **이벤트 도착 순서**
        # 이고 그것이 사용자가 쓴 순서와 같다는 보장은 없다.
        ordered = [u for u in self._sent_messages if u in uuids]
        # **본문을 아는 uuid 만** 취소한다(그쪽 docstring 의 Args 참고).
        sent = self.cancel_queued(ordered)
        bodies = []
        for msg_uuid in ordered:
            body, bubble = self._sent_messages.get(msg_uuid, ("", None))
            bodies.append(body)
            # 말풍선을 걷고, 경합이 나면 되돌릴 수 있게 본문을 들고 있는다.
            self.chat_view.remove_user_message(bubble)
            self._clear_dim(msg_uuid)
            self._dim_seen_queued.discard(msg_uuid)
            self._sent_messages.pop(msg_uuid, None)
            self._recalled[msg_uuid] = body
        draft = self.input_edit.toPlainText()
        merged = "\n".join(bodies)
        if draft:
            merged = merged + "\n" + draft
        # 되부르기와 같은 창구로 넣는다 - 그 함수가 `textChanged` 재진입
        # 가드를 들고 있어서 히스토리 탐색이 스스로 접히지 않는다.
        self.input_edit.apply_history_text(merged)
        # 커서는 첫 줄 처음이다. 되가져온 글을 바로 고치는 자리가 거기다.
        cursor = self.input_edit.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.input_edit.setTextCursor(cursor)
        self._recall_requests += 1
        self.chat_view.add_notice(NOTICE_RECALLED % len(ordered))
        self._on_machine_note(
            "queue_recalled",
            "n=%d cancel_requests=%d" % (len(ordered), sent))
        self._update_controls()
        self._update_status()
        return len(ordered)

    def _check_recall_race(self):
        """회수한 메시지가 이미 실행에 들어갔는지 본다(0.6.1).

        회수 요청은 "이미 꺼내진 메시지면 no-op" 이므로 `[스키마]`, 회수가
        늘 성공한다고 전제할 수 없다. 여기서 보는 신호는 둘이고 **둘 다
        관측값**이다 - 그 uuid 가 지금 실행 중(`started`)이거나, 어떤 턴의
        result 가 그 uuid 를 이름으로 불렀다.

        처분은 가장 단순한 쪽이다. 그 메시지는 실행된 것이므로 말풍선을
        되돌려 놓고 공지 한 줄을 적는다. **입력창의 글은 지우지 않는다** -
        사용자가 지금 보고 고치는 중인 글이고, 그것을 우리가 지우면 사용자가
        쓴 것이 사라진다. 그래서 같은 글이 두 번 갈 수 있고, 그 사실을 공지가
        말한다.

        Returns:
            int: 이번 호출에서 되돌린 건수.
        """
        if not self._recalled:
            return 0
        try:
            running = set(self.machine.running_uuids())
        except AttributeError:
            running = set()
        restored = 0
        for msg_uuid, body in list(self._recalled.items()):
            if msg_uuid not in running and not self._result_named(msg_uuid):
                continue
            self._recalled.pop(msg_uuid, None)
            bubble = self.chat_view.add_user_message(body)
            self._sent_messages[msg_uuid] = (body, bubble)
            self.chat_view.add_notice(NOTICE_RECALL_RACE)
            self._on_machine_note("queue_recall_raced", "uuid=%s" % msg_uuid)
            restored += 1
        return restored

    def _result_named(self, msg_uuid):
        """어떤 턴의 result 가 이 uuid 를 이름으로 불렀는가.

        `result.user_message_uuids` 가 입력 메시지와 턴을 1:1 로 짚는다
        `[실측]`(docs/10 6 절). 그것이 "그 메시지가 실행됐다" 의 권위다.

        Args:
            msg_uuid: 볼 메시지 uuid.

        Returns:
            bool
        """
        for turn in self.machine.turns:
            if msg_uuid in (getattr(turn, "user_message_uuids", None) or ()):
                return True
        return False

    # ------------------------------------------------------------------
    # 흐린 말풍선 (0.6.1, Claude Code 의 회색 대기 메시지)
    # ------------------------------------------------------------------

    def _clear_dim(self, msg_uuid):
        """그 uuid 의 말풍선을 보통 상태로 돌린다.

        Args:
            msg_uuid: 볼 메시지 uuid.

        Returns:
            bool: 흐림을 거뒀는가.
        """
        if msg_uuid not in self._dim_uuids:
            return False
        self._dim_uuids.discard(msg_uuid)
        _body, bubble = self._sent_messages.get(msg_uuid, ("", None))
        self.chat_view.set_user_message_dim(bubble, False)
        return True

    def _refresh_bubble_dim(self):
        """흐린 말풍선을 지금 관측된 수명 상태에 맞춘다(0.6.1).

        거두는 조건 셋. 전부 **관측값**이고 시간으로 재지 않는다.

            1. 그 uuid 가 `started` 다 - 모델이 그 메시지에 답하기 시작했다
            2. 어떤 턴의 result 가 그 uuid 를 이름으로 불렀다(정산)
            3. `queued` 로 **봤던** uuid 가 집합에서 사라졌다 - `completed`·
               `cancelled` 또는 접힘 정산으로 닫혔다

        3 에 "봤던" 이 붙는 이유
            `queued` 줄이 아직 도착하지 않은 구간에서도 그 uuid 는 집합에
            없다. 그 상태를 "닫혔다" 로 읽으면 보낸 직후 흐림이 바로
            풀려(= Claude Code 와 다른 모양) 대기 중임을 말하지 못한다.

        모르는 state 로 흐림을 거두지 않는다 - 집합에 있지만 `queued` 도
        `started` 도 아닌 값은 판정하지 않고 그대로 둔다(관측 없이 넓히지
        않는다는 수명 축의 규약과 같다).

        Returns:
            int: 이번 호출에서 거둔 건수.
        """
        if not self._dim_uuids:
            return 0
        try:
            queued = set(self.machine.queued_uuids())
            running = set(self.machine.running_uuids())
            lifecycle = set(getattr(self.machine, "lifecycle", {}) or {})
        except AttributeError:
            # 0.6.0 상태머신(창구 없음). 흐림을 거둘 근거가 없으므로 전부
            # 보통 상태로 돌린다 - 영구히 흐린 쪽보다 안전하다.
            for msg_uuid in list(self._dim_uuids):
                self._clear_dim(msg_uuid)
            return 0
        cleared = 0
        for msg_uuid in list(self._dim_uuids):
            if msg_uuid in queued:
                self._dim_seen_queued.add(msg_uuid)
                continue
            if msg_uuid in running:
                cleared += int(self._clear_dim(msg_uuid))
                continue
            if msg_uuid in lifecycle:
                # 모르는 state 다. 기록만 하고 판정하지 않는다.
                continue
            if self._result_named(msg_uuid) or msg_uuid in self._dim_seen_queued:
                cleared += int(self._clear_dim(msg_uuid))
        if cleared:
            self._on_machine_note("bubble_dim_cleared", "n=%d" % cleared)
        return cleared

    # ------------------------------------------------------------------
    # 끊기와 지금 보내기 (0.6.1)
    # ------------------------------------------------------------------

    def _on_stop_clicked(self):
        """[취소] 버튼. clicked 의 bool 인자를 삼키고 끊기로 넘긴다."""
        return self.stop_turn()

    def stop_turn(self):
        """지금 턴만 중단한다. Esc 와 [취소] 가 같은 이 함수를 쓴다(0.6.1).

        Claude Code 의 Esc 와 같은 뜻이다 - 턴을 끊고 **초안은 보내지
        않으며** 지금까지 한 작업은 유지한다. 대기 메시지는 지우지 않는다:
        스트리밍 중 plain interrupt 뒤 대기 메시지가 살아서 다음 턴으로
        실행된 것이 실측이다(docs/10 2 절 V50-03 대조군).

        요청 꼴은 **인자 없는 plain interrupt** 다. `cancel_queued` 도
        `send_now` 도 넣지 않는다 - 둘 다 다른 뜻의 요청이고, None 인 인자는
        어댑터가 키 자체를 버린다(측정된 형태가 인자 없는 쪽이다).

        폴백
            `interrupt_turn()` 이 request_id 를 못 돌려주면(능력 없음 또는
            라이터 닫힘) **백엔드 재시작 경로**(`cancel()`)로 내려가고 그
            사실을 공지한다. 그 경로는 프로세스를 바꾸므로 CLI 큐가 사라진다 -
            같은 조작이 아니라는 것을 공지가 말한다.

        Returns:
            bool: 끊기를 처리했는가. False 면 Esc 는 Qt 의 평소 동작으로
                넘어간다(QGIS 지도 도구의 Esc 를 삼키지 않는다).
        """
        backend = self.backend
        if backend is None:
            return False
        if not backend.is_busy():
            # 도는 턴이 없다. 끊을 것이 없으므로 가로채지 않는다.
            return False
        request_id = backend.interrupt_turn()
        if not request_id:
            # 제어 요청을 보낼 수 없다. 재시작 경로로 내려간다 - 그 경로
            # 코드는 그대로 남아 있고(`cancel`), 침묵 워치독 바의 [취소] 도
            # 같은 함수를 쓴다.
            self.chat_view.add_notice(NOTICE_STOP_FALLBACK)
            self._on_machine_note("stop_fallback_restart", "")
            self.cancel()
            return True
        self.machine.note_control_sent(
            request_id, getattr(backend, "interrupt_subtype", ""))
        self._stop_request_id = request_id
        self._stop_requests += 1
        self._interrupt_requests += 1
        self.chat_view.add_notice(NOTICE_STOP_SENT)
        self._on_machine_note("stop_sent", "request_id=%s" % request_id)
        self._update_controls()
        self._update_status()
        return True

    def _on_interrupt_shortcut(self):
        """Ctrl+Shift+Enter. 단축키의 인자 없는 신호를 받아 넘긴다."""
        return self.send_now()

    def send_now(self, text=None):
        """대기 메시지를 지금 보내 달라고 요청한다(0.6.1 sendNow).

        Claude Code 의 Ctrl+Enter 와 같은 구조다 - 대기 메시지가 곧바로
        나가고 입력 중인 초안은 그 뒤에 큐잉된다. 백그라운드로 보낼 수 있는
        작업이 돌고 있으면 CLI 가 그 작업을 백그라운드로 넘겨 같은 턴에서
        읽고, 글만 쓰고 있으면 턴을 끊고 다음에 보낸다. **그 분기는 CLI 가
        정한다** - 우리는 `send_now` 로 요청하고 영수증 값으로 안다.

        순서가 왜 "큐잉 먼저, 요청 나중" 인가
            요청에는 지목할 `message_uuid` 가 필요하고, 초안의 uuid 는 보내는
            순간 발급된다. 또 Claude Code 의 뜻이 "대기분이 먼저, 초안은 그
            뒤" 이므로 지목 대상은 **가장 오래 기다린 대기 메시지**다(초안밖에
            없으면 그것이 곧 지목 대상이고, 그 구성이 하네스 107 r1 의
            실측 구성이다 - H 를 큐에 넣고 H 를 지목했다).

        폴백
            `interrupt_send_now_v1` 을 광고하지 않는 CLI 판본에서는 0.6.1 의
            자작 2단계로 내려간다 - plain interrupt 를 보내고 **영수증을 받은
            뒤** 글을 보낸다(`_flush_interrupt_send`). 그 경로는 지우지 않고
            남긴다.

        Args:
            text: 보낼 문자열. None 이면 입력 위젯에서 가져온다.

        Returns:
            bool: 요청을 보냈는가.
        """
        backend = self.backend
        if backend is None:
            return False
        body = self.input_edit.toPlainText() if text is None else text
        body = (body or "").strip()
        if not backend.is_busy():
            # 도는 턴이 없다. 지금 보낼 것이 평소 전송과 같다.
            return bool(body) and self.send_message(text)
        live = getattr(backend, "interrupt_send_now_live", None)
        if not (callable(live) and live()):
            # sendNow 능력이 없다. 0.6.1 자작 2단계 폴백.
            return self._interrupt_then_send(body)
        waiting = list(self._queued_uuids())
        if not body and not waiting:
            # 지목할 것도 보낼 것도 없다. 지어낸 요청을 보내지 않는다.
            self.chat_view.add_notice(NOTICE_SEND_NOW_NOTHING)
            self._on_machine_note("send_now_nothing", "")
            return False
        if body:
            # 초안을 먼저 큐에 넣는다. 말풍선·입력창 비움·공지는 평소 전송
            # 창구가 한다 - 그 처리를 여기 복사하면 두 곳이 갈라진다.
            if not self.send_message(text):
                return False
            if text is not None:
                # 인자로 받은 전송은 스스로 입력창을 비우지 않는다.
                self.input_edit.clear()
            if not waiting:
                # 대기가 없었으면 지목 대상은 방금 넣은 초안이다.
                waiting = [getattr(backend, "last_sent_uuid", "") or ""]
        target = waiting[0] if waiting else ""
        if not target:
            self._on_machine_note("send_now_no_target", "")
            return False
        request_id = backend.interrupt_turn_send_now(target)
        if not request_id:
            # 라이터가 닫혔거나 능력이 중간에 내려갔다. 큐에 넣은 글은 그대로
            # 다음 턴에 실행되므로 더 하지 않는다.
            self.chat_view.add_notice(NOTICE_INTERRUPT_UNSUPPORTED)
            self._on_machine_note("send_now_unsupported", "")
            return False
        self.machine.note_control_sent(
            request_id, getattr(backend, "interrupt_subtype", ""))
        self._send_now_request_id = request_id
        self._send_now_requests += 1
        self._interrupt_requests += 1
        self._on_machine_note(
            "send_now_sent",
            "request_id=%s target=%s" % (request_id, target))
        self._update_controls()
        self._update_status()
        return True

    def _interrupt_then_send(self, body):
        """0.6.1 자작 2단계 폴백. plain interrupt 뒤 영수증을 기다려 보낸다.

        sendNow 능력이 없는 CLI 판본에서만 탄다. 영수증을 기다리는 이유는
        0.6.1 과 같다 - 먼저 보내면 중단 전에 큐로 들어간다.

        Args:
            body: 영수증 뒤에 보낼 글. 빈 문자열이면 중단만 한다.

        Returns:
            bool: 중단 요청을 보냈는가.
        """
        backend = self.backend
        request_id = backend.interrupt_turn()
        if not request_id:
            self.chat_view.add_notice(NOTICE_INTERRUPT_UNSUPPORTED)
            self._on_machine_note("interrupt_unsupported", "")
            return False
        self.machine.note_control_sent(
            request_id, getattr(backend, "interrupt_subtype", ""))
        self._interrupt_request_id = request_id
        self._interrupt_text = body
        self._interrupt_acked = False
        self._interrupt_requests += 1
        self.chat_view.add_notice(NOTICE_INTERRUPT_SENT)
        self._on_machine_note("interrupt_sent", "request_id=%s" % request_id)
        self._update_controls()
        self._update_status()
        return True

    def _on_control_response(self, request_id, subtype, payload, matched):
        """제어 응답 1건. 우리가 보낸 요청 종류로 분기한다(0.6.1).

        **여기서 사용자 메시지를 보내지 않는다.** 이 콜백은 드레인 중
        (`process._inspect`)에 불리고 그 시점에 상태머신은 아직 그 배치를
        먹지 않았다. 그 자리에서 보내면 턴 경계가 뒤집힌다. 폴백 경로의 실제
        전송은 `_on_events` 끝에서 한다.

        세 요청의 영수증이 같은 콜백으로 온다
            sendNow  `send_now` 키의 값으로 갈린다. `stopped` 면 돌던 턴이
                     멈췄고 그 result 가 뒤따른다 `[실측]` - 중단 공지는
                     `_check_interrupted_turn` 이 그 턴을 보고 적으므로
                     여기서는 적지 않는다. 그 밖의 값(`delivering`·
                     `nothing_waiting`)은 **턴을 멈추지 않았다**는 뜻이고
                     `[스키마]` 다 - 전달 공지 한 줄만 적는다. 키가 아예
                     없으면 그 판본이 플래그를 읽지 않은 것이므로 폴백
                     영수증과 같이 처리한다.
            plain 끊기  기록만 한다. 대기 메시지는 CLI 가 다음 턴으로
                     돌리고(V50-03 실측), 중단 공지는 턴을 보고 적는다.
            폴백 2단계  깃발을 세워 `_flush_interrupt_send` 가 보내게 한다.

        Args:
            request_id: 응답이 반향한 요청 식별자.
            subtype: 응답 subtype(실관측은 success 하나다).
            payload: 영수증 본문 dict.
            matched: 프로세스 계층이 짝지은 요청 subtype. 빈 문자열이면 짝이
                없는 응답이다.

        Returns:
            bool: 우리 끼어들기·지금보내기·끊기의 영수증이었는가.
        """
        payload = payload or {}
        self._on_machine_note(
            "control_response",
            "request_id=%s subtype=%s matched=%s keys=%s"
            % (request_id, subtype, matched, ",".join(sorted(payload))))
        if not request_id:
            return False
        if request_id == self._send_now_request_id:
            self._send_now_request_id = ""
            return self._handle_send_now_receipt(payload)
        if request_id == self._stop_request_id:
            self._stop_request_id = ""
            self._on_machine_note(
                "stop_receipt",
                "still_queued=%d" % len(payload.get("still_queued") or ()))
            return True
        if request_id == self._interrupt_request_id:
            self._interrupt_acked = True
            return True
        return False

    def _handle_send_now_receipt(self, payload):
        """sendNow 영수증 1건을 `send_now` 값으로 분기한다(0.6.1).

        값의 뜻과 근거 등급은 `process.interrupt_turn_send_now` docstring 에
        있다. 여기서 지키는 것은 **값마다 다른 처분을 지어내지 않는 것**이다 -
        `stopped` 만 "멈췄다" 로 읽고 나머지는 전부 "멈추지 않았다" 로 읽는다.

        Args:
            payload: 영수증 본문 dict.

        Returns:
            bool: 처리했는가(언제나 True - 우리 요청의 영수증이다).
        """
        value = payload.get("send_now")
        if value is None:
            # 키가 없다. 그 판본이 플래그를 읽지 않았다는 뜻이므로(docs/10
            # 2 절: 안 보내면 키가 아예 없다) 폴백 영수증과 같이 처리한다.
            # 보낼 보류 글은 없다 - sendNow 경로는 이미 큐에 넣었다.
            self._interrupt_acked = bool(self._interrupt_text)
            self._on_machine_note("send_now_key_absent", "")
            return True
        if value == SEND_NOW_STOPPED:
            # 중단 공지는 그 턴의 result 를 보고 `_check_interrupted_turn` 이
            # 적는다. 여기서 또 적으면 같은 사실이 두 줄이 된다.
            self._on_machine_note("send_now_stopped", "")
            return True
        # `delivering`·`nothing_waiting`, 그리고 모르는 값. 전부 "턴을
        # 멈추지 않았다" 로만 읽는다. 원값을 진단에 남긴다.
        self.chat_view.add_notice(NOTICE_SEND_NOW_DELIVERING)
        self._on_machine_note("send_now_delivering", "value=%s" % value)
        return True

    def _flush_interrupt_send(self):
        """영수증을 받은 끼어들기의 보류 전송을 처리한다(0.6.1).

        `_on_events` 끝에서만 불린다 - 그 시점에 상태머신이 이번 배치를 다
        먹었으므로 중단된 턴이 이미 닫혀 있다.

        보낼 글이 없으면(단축키만 누름) 중단만 하고 끝낸다. 지어낸 요청을
        보내지 않는다(상승 재전송의 같은 규약).

        Returns:
            bool: 보냈는가.
        """
        if not self._interrupt_acked:
            return False
        text = self._interrupt_text
        self._interrupt_acked = False
        self._interrupt_request_id = ""
        self._interrupt_text = ""
        if not text:
            return False
        sent = self.send_message(text)
        if sent:
            # 입력창은 보낸 뒤에 비운다. send_message(text=...) 는 인자를
            # 받았으므로 스스로 비우지 않는다.
            self.input_edit.clear()
            self._update_controls()
        return bool(sent)

    def _check_interrupted_turn(self):
        """중단된 턴을 **오류가 아니라 공지**로 적는다(0.6.1).

        중단된 턴의 result 는 `error_during_execution`·`is_error=true`·
        `result=null`·cost 0 으로 오고, 그 뒤 같은 프로세스가 다음 메시지를
        정상 처리한다(실측). 그래서 백엔드 사망·오류 문면을 쓰지 않는다.
        분류는 상태머신이 이미 했다(`Turn.interrupted`) - 여기서는 그 판정을
        읽어 공지 한 줄을 붙인다.

        턴당 한 번이다. 같은 턴을 다시 보고 또 적지 않는다(미로그인 공지와
        같은 근거).

        Returns:
            bool: 이번 호출에서 공지를 새로 붙였는가.
        """
        added = False
        for turn in self.machine.turns:
            if not getattr(turn, "interrupted", False):
                continue
            if turn.turn_no in self._interrupted_notice_turns:
                continue
            self._interrupted_notice_turns.add(turn.turn_no)
            self.chat_view.add_notice(NOTICE_INTERRUPTED)
            self._on_machine_note("turn_interrupted_notice",
                                  "turn=%d" % turn.turn_no)
            added = True
        return added

    def set_cwd(self, path):
        """cwd 표시를 갱신하고 프리셋 활성 상태를 다시 계산한다(설계 7-1 [6], 6-3).

        폴더 판정이 cwd 기준이므로(설계 6-3 마지막 줄) 표시만 바꾸고 끝내면
        프리셋이 이전 폴더 기준으로 남는다.
        """
        self._cwd = str(path or "")
        # 표시는 폭에 맞춰 앞을 줄이고, 전문은 툴팁에. 긴 경로가 독의 최소
        # 폭을 밀지 않게 한다.
        self.cwd_label.set_path_text(CWD_PREFIX, self._cwd or CWD_UNSET)
        self.cwd_label.setToolTip(
            (self._cwd + "\n클릭하면 작업 폴더를 바꿉니다(백엔드를 다시 띄웁니다)")
            if self._cwd else
            "클릭하면 작업 폴더를 바꿉니다(백엔드를 다시 띄웁니다)")
        if self._prereq is not None:
            self._prereq.set_cwd(self._cwd)
        self.refresh_prerequisites()

    def set_denial_retry_enabled(self, enabled):
        """거부 재시도 버튼을 쓸 수 있게 한다. 상승 배선(S5)이 부른다."""
        self.denial_bar.set_retry_enabled(enabled)

    # ------------------------------------------------------------------
    # 전제조건과 프리셋 (S6)
    # ------------------------------------------------------------------

    def set_prerequisites(self, prereq):
        """탐지 결과 객체를 붙인다(설계 6-4).

        독이 직접 탐지하지 않는다. claude 경로 탐색과 설정 읽기는 플러그인이
        하고 독은 그 결과를 읽어 바와 버튼에 반영한다.

        Args:
            prereq: backend.detect.Prerequisites. None 이면 프리셋이 전부
                비활성인 채로 둔다 - 전제조건을 모르는데 누를 수 있게 두지 않는다.
        """
        self._prereq = prereq
        if prereq is not None and self._cwd:
            prereq.set_cwd(self._cwd)
        self.refresh_prerequisites()

    def set_self_check(self, provider):
        """내장 서버 자체 점검 함수를 꽂는다(0.3.0, 설계 5-4 (b)).

        Args:
            provider: callable() -> dict(state, text, detail). 보통
                `backend.embedded.EmbeddedServer.self_check` 다. None 이면
                [점검] 이 "쓸 수 없다" 로 답한다 - 조용히 아무 것도 안 하는
                버튼을 두지 않는다.
        """
        self._self_check = provider
        return provider is not None

    def set_port_probe(self, starter):
        """소켓 프로브 기동 함수를 꽂는다 (U6, docs/6 U6).

        `set_self_check` 와 같은 이음매다. 독은 서버 객체도 소켓도 들지 않고,
        "한 번 재 달라" 는 요청과 그 결과만 주고받는다. 그래서 하네스가 가짜
        기동자를 넣어 UI 분기만 재는 것이 가능하고, 제품에서는 플러그인이
        `EmbeddedServer.start_probe` 를 넘긴다.

        Args:
            starter: callable(on_result) -> bool. 프로브 1회를 **비동기로**
                띄우고, 끝나면 on_result(dict) 를 부른다. None 이면 연결 표시가
                "확인 중" 에 머문다 - 모르는 것을 "끊김" 으로 적지 않는다.

        Returns:
            bool: 꽂혔는가.
        """
        self._port_probe = starter
        self._probe_inflight = False
        # 꽂은 즉시 한 번 잰다. 5초를 기다려야 첫 상태가 보이면 사용자는
        # 플러그인이 멈춘 것으로 읽는다.
        self._on_probe_tick()
        return starter is not None

    def _on_probe_tick(self):
        """연결 프로브 틱 (U6). **여기서 소켓을 열지 않는다.**

        독은 UI 스레드다. 서버는 그 같은 스레드의 QTimer 로 응답하므로 여기서
        블로킹 connect/recv 를 하면 응답할 타이머가 묶여 교착이다(설계 함정 1,
        backend/embedded 의 프로브 주석). 그래서 이 함수가 하는 일은 기동
        요청과 겹침 방지뿐이고, 실제 소켓 작업은 백그라운드 스레드가 한다.

        Returns:
            bool: 이번 틱에 프로브를 띄웠는가.
        """
        starter = self._port_probe
        if starter is None:
            return False
        if self._probe_inflight:
            # 앞 프로브가 아직 안 돌아왔다. 요청을 쌓지 않는다.
            return False
        self._probe_inflight = True
        try:
            started = bool(starter(self._on_probe_result))
        except Exception as exc:  # noqa: BLE001 - 프로브 실패가 독을 깨지 않는다
            self._probe_inflight = False
            self._on_machine_note("port_probe_failed", repr(exc))
            return False
        if not started:
            # 꺼져 있거나 앞 프로브가 서버 쪽에서 아직 도는 중이다. 둘 다
            # 결과 콜백으로 이미 내려왔거나 다음 틱에 다시 잰다.
            self._probe_inflight = False
        return started

    def _on_probe_result(self, result):
        """프로브 결과 한 건 (U6). 표시만 갈고 아무 것도 재시작하지 않는다.

        경고를 보고 자동으로 서버를 다시 띄우지 않는 이유는, 포트 재점유나
        무응답의 원인이 우리 쪽이 아닐 수 있고(다른 프로그램, 긴 디스패치)
        그 상태에서 재기동을 반복하면 사용자가 멈출 수단을 잃기 때문이다.
        판단은 사람이 하고 여기서는 사실만 적는다.

        Args:
            result: `backend.embedded.probe_once` 의 판정 dict.

        Returns:
            str: 적용한 판정값.
        """
        self._probe_inflight = False
        if not isinstance(result, dict):
            result = {"verdict": "", "port": 0, "why": repr(result)}
        self._last_probe = result
        verdict = self._refresh_conn_label()
        # 진단 로그에는 매번 남긴다. 사용자가 "끊겼다" 고 말할 때 그 시점의
        # 판정과 왕복 시간을 돌아볼 수 있어야 한다. 토큰 값은 애초에 결과
        # dict 에 없다.
        self._on_machine_note(
            "port_probe",
            "verdict=%s port=%s ms=%.1f why=%s"
            % (result.get("verdict"), result.get("port"),
               float(result.get("elapsed_ms") or 0.0),
               str(result.get("why") or "")[:120]))
        return verdict

    def _refresh_conn_label(self):
        """연결 표시(점·글자·툴팁)를 마지막 판정에 맞춘다 (U6).

        포트는 **판정과 무관하게** 아는 한 적는다. 멀티 QGIS 창에서 어느 창의
        서버인지 가르는 단서가 그것뿐이기 때문이다(CONN_TEXT_* 주석).

        Returns:
            str: 적용한 판정값. 아직 재지 않았으면 빈 문자열.
        """
        result = self._last_probe or {}
        verdict = str(result.get("verdict") or "")
        port = result.get("port") or 0
        shown = str(port) if port else CONN_PORT_UNKNOWN
        # (글자, 상태, 툴팁). 상태값은 theme 의 네 값 중 하나다 - 거부 전용
        # 빨강(danger)은 쓰지 않는다(theme.STATE_WARN 주석).
        table = {
            CONN_VERDICT_OK: (CONN_TEXT_OK % shown, theme_mod.STATE_OK,
                              CONN_TIP_OK),
            CONN_VERDICT_NO_ANSWER: (CONN_TEXT_NO_ANSWER % shown,
                                     theme_mod.STATE_WARN, CONN_TIP_NO_ANSWER),
            CONN_VERDICT_FOREIGN: (CONN_TEXT_FOREIGN % shown,
                                   theme_mod.STATE_WARN, CONN_TIP_FOREIGN),
            CONN_VERDICT_DOWN: (CONN_TEXT_DOWN % shown, theme_mod.STATE_FAIL,
                                CONN_TIP_DOWN),
            CONN_VERDICT_OFF: (CONN_TEXT_OFF, theme_mod.STATE_UNKNOWN,
                               CONN_TIP_OFF),
        }
        text, state, tip = table.get(
            verdict,
            (CONN_TEXT_PENDING % shown, theme_mod.STATE_UNKNOWN,
             CONN_TIP_PENDING))
        why = str(result.get("why") or "")
        if why and verdict not in (CONN_VERDICT_OK, ""):
            # 사유는 툴팁에만 둔다. 글자에 넣으면 헤더가 독 폭을 민다.
            tip = tip + "\n사유: " + why
        self.conn_label.setText(text)
        self.conn_label.setToolTip(tip)
        self.conn_dot.setToolTip(tip)
        theme_mod.set_state(self.conn_label, state)
        theme_mod.set_state(self.conn_dot, state)
        return verdict

    def _on_self_check(self):
        """[점검]. 내장 서버에 직접 물어 전사에 한 줄 적는다(0.3.0).

        **모델을 호출하지 않는다.** 0.2.x 는 같은 질문을
        `/upwise-qgis-mcp-toolkit:qgis-connect-check` 를 자동 전송해 물었고
        유료 1턴이었다. 내장 서버는 우리 것이므로 핸들러 직접 호출로 끝난다 -
        턴 0, 토큰 0, 결정적이다(설계 5-4).

        턴 중에도 누를 수 있다. 소켓을 타지 않고 재진입 가드를 존중하므로
        (`EmbeddedServer.self_check`) 교착이 없고, 디스패치 중이면 "작업 중"
        으로 내려온다.

        Returns:
            dict 또는 None: 점검 결과. 제공자가 없으면 None.
        """
        provider = self._self_check
        if provider is None:
            self.chat_view.add_status_notice(
                SELF_CHECK_NOTICE_KEY, NOTICE_CHECK_UNWIRED)
            self._on_machine_note("self_check", "unwired")
            return None
        try:
            result = provider()
        except Exception as exc:  # noqa: BLE001 - 점검 실패가 독을 깨지 않는다
            result = {"state": "ERROR",
                      "text": "점검 호출이 실패했습니다: %r" % (exc,),
                      "detail": {"why": repr(exc)}}
        if not isinstance(result, dict):
            result = {"state": "ERROR", "text": "점검 결과를 읽지 못했습니다.",
                      "detail": {"raw": repr(result)}}
        self._last_self_check = result
        # U11: 같은 질문의 답은 최신 1건만 남긴다. [점검] 은 무과금이라 사용자가
        # 여러 번 누르고, 그때마다 쌓으면 같은 사실의 사본이 전사를 채운다.
        # 감사 경로는 영향이 없다 - 아래 note 는 매번 jsonl 에 남는다.
        self.chat_view.add_status_notice(
            SELF_CHECK_NOTICE_KEY, str(result.get("text") or ""))
        self._on_machine_note("self_check", "%s %s" % (
            result.get("state"), result.get("detail")))
        return result

    def refresh_keys_state(self):
        """키 설정 상태를 다시 읽어 레다크터와 전제조건에 반영한다(0.2.1).

        세 가지를 한 번에 맞춘다. (1) 레다크터의 지울 값 목록, (2) 전제조건의
        키 축, (3) 패널 행의 상태 문구. 플러그인 적재 시 1회와 저장/삭제마다
        불린다.

        **키 값은 레다크터로만 간다.** 진단에 남기는 것은 수뿐이다.

        Returns:
            dict: 레다크터 요약(값 없음). 하네스가 읽는다.
        """
        try:
            self.redactor.set_secrets(keystore_mod.secrets())
        except Exception as exc:  # noqa: BLE001 - 설정 읽기 실패가 독을 막지 않는다
            self._on_machine_note("keys_read_failed", repr(exc))
        panel = getattr(self, "key_panel", None)
        if panel is not None:
            panel.refresh()
        if self._prereq is not None:
            self._prereq.refresh_keys()
        self.refresh_prerequisites()
        summary = self.redactor.summary()
        self._on_machine_note("redactor", str(summary))
        return summary

    def _on_keys_toggled(self, checked):
        """헤더 [키 설정] 토글. 패널을 여닫는다. 모달을 쓰지 않는다.

        U10: 패널이 스크롤 영역 안에 있으므로 **둘 다** 여닫는다. 바깥만 숨기면
        `KeyPanel.stats()["key_panel_visible"]` 이 숨은 패널을 보인다고 말한다
        (isHidden 은 명시적으로 숨긴 것만 True 다). 그 값을 하네스 24 가 읽는다.
        """
        panel = getattr(self, "key_panel", None)
        if panel is None:
            return False
        if checked:
            panel.refresh()
        panel.setVisible(bool(checked))
        scroll = getattr(self, "key_scroll", None)
        if scroll is not None:
            scroll.setVisible(bool(checked))
            if checked:
                # 열린 다음에 높이를 정한다 - 숨은 위젯의 sizeHint 는 내용이
                # 다 올라오기 전 값일 수 있다.
                self._resize_key_panel()
        # 바텀 내비가 가리키는 칸을 화면과 맞춘다. 내비는 배타라 "키" 와
        # "통계" 가 동시에 켜진 상태를 표현할 수 없다 - 그래서 키를 열면
        # 통계를 내린다. 내비를 거치지 않은 헤더 토글도 같은 규칙을 받는다.
        nav = getattr(self, "bottom_nav", None)
        pane = getattr(self, "stats_pane", None)
        if checked and pane is not None and not pane.isHidden():
            pane.setVisible(False)
        if nav is not None:
            if checked:
                nav.set_current(NAV_KEYS)
            elif pane is None or pane.isHidden():
                nav.set_current(NAV_CHAT)
        return bool(checked)

    def _on_keys_changed(self, configured_n):
        """키 저장/삭제 성공. 전제조건과 레다크터를 다시 맞춘다(0.2.1).

        Args:
            configured_n: 키가 설정된 제공자 수. **값은 오지 않는다.**

        Returns:
            int: 설정된 제공자 수.
        """
        self._on_machine_note("keys_changed", "configured=%d" % configured_n)
        self.refresh_keys_state()
        return int(configured_n)

    def refresh_prerequisites(self):
        """전제조건 바와 프리셋 행을 지금 상태로 다시 그린다(설계 7-1 [2], [3]).

        Returns:
            int: 활성인 프리셋 버튼 수.
        """
        prereq = self._prereq
        items = []
        if self._backend_rc is not None:
            items.append(("backend", PREREQ_BACKEND_DEAD % self._backend_rc,
                          theme_mod.LEVEL_UNMET))
        if prereq is None:
            self.prereq_bar.show_items(items)
            self.preset_row.set_states(
                [(p, False, "전제조건 탐지가 아직 붙지 않았습니다")
                 for p in detect_mod.PRESET_ORDER]
            )
            return 0
        items.extend(self._leveled_items(prereq))
        self.prereq_bar.show_items(items)
        self._refresh_coexist_notice(prereq)
        return self.preset_row.set_states(prereq.preset_states())

    def _refresh_coexist_notice(self, prereq):
        """상류 플러그인(T1) 공존 안내 1줄을 켜거나 끈다(0.3.0).

        FOUND 일 때만 보인다. UNKNOWN(판정 불가)에서 띄우면 혼자 쓰는 사용자가
        있지도 않은 충돌을 걱정한다 - 탐지 실패를 "있음" 으로 단정하지 않는
        원칙의 반대 방향이다.
        """
        label = getattr(self, "coexist_notice_label", None)
        if label is None:
            return False
        shown = getattr(prereq, "upstream_plugin_status", None) == detect_mod.FOUND
        label.setText(detect_mod.UPSTREAM_COEXIST_TEXT if shown else "")
        label.setVisible(bool(shown))
        # 건수 줄을 다시 센다. 자동 펼침은 **하지 않는다** - 이것은 정적
        # 상설 안내라서다(기본 접힘, 사용자 지시 2026-10-16).
        self._apply_notice_expanded()
        return bool(shown)

    def refresh_login_notice(self):
        """미로그인 soft 안내 1줄을 켜거나 끈다(0.4.0, 가드 A).

        `detect.login_evidence()` 가 자격의 **흔적**을 못 찾았을 때만 보인다.
        전송은 막지 않는다 - 다른 인증 경로를 쓰는 환경에서 거짓 음성이
        나므로, 추정으로 플러그인을 못 쓰게 만들지 않는다(detect 주석).

        Returns:
            bool: 안내를 띄웠는가.
        """
        label = getattr(self, "login_notice_label", None)
        if label is None:
            return False
        found, reason = detect_mod.login_evidence()
        shown = not found
        # 이번 호출에서 **새로 켜졌는가**. 이미 켜져 있던 안내를 다시 확인한
        # 것은 발화가 아니다 - 그때마다 펼치면 사용자가 접어 둔 묶음이
        # [새 대화] 를 누를 때마다 되살아난다.
        fired = bool(shown) and label.isHidden()
        label.setText(detect_mod.LOGIN_SOFT_NOTICE_TEXT if shown else "")
        label.setVisible(bool(shown))
        # 새로 발화한 실행형 안내는 처음 한 번 펼쳐서 보여준다(사용자 지시
        # 2026-10-16). 정적 상설 안내(터미널·공존)와 다른 처분인 이유는
        # 이것이 **지금 막 판정된 사실**이고 사용자가 할 일(터미널 /login)이
        # 있기 때문이다. 사용자가 이번 세션에 손으로 접었으면 그 결정을
        # 지킨다 - 안 지키면 접기가 동작하지 않는 것과 같다.
        if fired and not self._notice_user_collapsed:
            self.set_notice_expanded(True)
        else:
            self._apply_notice_expanded()
        self._on_machine_note("login_precheck",
                              "found=%s reason=%s" % (found, reason))
        return bool(shown)

    def _check_login_failure(self):
        """닫힌 턴의 본문에서 미로그인 신호를 찾아 공지를 **병기**한다(가드 B).

        CLI 원문 행은 치환하지 않는다. 전사는 무엇이 실제로 왔는지의 기록이고,
        한국어 안내로 덮으면 사용자가 터미널에서 같은 문장을 다시 만났을 때
        두 화면을 잇지 못한다. 그래서 원문은 그대로 두고 공지 한 줄을 뒤에
        붙인다(제외 안내 바가 원문 오류를 지우지 않는 것과 같은 결).

        Returns:
            bool: 이번 호출에서 공지를 새로 붙였는가.
        """
        turn = self.machine.last_closed_turn
        if turn is None or turn.turn_no in self._login_notice_turns:
            return False
        # result 와 assistant 텍스트를 둘 다 본다. 미로그인 응답이 어느
        # 쪽으로 오는지가 판본에 달려 있고(실기는 result 였다), 한쪽만
        # 보면 다른 판본에서 조용히 놓친다.
        body = "\n".join([turn.result_text or "", turn.assistant_text() or ""])
        if not detect_mod.text_shows_not_logged_in(body):
            return False
        self._login_notice_turns.add(turn.turn_no)
        self.chat_view.add_notice(detect_mod.LOGIN_HARD_NOTICE_TEXT)
        self._on_machine_note("login_not_logged_in", "turn=%d" % turn.turn_no)
        return True

    def _leveled_items(self, prereq):
        """미충족 항목에 심각도를 붙인다(0.2.2 표시 전용).

        detect 의 판정을 바꾸지 않는다. `unmet_items()` 가 주는 (코드, 한 줄)
        에 **이미 있는** `summary()` 의 코드별 상태를 붙여 읽을 뿐이다.
        UNKNOWN 은 "확인 중", 그 밖(MISSING 등)은 "미충족" 이다. 코드가
        요약에 없으면 미충족으로 본다 - 모르는 것을 덜 심각하게 적지 않는다.

        Args:
            prereq: backend.detect.Prerequisites (또는 같은 창구를 가진 객체).

        Returns:
            list[tuple]: (코드, 한 줄, 심각도) 목록.
        """
        try:
            summary = prereq.summary() or {}
        except Exception:  # noqa: BLE001 - 표시용 읽기가 바를 비우게 하지 않는다
            summary = {}
        out = []
        for code, text in prereq.unmet_items():
            status = summary.get(code)
            level = (theme_mod.LEVEL_UNKNOWN if status == detect_mod.UNKNOWN
                     else theme_mod.LEVEL_UNMET)
            out.append((code, text, level))
        return out

    def _note_init_detect(self):
        """첫 init 원본으로 툴킷/MCP/스킬 탐지를 채운다(설계 6-4).

        게이트 요약에는 plugins/skills 가 없어서 원본이 필요하다. 원본은
        백엔드가 보관하고 있고(process.last_init_event) 이 함수는 gate_result
        슬롯 안에서 불린다 - init 1건당 시그널을 새로 만들지 않기 위함이다.
        """
        prereq = self._prereq
        backend = self.backend
        if prereq is None or backend is None:
            return False
        init_event = getattr(backend, "last_init_event", None)
        if not isinstance(init_event, dict):
            return False
        prereq.note_init(init_event)
        self._on_machine_note("prereq_detect", str(prereq.summary()))
        self.refresh_prerequisites()
        return True

    def _on_preset_clicked(self, preset):
        """프리셋 버튼(설계 6-1, docs/2 3-3).

        입력 박스에 슬래시 명령을 넣고 포커스를 준다. 자동 전송은
        detect.PRESET_AUTOSEND 에 있는 것만 한다(connect-check 하나). 전송이
        거절되면(턴 중) 넣은 문자열을 그대로 남긴다 - 사용자가 턴이 끝난 뒤
        그대로 보낼 수 있어야 한다.

        0.2.0: 프리셋이 더 높은 포스처를 요구하고 지금 포스처가 낮으면 **먼저
        확인 바를 띄우고** 주입을 미룬다. 전환이 재spawn 이라 사용자 동의
        없이 백엔드를 끊지 않는다. 이미 충분한 포스처면 묻지 않는다 - 사용자가
        W 로 올려 둔 상태에서 또 전환을 요구하지 않기 위함이다.

        Args:
            preset: 프리셋 이름.

        Returns:
            bool: 자동 전송까지 갔는가.
        """
        want = detect_mod.PRESET_POSTURE.get(preset)
        if want and posture_mod.posture_rank(self._posture_name) \
                < posture_mod.posture_rank(want):
            self.posture_bar.ask(preset, want, posture_mod.COLLECT_ELEVATE_TEXT)
            return False
        return self._inject_preset(preset)

    def _inject_preset(self, preset):
        """프리셋 슬래시 문자열을 입력 박스에 넣는다(전환 뒤 공통부).

        Returns:
            bool: 자동 전송까지 갔는가.
        """
        command = detect_mod.slash_command(preset)
        self.input_edit.setPlainText(command)
        self.input_edit.setFocus()
        # 커서를 끝으로 보낸다. 대상 인자를 이어 적는 것이 기본 사용법이다.
        cursor = self.input_edit.textCursor()
        cursor.movePosition(cursor.End)
        self.input_edit.setTextCursor(cursor)
        self._update_controls()
        if preset not in detect_mod.PRESET_AUTOSEND:
            return False
        return bool(self.send_message())

    def _on_posture_confirmed(self, preset):
        """확인 바의 [전환]. 포스처를 올리고 프리셋을 주입한다(0.2.0).

        재전송은 하지 않는다. 수집은 대상과 영역을 인자로 받으므로 사용자가
        적어 보내야 한다(설계 docs/2 3-3 마지막 줄).

        Returns:
            bool: 전환이 됐는가.
        """
        want = detect_mod.PRESET_POSTURE.get(preset)
        if not want:
            return False
        ok = self.elevate_posture(want)
        if ok:
            self._inject_preset(preset)
        return ok

    def _on_posture_cancelled(self):
        """확인 바의 [취소]. 포스처도 입력도 건드리지 않는다."""
        self.chat_view.add_notice(NOTICE_POSTURE_CANCELLED)
        return True

    def elevate_posture(self, posture_name):
        """포스처를 올려 재spawn 한다. 재전송은 하지 않는다(0.2.0).

        elevate_and_resend() 와 기전이 같고 재전송만 없다. 수집 경로가 이쪽을
        쓴다 - 수집은 인자를 받아야 하므로 자동 전송하지 않는다.

        Args:
            posture_name: 올릴 포스처 이름.

        Returns:
            bool: 재spawn 성공 여부.
        """
        backend = self.backend
        if backend is None:
            # 백엔드가 아직 없으면 다음 spawn 이 이 포스처로 뜨게만 해 둔다.
            # 공장이 posture_name 을 인자로 받으므로(S5-2) 값만 바꾸면 된다.
            self._posture_name = str(posture_name)
            return False
        spec = posture_mod.posture_spec(posture_name)
        # 0.3.1: 사전승인 목록도 함께 넘긴다. 게이트 6 이 포스처별
        # 노출/사전승인 정합을 보므로, 안 넘기면 올린 직후 전 포스처의
        # allowlist 로 판정한다(장부 V32-A52).
        ok = backend.elevate(spec.name, spec.tools, spec.disallowed_tools,
                             expect_allowed=spec.allowed_tools)
        if not ok:
            self.chat_view.add_notice(
                NOTICE_POSTURE_SWITCH_FAILED
                % posture_mod.POSTURE_LABELS.get(posture_name, posture_name))
            self._update_controls()
            return False
        self._posture_name = spec.name
        self._elevate_count += 1
        self.machine.note_starting()
        # 재spawn 이므로 CLI 큐가 사라졌다(0.6.1, cancel 과 같은 근거).
        self._reset_queue_state()
        self.chat_view.add_notice(
            NOTICE_POSTURE_SWITCHED
            % posture_mod.POSTURE_LABELS.get(spec.name, spec.name))
        self._update_controls()
        self._update_status()
        return True

    def _judge_preset_turns(self):
        """닫힌 프리셋 턴의 스킬 마커를 판정한다(설계 6-2).

        판정식은 detect.MARKER_RE 하나다(사전 명세). result 로 닫힌 턴만 본다 -
        취소되거나 재spawn 으로 버려진 턴은 응답이 끝까지 오지 않았으므로
        "마커가 없다" 를 호출 실패로 읽으면 틀린다.

        0.1.4(V28-A48): 판정 입력이 turn.first_text_line() 에서
        turn.assistant_text() 로 바뀌었다. 판정 대상이 result 로 닫힌 턴이라는
        **범위는 그대로**이고, 그 턴 안에서 보는 **텍스트 범위만** 첫 줄에서
        응답 전체로 넓혔다. 모델이 스킬 호출 전에 안내 문장을 먼저 말하면
        마커가 중간 줄에 찍혀 거짓 음성이 났다.

        Returns:
            int: 이번 호출에서 새로 판정한 턴 수.
        """
        judged = 0
        for turn in self.machine.turns:
            if turn.turn_no in self._judged_turns:
                continue
            preset = self._preset_turns.get(turn.turn_no)
            if not preset or turn.closed_by != "result":
                continue
            self._judged_turns.add(turn.turn_no)
            judged += 1
            body = turn.assistant_text()
            ok, name, version, line_no = detect_mod.find_marker(body)
            self._marker_verdicts.append((turn.turn_no, preset, ok, name, version))
            # 첫 2회를 포함해 전부 진단 로그에 남긴다(설계 6-2 는 첫 2회를
            # 요구한다. D02 종결 자료가 되도록 회차 번호를 함께 적는다).
            # 0.1.4: 매칭된 마커 원문과 그것이 몇 번째 줄이었는지를 남긴다.
            # 거짓 음성이 "마커가 없었다" 인지 "중간 줄이어서 못 봤다" 인지
            # 로그만으로 가를 수 있어야 한다. 첫 줄도 함께 남겨 둔다 - 안내
            # 문장이 먼저 왔는지가 그 줄에서 바로 읽힌다.
            matched = ("[%s %s]" % (name, version)) if ok else "(none)"
            lines_n = len(body.splitlines())
            self._on_machine_note(
                "preset_marker",
                "n=%d turn=%d preset=%s ok=%s marker=%s matched=%s "
                "line=%d/%d first_line=%r"
                % (len(self._marker_verdicts), turn.turn_no, preset, ok,
                   name or "(none)", matched, line_no, lines_n,
                   (body or "").split("\n", 1)[0][:80]),
            )
            if ok:
                if name and name != preset:
                    # 판정식에는 넣지 않는다. 다른 스킬이 응답한 것은 사실로
                    # 남겨 두고 사용자에게는 호출된 스킬 이름을 보여 준다.
                    self._on_machine_note(
                        "preset_marker_name_mismatch",
                        "preset=%s marker=%s" % (preset, name))
                self.chat_view.add_notice(NOTICE_MARKER_OK % (name or preset))
                self.marker_bar.hide_bar()
            elif turn.turn_no not in self._marker_dismissed:
                self.marker_bar.show_miss(turn.turn_no, preset)
        return judged

    def _on_marker_fallback(self, preset):
        """[자연어로 다시 요청]. 스킬 이름과 출력 규칙을 풀어 보낸다(설계 6-2)."""
        turn_no = self.marker_bar.turn_no()
        if turn_no is not None:
            self._marker_dismissed.add(turn_no)
        prompt = detect_mod.fallback_prompt(preset)
        return bool(self.send_message(prompt))

    def _on_marker_dismissed(self):
        """마커 안내 바를 닫았다. 그 턴은 다시 띄우지 않는다."""
        turn_no = self.marker_bar.turn_no()
        if turn_no is not None:
            self._marker_dismissed.add(turn_no)
        self.marker_bar.hide_bar()

    # ------------------------------------------------------------------
    # cwd 변경 (S5-3)
    # ------------------------------------------------------------------

    def _on_cwd_clicked(self):
        """cwd 표시를 누르면 인라인 편집 행을 연다."""
        self.cwd_edit.setText(self._cwd)
        self.cwd_edit_row.setVisible(True)
        self.cwd_edit.setFocus()

    def _on_cwd_edit_cancel(self):
        """편집 행을 닫는다. 값은 바꾸지 않는다."""
        self.cwd_edit_row.setVisible(False)

    def _on_cwd_apply(self):
        """cwd 를 바꾸고 백엔드를 다시 띄운다(S5-3).

        cwd 는 모델의 파일 접근 범위와 CLAUDE.md 자동 탐색 범위를 동시에 정하므로
        (설계 2-3) 돌아가는 프로세스에 적용할 방법이 없다. 재spawn 이다. 맥락은
        `--resume` 가 가져온다(D01 PASS).

        Returns:
            bool: 실제로 바뀌었는가.
        """
        new_cwd = (self.cwd_edit.text() or "").strip()
        self.cwd_edit_row.setVisible(False)
        if not new_cwd or new_cwd == self._cwd:
            return False
        backend = self.backend
        if backend is None:
            # 아직 백엔드가 없으면 표시만 바꾼다. 첫 spawn 이 이 값을 쓴다.
            self.set_cwd(new_cwd)
            return True
        ok = backend.restart_with_cwd(new_cwd)
        if ok:
            self.set_cwd(new_cwd)
            self.machine.note_starting()
            self.chat_view.add_notice(NOTICE_CWD_CHANGED % new_cwd)
        else:
            self.chat_view.add_notice(NOTICE_CWD_FAILED % new_cwd)
        self._update_controls()
        self._update_status()
        return bool(ok)

    def note_project_changed(self, project_name, new_cwd):
        """QGIS 프로젝트가 바뀌었다(설계 8, S5-3).

        세 가지를 한다. 백엔드를 **죽이지 않는다** - 턴 중일 수 있고, 재시작
        시점은 사용자가 고른다.
            1. 전사에 경고를 남긴다. 모델이 들고 있는 레이어 지식이 무효가 됐다.
            2. 다음 사용자 메시지 앞에 붙일 한 줄을 백엔드에 예약한다.
            3. cwd 가 달라졌으면 stale 바를 띄운다(자동 재시작 없음).

        Args:
            project_name: 바뀐 프로젝트 이름.
            new_cwd: 새 프로젝트 기준 작업 폴더.

        Returns:
            bool: stale 바를 띄웠는가.
        """
        name = str(project_name or "(이름 없음)")
        self.chat_view.add_notice(NOTICE_PROJECT_CHANGED % name)
        backend = self.backend
        if backend is not None:
            backend.queue_notice_prefix(PREFIX_PROJECT_CHANGED % name)
        new_cwd = str(new_cwd or "")
        if not new_cwd or new_cwd == self._cwd:
            return False
        self.stale_bar.show_stale(name, new_cwd)
        return True

    def _on_stale_restart(self, new_cwd):
        """stale 바의 "새 폴더로 재시작". cwd 변경과 같은 경로를 쓴다(S5-3)."""
        if not new_cwd:
            return False
        self.cwd_edit.setText(str(new_cwd))
        return self._on_cwd_apply()

    # ------------------------------------------------------------------
    # 포스처 상승 재전송 (S5-4)
    # ------------------------------------------------------------------

    def elevate_and_resend(self):
        """포스처를 올려 재spawn 하고 같은 요청을 1회 다시 보낸다(S5-4).

        개별 도구 호출을 플러그인이 주입할 수는 없다. 그래서 재시도는 **원래
        사용자 의도를 W 포스처로 1회 재전송**하는 것이다(설계 3-5).

        이 경로가 D23 의 측정 대상이다. 상승이 거부를 뒤집는 것(D05-a)과
        `--resume` 가 맥락을 가져오는 것(D01)은 각각 실측됐고, 둘을 겹친 것이
        여기서 처음 돈다.

        Returns:
            bool: 상승과 재전송이 둘 다 됐는가.
        """
        backend = self.backend
        if backend is None:
            return False
        text = self._last_user_text
        spec = posture_mod.posture_spec(posture_mod.POSTURE_W)
        # 0.3.1: 사전승인 목록도 함께 넘긴다. 게이트 6 이 포스처별
        # 노출/사전승인 정합을 보므로, 안 넘기면 올린 직후 전 포스처의
        # allowlist 로 판정한다(장부 V32-A52).
        ok = backend.elevate(spec.name, spec.tools, spec.disallowed_tools,
                             expect_allowed=spec.allowed_tools)
        if not ok:
            self.chat_view.add_notice(NOTICE_ELEVATE_FAILED)
            self._update_controls()
            return False
        self._posture_name = spec.name
        self._elevate_count += 1
        self.machine.note_starting()
        # 재spawn 이므로 CLI 큐가 사라졌다(0.6.1). 재전송은 아래에서 **새**
        # 전송으로 들어간다 - 대기 집합을 들고 가면 그 전송이 큐 전송으로
        # 오인된다.
        self._reset_queue_state()
        self.chat_view.add_notice(NOTICE_ELEVATED)
        if not text:
            # 보낼 원문이 없으면 상승만 하고 끝낸다. 지어낸 요청을 보내지 않는다.
            self._update_controls()
            self._update_status()
            return False
        sent = self.send_message(posture_mod.ELEVATION_NOTICE + "\n" + text)
        # 재전송문이 아니라 원문을 기억한다. 두 번 올리면 안내문이 겹친다.
        self._last_user_text = text
        self._update_controls()
        self._update_status()
        return bool(sent)

    # ------------------------------------------------------------------
    # 백엔드 시그널 처리
    # ------------------------------------------------------------------

    def _on_events(self, batch):
        """50 ms 드레인 배치 하나를 먹고 한 번 그린다(설계 2-6).

        이벤트 1건당 갱신하지 않는다. 배치 하나에 렌더 1회가 이 구조의 전부다.
        """
        self._last_batch_n = len(batch or ())
        # 사용량 차트는 **배치 원문**을 읽는다. 백엔드는 한도 수치를 보관하지
        # 않고(설계 9 "수치 표시는 비범위") 경고 한 줄만 만든다 - 백엔드를
        # 고치지 않고 UI 가 같은 배치에서 직접 집는다(charts.usage_from_event).
        rate_n, cost_n = self.stats_pane.usage_card.feed_batch(batch or ())
        self._usage_events += rate_n
        self._cost_events += cost_n
        self.machine.feed_batch(batch or ())
        self.chat_view.sync(self.machine)
        # 턴이 닫힌 배치에서만 수집 통계를 다시 훑는다. 열려 있을 때만이고,
        # 드레인(50 ms)마다 디스크를 읽지 않는다.
        if cost_n and not self.stats_pane.isHidden():
            self.refresh_collect_stats()
        # 마커 판정은 전사 동기화 뒤에 한다. 공지 한 줄이 그 턴 글 뒤에 와야
        # 읽는 순서가 맞다(설계 6-2).
        self._judge_preset_turns()
        # 미로그인 공지도 전사 동기화 뒤다(마커 공지와 같은 근거) - CLI 원문
        # 행이 먼저 그려지고 그 뒤에 안내가 와야 읽는 순서가 맞다.
        self._check_login_failure()
        # 중단된 턴 공지(0.6.1). 전사 동기화 뒤다 - 공지 한 줄이 그 턴 글 뒤에
        # 와야 읽는 순서가 맞다(마커·미로그인 공지와 같은 근거).
        self._check_interrupted_turn()
        # 0.6.1 두 조정. 둘 다 **상태머신이 이 배치를 먹은 뒤**라야 한다 -
        # 흐림 해제와 회수 경합의 근거가 그 배치로 갱신된 수명 집합이다.
        self._refresh_bubble_dim()
        self._check_recall_race()
        self._update_denial_bar()
        self._update_chip()
        self._update_controls()
        self._update_status()
        # 끼어들기 보류 전송은 **이 배치를 다 먹은 뒤**다. 콜백 자리에서
        # 보내면 상태머신이 아직 이 배치를 먹지 않은 상태에서 턴이 열린다
        # (_on_control_response docstring).
        self._flush_interrupt_send()

    def _on_stderr(self, raw):
        """stderr 한 줄. 진단에만 쌓고 전사에 섞지 않는다(설계 4-2)."""
        self._stderr_tail.append(raw)
        self._stderr_count += 1
        self._update_status()

    def _on_died(self, rc, tail):
        """백엔드 사망. 전사는 유지하고 공지 카드를 남긴다(설계 8)."""
        self.machine.note_died(rc, tail)
        text = "백엔드가 종료되었습니다 (rc=%s)." % rc
        if tail:
            text += "\nstderr 꼬리:\n" + tail
        self.chat_view.add_notice(text)
        # 자식이 죽었으면 CLI 큐도 함께 사라졌다. 대기 표시와 기다리던
        # 영수증을 지운다(0.6.1) - 안 지우면 없는 큐를 가리키고, 받을 수 없는
        # 영수증 때문에 보류 전송이 영구히 남는다.
        self._reset_queue_state()
        # 전제조건 바의 "기동 실패" 항목(설계 7-1 [2]). 다시 뜨면 지운다.
        self._backend_rc = rc
        self.refresh_prerequisites()
        self._update_controls()
        self._update_status()

    def _on_gate(self, result):
        """기동 자기점검 판정을 배지에 반영하고, 깨지면 입력을 막는다(S5-1).

        설계 3-4 는 "하나라도 어긋나면 입력 박스를 열지 않는다" 를 요구한다.
        S4 는 배지와 툴팁까지만 했고 게이트가 깨져도 입력이 열려 있었다.
        여기가 그 인계 항목을 닫는 자리다. 실제 전송 차단은 두 겹이다 -
        백엔드의 send() 가 거부하고(process.gate_blocked) UI 도 버튼을 끈다.
        """
        self._gate = result
        # init 이 왔다는 신호이기도 하다. 탐지를 먼저 채워서 전제조건 바와
        # 프리셋이 같은 틱에 갱신되게 한다(설계 6-4).
        self._note_init_detect()
        if not isinstance(result, dict):
            return
        # 0.2.0: 소프트 경고는 입력을 막지 않으므로 ok 와 따로 적는다.
        # 하나로 섞으면 "수집 서버가 없다" 가 "권한 점검 실패" 로 표시된다.
        warns = posture_mod.warn_checks(result)
        self._gate_warn_checks = list(warns)
        if result.get("ok"):
            self._gate_blocked = False
            self._gate_failed_checks = []
            # 배지는 3값이다(설계 docs/2 3-3). 포스처 이름 대신 사용자 말로 적는다.
            #
            # 0.4.2: 권한 모드를 배지에서 툴팁으로 내렸다(BADGE_OK_FMT 주석).
            # 배지에 남는 것은 포스처와 도구 수 - 사용자가 "지금 무엇을 할 수
            # 있나" 를 가르는 두 값이다.
            mode = result.get("permission_mode") or "-"
            posture_label = posture_mod.POSTURE_LABELS.get(
                self._posture_name, self._posture_name)
            n_tools = len(result.get("tools") or ())
            self.badge_label.setText(BADGE_OK_FMT % (posture_label, n_tools))
            tip = BADGE_OK_TIP_FMT % (mode, posture_label, n_tools)
            if warns:
                tip += "\n경고(입력은 막지 않습니다): " + ", ".join(
                    str(w) for w in warns)
            self.badge_label.setToolTip(tip)
            theme_mod.set_state(self.badge_label, theme_mod.STATE_OK)
        else:
            failed = [
                i.get("check")
                for i in (result.get("items") or ())
                if i.get("status") != "PASS"
            ]
            self._gate_failed_checks = failed
            self._gate_blocked = True
            self.badge_label.setText("권한 점검 실패")
            self.badge_label.setToolTip("어긋난 항목: " + ", ".join(str(f) for f in failed))
            theme_mod.set_state(self.badge_label, theme_mod.STATE_FAIL)
            joined = ", ".join(str(f) for f in failed)
            # 재시작을 예약했는지는 백엔드가 안다. 추측하지 않고 읽는다.
            retrying = bool(getattr(self.backend, "gate_restart_pending", False))
            self.chat_view.add_notice(
                (NOTICE_GATE_BLOCKED if retrying else NOTICE_GATE_BLOCKED_FINAL) % joined
            )
        self._update_controls()
        self._update_status()

    def _on_machine_note(self, tag, detail=""):
        """상태머신 진단 한 줄을 백엔드 로그북에 넘긴다.

        로그북은 spawn 마다 새로 열리므로 호출 시점에 찾는다. 없으면 버린다.
        """
        backend = self.backend
        book = getattr(backend, "logbook", None) if backend is not None else None
        if book is not None:
            book.diag("ui_" + str(tag), detail)

    # ------------------------------------------------------------------
    # 거부 재시도 바
    # ------------------------------------------------------------------

    def _update_denial_bar(self):
        """거부가 있는 가장 최근 턴에 바 하나를 붙인다(설계 3-5).

        거부마다 쌓지 않고 턴당 하나다. 사용자가 닫은 턴은 다시 띄우지 않는다.
        """
        target = None
        for turn in reversed(self.machine.turns):
            if turn.denials:
                target = turn
                break
        if target is None or target.turn_no in self._denial_dismissed:
            self.denial_bar.hide_bar()
        else:
            self.denial_bar.show_attempts(target.turn_no, target.denials)
        self._update_exclusion_bar()

    def _update_exclusion_bar(self):
        """제외가 있는 가장 최근 턴에 안내 바 하나를 붙인다(설계 3-5 표).

        거부 바와 독립이다. 한 턴에 거부와 제외가 같이 날 수 있고, 그때 두 바가
        같이 보여야 사용자가 "허용으로 풀리는 것" 과 "안 풀리는 것" 을 구분한다.
        """
        target = None
        for turn in reversed(self.machine.turns):
            if turn.exclusions:
                target = turn
                break
        if target is None or target.turn_no in self._exclusion_dismissed:
            self.exclusion_bar.hide_bar()
            return
        self.exclusion_bar.show_exclusions(target.turn_no, target.exclusions)

    def _on_exclusion_dismissed(self):
        """제외 안내 바를 닫았다. 그 턴은 다시 띄우지 않는다."""
        turn_no = self.exclusion_bar.turn_no()
        if turn_no is not None:
            self._exclusion_dismissed.add(turn_no)
        else:
            for turn in self.machine.turns:
                if turn.exclusions:
                    self._exclusion_dismissed.add(turn.turn_no)
        self.exclusion_bar.hide_bar()

    def _on_denial_retry(self):
        """"허용하고 다시 요청". 상승 경로는 S5 가 받는다."""
        turn_no = self.denial_bar.turn_no()
        self._dismiss_denial(turn_no)
        self.denial_retry_requested.emit()

    def _on_denial_keep(self):
        """"거부 유지". 바를 닫고 그 턴을 다시 띄우지 않는다."""
        self._dismiss_denial(self.denial_bar.turn_no())

    def _dismiss_denial(self, turn_no):
        """닫은 턴을 기억한다. 턴 번호를 모르면 지금 열린 턴들을 전부 닫는다."""
        if turn_no is not None:
            self._denial_dismissed.add(turn_no)
        else:
            for turn in self.machine.turns:
                if turn.denials:
                    self._denial_dismissed.add(turn.turn_no)
        self.machine.awaiting_approval = False
        self.denial_bar.hide_bar()

    # ------------------------------------------------------------------
    # 워치독 (설계 4-5)
    # ------------------------------------------------------------------

    def _on_watchdog_tick(self):
        """1초마다 침묵을 다시 보고 카운트다운을 쓴다.

        총 경과로 끊지 않는다. 같은 전처리 과업 실측이 141.7 s 라 총 경과
        기준은 정상 작업을 죽인다(설계 4-5).
        """
        # 게이트 실패 재시작이 끝나면 차단을 푼다(S5-1).
        # 풀지 않으면 교착이다. 새 백엔드의 init 은 사용자가 한 턴을 보낸 뒤에만
        # 오는데(D06 FAIL) 입력이 막혀 있으면 보낼 수가 없다. 그래서 재시작이
        # 끝난 시점에 "권한 미확인" 으로 되돌리고 첫 턴에서 다시 게이트를 돈다.
        # 전용 시그널을 만들지 않고 이 1초 틱에서 동기화한다.
        backend = self.backend
        if self._gate_blocked and backend is not None \
                and not getattr(backend, "gate_blocked", False) \
                and backend.is_running():
            self._gate_blocked = False
            self.badge_label.setText(BADGE_UNKNOWN)
            self.badge_label.setToolTip(
                "백엔드를 다시 띄웠습니다. 다음 턴의 init 에서 다시 점검합니다."
            )
            theme_mod.set_state(self.badge_label, theme_mod.STATE_UNKNOWN)
            self._update_controls()

        # 백엔드가 다시 살아났으면 "기동 실패" 항목을 내린다. 재시작 경로가
        # 여럿이라(사망 자동 재시작, 취소, cwd 변경, 상승) 각 경로에서 지우는
        # 대신 이 1초 틱에서 한 번만 동기화한다.
        if self._backend_rc is not None and backend is not None \
                and backend.is_running():
            self._backend_rc = None
            self.refresh_prerequisites()

        # 진행 중 표시의 점을 한 칸 돌린다. 전용 타이머를 만들지 않는다.
        #
        # 0.6.1: 글자를 직접 쓰지 않고 조립 함수를 부른다. 직접 쓰면 대기
        # 건수 꼬리를 매 틱 지운다(_apply_busy_label docstring).
        if self.busy_label.isVisible():
            self._busy_dots = (self._busy_dots + 1) % (BUSY_DOTS_MAX + 1)
            self._apply_busy_label()

        turn = self.machine.current_turn
        if turn is None:
            self.watchdog_row.setVisible(False)
            self._silence_ack_s = 0.0
            self._update_status()
            return
        status, value = self.machine.watchdog()
        if status == "too_long":
            self.watchdog_label.setText(
                "턴이 %s 를 넘었습니다. 취소(백엔드 재시작)를 권합니다."
                % _mmss(machine_mod.TURN_TOTAL_MAX_S)
            )
            self.watchdog_row.setVisible(True)
        elif status == "silent" and value > self._silence_ack_s + machine_mod.SILENCE_WARN_S:
            elapsed = time.time() - (turn.started_ts or time.time())
            remaining = machine_mod.TURN_TOTAL_MAX_S - elapsed
            self.watchdog_label.setText(
                "응답이 없습니다 (침묵 %s). 총 상한까지 %s 남았습니다."
                % (_mmss(value), _mmss(remaining))
            )
            self.watchdog_row.setVisible(True)
        else:
            self.watchdog_row.setVisible(False)
        self._update_status()

    def _on_keep_waiting(self):
        """"계속 기다리기". 지금 침묵 길이를 기준으로 다시 120 s 를 센다."""
        _, value = self.machine.watchdog()
        self._silence_ack_s = float(value)
        self.watchdog_row.setVisible(False)

    # ------------------------------------------------------------------
    # 표시 갱신
    # ------------------------------------------------------------------

    def _ensure_backend(self):
        """백엔드가 없으면 공장으로 만들어 띄운다(설계 2-1: 첫 전송에서 spawn).

        Returns:
            BackendProcess or None
        """
        if self.backend is not None:
            if not self.backend.is_running():
                self.backend.start()
            return self.backend
        if self._backend_factory is None:
            return None
        backend = self._backend_factory()
        if backend is None:
            return None
        self.attach_backend(backend)
        if not backend.is_running():
            backend.start()
        return backend

    def _update_chip(self):
        """상태 칩. init 요약에서 모델/도구 수/MCP 를 가져온다(설계 4-2)."""
        chip = self.machine.chip
        if not chip:
            return
        servers = chip.get("mcp_servers") or ()
        self.chip_label.setText(
            "모델 %s  ·  도구 %d  ·  MCP %s"
            % (chip.get("model") or "-", chip.get("tools_n") or 0,
               ", ".join(servers) if servers else "없음")
        )

    def _update_controls(self):
        """전송/취소 버튼과 입력 placeholder 를 상태에 맞춘다.

        0.6.1: **턴 중에도 전송을 막지 않는다.** 보낸 글은 CLI 큐에 쌓이고
        턴이 끝나면 자동으로 다음 턴으로 실행된다(설계 2-4 의 정정 근거는
        `send_message` docstring). 능력이 없는 백엔드에서는 `process.send`
        가 거부하므로 버튼이 켜져 있어도 보내지지 않는다 - 거부 판단을 UI 에
        복사하지 않는 쪽이다.
        """
        has_factory = self._backend_factory is not None
        backend = self.backend
        busy = bool(backend is not None and backend.is_busy())
        alive = bool(backend is not None and backend.is_running())
        # 게이트 차단은 백엔드 쪽 사실이 우선이다. 독의 플래그는 백엔드가 아직
        # 없을 때(재시작 중)를 메우는 용도다.
        blocked = bool(getattr(backend, "gate_blocked", False)) or self._gate_blocked
        can_type = (has_factory or backend is not None) and not blocked
        self.input_edit.setEnabled(can_type)
        if blocked:
            placeholder = PLACEHOLDER_GATE_BLOCKED
        elif can_type:
            placeholder = PLACEHOLDER_READY
        else:
            placeholder = PLACEHOLDER_NO_BACKEND
        self.input_edit.setPlaceholderText(placeholder)
        has_text = bool(self.input_edit.toPlainText().strip())
        # `not busy` 를 뺐다(0.6.1 요구사항 1). 입력창은 전부터 busy 와
        # 무관했고 버튼만 꺼져 있었다.
        self.send_button.setEnabled(can_type and has_text)
        # 0.6.1: [취소] 는 "지금 턴 중단" 이 됐으므로 **턴이 돌 때만** 누를 수
        # 있다. 1차 배선(7735db1)까지는 `alive or busy` 여서 도는 턴이 없을 때도 백엔드를
        # 재시작할 수 있었다 - 그 조작은 Esc 와 짝이 맞지 않는다(Esc 는 끊을
        # 턴이 없으면 Qt 로 넘어간다). 재시작 경로 자체는 남아 있다:
        # 침묵 워치독 바의 [취소] 와 끊기 폴백이 부른다.
        self.cancel_button.setEnabled(busy)
        self.cwd_label.setEnabled(not busy)
        # 내보내기(0.2.3). 빈 전사를 저장하면 머리글만 있는 파일이 생기므로
        # 행이 하나라도 있을 때만 누를 수 있게 둔다. 이유는 툴팁이 말한다.
        has_rows = self.chat_view.row_count() > 0
        self.export_button.setEnabled(has_rows)
        self.export_button.setToolTip(
            EXPORT_BUTTON_TIP if has_rows else EXPORT_EMPTY_TIP)
        # 대화 지우기(U11). 같은 두 축(행이 있는가, 턴이 도는가)을 본다.
        self._refresh_clear_button()
        # 새 대화(U16). 턴 축만 본다 - 빈 화면에서도 세션은 새로 시작할 수 있다.
        self._refresh_new_button()
        # 진행 중 표시(0.2.2) + 대기 건수(0.6.1). 글자 조립은 한 자리에만
        # 둔다 - 워치독 틱도 같은 함수를 부른다(_apply_busy_label docstring).
        self._apply_busy_label()
        self._refresh_queue_bar()

    def _update_status(self):
        """[7] 상태 바 한 줄."""
        turn = self.machine.current_turn
        parts = ["상태 %s" % self.machine.state]
        if turn is not None:
            elapsed = time.time() - (turn.started_ts or time.time())
            parts.append("턴 %d 경과 %s" % (turn.turn_no, _mmss(elapsed)))
            parts.append("침묵 %s" % _mmss(self.machine.silence_s()))
        else:
            closed = self.machine.last_closed_turn
            if closed is not None and closed.started_ts and closed.ended_ts:
                parts.append(
                    "직전 턴 %d %s" % (closed.turn_no, _mmss(closed.ended_ts - closed.started_ts))
                )
        stage = self.machine.tool_stage()
        if stage:
            parts.append("도구 %s" % stage)
        if self._stderr_count:
            parts.append("stderr %d줄" % self._stderr_count)
        if self.machine.rate_limit_warnings:
            # 수치 표시는 비범위이고 경고 한 줄은 범위 안이다(설계 4-2, 9).
            parts.append(self.machine.rate_limit_warnings[-1])
        self.status_label.setText("  ·  ".join(parts))

    # ------------------------------------------------------------------
    # 조회 (검증 하네스가 읽는다)
    # ------------------------------------------------------------------

    def stats(self):
        """독 상태 요약. 완료 판정의 근거를 한 dict 로 모은다."""
        out = {
            "state": self.machine.state,
            "badge": self.badge_label.text(),
            "status": self.status_label.text(),
            "chip": self.chip_label.text(),
            # isVisible() 은 조상이 숨어 있으면 거짓이다. 여기서 알고 싶은 것은
            # "띄우기로 했는가" 이므로 isHidden() 의 반대를 쓴다.
            "denial_visible": not self.denial_bar.isHidden(),
            "denial_turn": self.denial_bar.turn_no(),
            "denial_text": self.denial_bar.label_text(),
            "exclusion_visible": not self.exclusion_bar.isHidden(),
            "exclusion_turn": self.exclusion_bar.turn_no(),
            "exclusion_text": self.exclusion_bar.label_text(),
            "gate_blocked": bool(self._gate_blocked),
            "gate_failed_checks": list(self._gate_failed_checks),
            "gate_warn_checks": list(self._gate_warn_checks),
            "input_enabled": self.input_edit.isEnabled(),
            "placeholder": self.input_edit.placeholderText(),
            "posture": self._posture_name,
            "elevate_count": self._elevate_count,
            "cwd": self._cwd,
            "cwd_edit_visible": not self.cwd_edit_row.isHidden(),
            "stale_visible": not self.stale_bar.isHidden(),
            "stale_text": self.stale_bar.label_text(),
            "stale_target": self.stale_bar.target(),
            # 0.2.3 내보내기. 바가 떴는가와 어디에 썼는가를 밖에서 읽는다.
            "export_visible": not self.export_bar.isHidden(),
            "export_text": self.export_bar.label_text(),
            "export_target": self.export_bar.target(),
            "export_enabled": self.export_button.isEnabled(),
            # U11 대화 지우기. 확인 단계가 서 있는지와 버튼 문구를 밖에서 읽는다.
            "clear_enabled": self.clear_button.isEnabled(),
            "clear_armed": bool(self._clear_armed),
            "clear_text": self.clear_button.text(),
            "clear_tooltip": self.clear_button.toolTip(),
            # U16 새 대화. 확인 단계와 횟수를 밖에서 읽는다.
            "new_enabled": self.new_button.isEnabled(),
            "new_armed": bool(self._new_armed),
            "new_text": self.new_button.text(),
            "new_tooltip": self.new_button.toolTip(),
            "new_session_count": int(self._new_session_count),
            # U6 연결 표시. 판정·포트·색 상태를 따로 읽는다 - 글자만 보면
            # 색이 맞는지 알 수 없다.
            "conn_text": self.conn_label.text(),
            "conn_tooltip": self.conn_label.toolTip(),
            "conn_state": str(self.conn_label.property(
                theme_mod.STATE_PROPERTY) or ""),
            "conn_dot_state": str(self.conn_dot.property(
                theme_mod.STATE_PROPERTY) or ""),
            "conn_probe_wired": self._port_probe is not None,
            "conn_probe_inflight": bool(self._probe_inflight),
            "conn_probe_ms": int(self._probe_timer.interval()),
            "last_probe": self._last_probe,
            # U5 푸터.
            "footer_text": self.footer_link.text(),
            "footer_tooltip": self.footer_link.toolTip(),
            # U10 키 패널 칸. 스플리터 분배와 최소 높이를 밖에서 읽는다.
            "key_scroll_visible": not self.key_scroll.isHidden(),
            "key_scroll_min_h": int(self.key_scroll.minimumHeight()),
            "key_scroll_resizable": bool(self.key_scroll.widgetResizable()),
            "split_sizes": list(self.body_split.sizes()),
            "split_count": int(self.body_split.count()),
            "split_collapsible": bool(self.body_split.childrenCollapsible()),
            # 차트 2종과 바텀 내비. 밖에서 "무엇이 그려졌나" 를 읽는 창구다.
            "stats_pane_visible": not self.stats_pane.isHidden(),
            "usage_chart": self.stats_pane.usage_card.stats(),
            "collect_chart": self.stats_pane.collect_card.stats(),
            "usage_events": int(self._usage_events),
            "cost_events": int(self._cost_events),
            "nav_current": self.bottom_nav.current(),
            "nav_stats": self.bottom_nav.stats(),
            "watchdog_visible": not self.watchdog_row.isHidden(),
            "watchdog_text": self.watchdog_label.text(),
            "send_enabled": self.send_button.isEnabled(),
            "cancel_enabled": self.cancel_button.isEnabled(),
            "stderr_lines": self._stderr_count,
            "cancel_ms": self._cancel_elapsed_ms,
            "last_batch": self._last_batch_n,
            # S6
            "prereq_visible": not self.prereq_bar.isHidden(),
            "prereq_codes": list(self.prereq_bar.codes()),
            "prereq_text": self.prereq_bar.label_text(),
            # 0.2.2 심미 패스
            "prereq_levels": list(self.prereq_bar.levels()),
            "prereq_more_visible": self.prereq_bar.more_visible(),
            "badge_state": str(self.badge_label.property(
                theme_mod.STATE_PROPERTY) or ""),
            "busy_visible": not self.busy_label.isHidden(),
            "busy_text": self.busy_label.text(),
            # 0.6.1 큐·끼어들기. 대기 건수의 **출처**는 상태머신이고
            # `result.queued_turn_count` 가 아니다(_queued_count docstring).
            "busy_tooltip": self.busy_label.toolTip(),
            "queued_count": self._queued_count(),
            "queued_uuids": list(self._queued_uuids()),
            "queue_bar_visible": not self.queue_row.isHidden(),
            "queue_bar_text": self.queue_label.text(),
            "queue_cancel_enabled": self.queue_cancel_button.isEnabled(),
            "interrupt_requests": int(self._interrupt_requests),
            "interrupt_pending_text": self._interrupt_text,
            "interrupt_request_id": self._interrupt_request_id,
            "interrupt_acked": bool(self._interrupt_acked),
            "queue_cancel_requests": int(self._queue_cancel_requests),
            "interrupted_turns": sorted(self._interrupted_notice_turns),
            # 0.6.1 Claude Code 동형 조작. 요청 수는 축마다 따로 센다 -
            # 하나로 묶으면 "끊었는가" 와 "지금 보냈는가" 를 가를 수 없다.
            "stop_requests": int(self._stop_requests),
            "stop_request_id": self._stop_request_id,
            "send_now_requests": int(self._send_now_requests),
            "send_now_request_id": self._send_now_request_id,
            "recall_requests": int(self._recall_requests),
            "recalled_uuids": list(self._recalled),
            "sent_message_uuids": list(self._sent_messages),
            "dim_uuids": sorted(self._dim_uuids),
            "queue_recall_text": self.queue_cancel_button.text(),
            "cancel_tooltip": self.cancel_button.toolTip(),
            "cwd_display": self.cwd_label.text(),
            "preset_states": self.preset_row.states(),
            "preset_turns": dict(self._preset_turns),
            "marker_visible": not self.marker_bar.isHidden(),
            "marker_turn": self.marker_bar.turn_no(),
            "marker_preset": self.marker_bar.preset(),
            "marker_text": self.marker_bar.label_text(),
            "marker_verdicts": list(self._marker_verdicts),
            # 0.2.0 포스처 확인 바
            "posture_bar_visible": not self.posture_bar.isHidden(),
            "posture_bar_preset": self.posture_bar.preset(),
            "posture_bar_posture": self.posture_bar.posture(),
            "posture_bar_text": self.posture_bar.label_text(),
            "posture_label": posture_mod.POSTURE_LABELS.get(
                self._posture_name, self._posture_name),
            "terminal_notice": self.terminal_notice_label.text(),
            # 0.3.0 공존 안내와 자체 점검(설계 8-3 (j) 가 읽는 값).
            "coexist_notice": self.coexist_notice_label.text(),
            "coexist_notice_hidden": self.coexist_notice_label.isHidden(),
            # 0.4.0 미로그인 가드 3종이 하네스에 내보이는 창구.
            "login_notice": self.login_notice_label.text(),
            "login_notice_hidden": self.login_notice_label.isHidden(),
            "login_notice_turns": sorted(self._login_notice_turns),
            # 헤더·공지 접기(사용자 실기 피드백 2026-10-16). 라벨의
            # `*_hidden` 은 "그 안내가 켜졌는가" 이고, 아래 값들은 "지금
            # 펼쳐 보이는가" 다 - 두 축을 따로 읽어야 접기와 끄기가 섞이지
            # 않는다.
            "header_expanded": bool(self.header_expanded),
            "header_more_hidden": self.header_more.isHidden(),
            "header_toggle_checked": self.header_toggle.isChecked(),
            "header_toggle_text": self.header_toggle.text(),
            "notice_expanded": bool(self._notice_expanded),
            "notice_list_hidden": self.notice_list.isHidden(),
            "notice_box_hidden": self.notice_box.isHidden(),
            "notice_count": self.notice_count(),
            "notice_toggle_text": self.notice_toggle.text(),
            "notice_user_collapsed": bool(self._notice_user_collapsed),
            "self_check": self._last_self_check,
            "self_check_wired": self._self_check is not None,
            "terminal_notice_hidden": self.terminal_notice_label.isHidden(),
            "input_text": self.input_edit.toPlainText(),
            # U2 테마 컨트롤. 고른 값·켜진 칸·강제 여부를 따로 읽는다 -
            # 모드만 보면 세그먼트가 실제로 그 칸을 켰는지 알 수 없다.
            "theme_mode": self.theme_mode,
            "theme_modes": list(theme_mod.THEME_MODES),
            # 0.5.1: 세그먼트가 드롭다운이 됐다. 키 이름은 그대로 둔다 -
            # 하네스가 읽는 창구 이름이고, 묻는 것도 그대로다("컨트롤이
            # 실제로 그 값을 가리키는가"). 드롭다운은 하나만 고를 수
            # 있으므로 목록 길이는 0 또는 1 이다.
            "theme_seg_checked": [m for m in theme_mod.THEME_MODES
                                  if self.theme_pick.currentData() == m],
            "theme_forced": self.theme_mode != theme_mod.THEME_MODE_SYSTEM,
            # 0.4.0 모델 선택. 고른 값·켜진 칸·CLI 인자를 따로 읽는다 -
            # 선택값만 보면 세그먼트가 그 칸을 켰는지, argv 에 무엇이 가는지
            # 알 수 없다.
            "model_choice": self.model_choice,
            "model_choices": list(posture_mod.MODEL_CHOICES),
            # 0.5.1: 테마와 같은 이유로 키 이름을 그대로 둔다.
            "model_seg_checked": [c for c in posture_mod.MODEL_CHOICES
                                  if self.model_pick.currentData() == c],
            "model_arg": posture_mod.model_arg(self.model_choice),
            # 0.4.0 입력 히스토리. 목록과 탐색 위치를 따로 읽는다.
            "input_history": self.input_history.items(),
            "input_history_index": self.input_history.index(),
            "input_history_browsing": self.input_history.browsing(),
            # 0.4.0 저장 안내 자동 숨김.
            "export_bar_auto_hide": self.export_bar.auto_hide_active(),
            "export_bar_auto_hide_ms": self.export_bar.auto_hide_ms(),
            # 0.4.2 저장 안내 우상단 닫기(X). 자동 숨김과 **다른 축**이다 -
            # 하나는 시간이 내리는 것이고 하나는 사용자가 내리는 것이다.
            "export_bar_close_visible": self.export_bar.close_button_visible(),
            # U4 프리셋 카드의 그라데이션 테두리 두 끝(지금 팔레트 기준).
            "preset_border_colors": list(self.preset_row.border_colors()),
            # S7 브랜딩
            "theme_dark": bool(self.theme_dark),
            "brand_wordmark": self.brand_link.wordmark_text(),
            "brand_tooltip": self.brand_link.toolTip(),
            "dock_qss_len": len(self.body.styleSheet()),
            # 0.2.1 키 설정과 레다크션. 어느 칸에도 키 값이 들어가지 않는다.
            "keys_button_checked": self.keys_button.isChecked(),
            "redactions": self.redactor.count,
            "redact_secrets_n": self.redactor.secrets_n,
        }
        out.update(self.chat_view.stats())
        out.update(self.key_panel.stats())
        return out
