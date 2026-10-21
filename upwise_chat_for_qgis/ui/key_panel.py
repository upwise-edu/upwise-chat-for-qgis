"""비모달 키 설정 패널 (0.5.0, 설계 docs/2 8 + docs/8 5-1, 5-2, 5-3).

왜 독 안의 패널인가
    1순위가 독 안의 **비모달 설정 패널**이다(설계 8). 모달은 금지다 - 모달
    팝업이 자동화를 정지시킨다(설계 3-5). `QFileDialog` 도 쓰지 않는다. 그래서
    이 패널은 떠 있는 동안에도 QGIS 조작이 되고, 지도에서 좌표를 보며 키를
    넣을 수 있다. QGIS 옵션 페이지는 2순위이고 이번 범위가 아니다.

패널이 보여 주는 것 (설계 docs/8 5-2 안 A - 한 패널 3섹션)
    섹션 1  제공자별 키 입력(마스킹 표시) / 저장 / 삭제. 다필드 제공자는
            칸이 **세로로 쌓인다**(SGIS 는 서비스 ID + 보안 Key 둘이다).
    섹션 2  고급(접힘): 엔드포인트 기본 주소
    섹션 3  고급(접힘): data.go.kr 데이터셋 등록
    그리고 "저장 위치와 평문 여부" 안내 한 줄.

    제공자 선택 콤보 + 스택(안 B)을 쓰지 않은 이유는 설계 5-2 표에 있다 -
    이 패널의 1차 기능이 "왜 수집 버튼이 꺼져 있나" 에 답하는 것이고 그
    답은 3사 동시 표시여야 성립한다. 콤보는 가로도 먹는다.

키 값을 다루는 규칙
    * 입력 위젯은 `QLineEdit.Password` 다. 화면에 글자가 남지 않는다.
    * **저장 성공 즉시 입력 칸을 비운다.** 패널이 화면 공유나 캡처에 들어갈
      수 있고, 위젯에 남은 값은 지울 이유가 없는 사본이다.
    * 상태 표시는 `keystore.mask()` 를 쓴다. 값의 어느 글자도 내보내지 않는다
      (끝 네 자리를 보여 주는 흔한 UX 를 일부러 쓰지 않는다).
    * 이 모듈은 **값을 로그에 넘기지 않는다.** 밖으로 내는 시그널
      `keys_changed(int)` 의 인자는 설정된 제공자 **수**다.
    * 다필드 제공자는 required 칸이 **전부** 찼을 때만 설정된 것으로 센다.
      부분 입력의 상태 문구에는 빠진 **칸 이름**만 적는다(값 금지).

저장은 keystore 와 userregistry 가 한다
    `QgsSettings` 쓰기와 `sync()` 는 `backend/keystore` 하나가 맡는다(설계
    5-3 단서 2: sync 를 안 부르면 수집 서버가 빈 값을 읽는다). 등록 레코드
    파일 쓰기는 `backend/userregistry` 가 맡고 원자적으로 쓴다. 패널은 결과
    문구만 그린다.

등록 섹션의 범위 (설계 docs/8 5-3)
    입력은 이름·엔드포인트 주소·프리셋·호출 파라미터이고 봉투 필드는 접힌
    고급 칸에 있다. **편집 UI 는 만들지 않는다** - 고치려면 지우고 다시
    등록한다(범위 통제). 프리셋 정의는 **서버측 카탈로그가 정본**이고 이
    패널은 읽기만 한다. 정의가 없는 회차에서는 콤보가 비고 등록이 거절된다.

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog, QFileDialog,
중첩 이벤트 루프. Qt import 는 전부 qgis.PyQt 셰임 경로로 한다(설계 7-4).

설계 정본: docs/2.collect_feature_design_v1.md 5-2, 5-3, 8 /
docs/8.collect_expansion_design_v1.md 4-3, 5-1, 5-2, 5-3
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..backend import keystore, userregistry
from . import theme as theme_mod
from .approval_bar import BAR_BUTTON_MIN_W
from .chat_view import CollapsibleSection

# 패널 머리말.
PANEL_HEADER = "공공 API 키"

# "저장 위치와 평문 여부" 안내 한 줄(설계 8 필드 목록의 항목). 사실만 적는다 -
# 평문이라는 것을 숨기지 않는 것이 설계 5-2 의 조건이다.
#
# U15(0.3.x UI 패스 2차): "전사" 를 "대화 기록" 으로 바꿨다. 사용자 노출 문구에
# 내부 용어를 쓰지 않는다는 원칙의 연장이고, 이 줄이 가리키는 세 곳(채팅 입력,
# 저장되는 대화, 로그)은 그대로다. 상수 이름과 하네스 24 P6 의 판정 근거
# ("QGIS3.ini"·"평문")도 건드리지 않는다.
STORAGE_NOTICE = (
    "키는 이 PC 의 QGIS 설정 파일(QGIS3.ini)에 평문으로 저장됩니다. "
    "사본은 그 파일 하나뿐이고, 채팅과 대화 기록과 로그에는 들어가지 않습니다."
)

# 키를 채팅에 붙여 넣지 말라는 한 줄. 붙여 넣는 순간 모델 제공자 서버와 CLI
# 자체 세션 저장소에 남고 우리가 지울 수 없다(S9a 실측, 설계 5-1 L2/L3).
PASTE_WARNING = (
    "키를 채팅 입력창에 붙여 넣지 마세요. 한 번 들어가면 지울 수 없는 곳에 "
    "남습니다. 수집은 이 칸에 넣은 키로만 돌아갑니다."
)

# 제공자 행의 상태 문구.
STATE_SET = "저장됨 %s"
STATE_UNSET = "키가 설정되지 않았습니다"
STATE_NOT_NEEDED = "키가 필요하지 않습니다"
# 부분 입력(설계 docs/8 5-1). 빠진 **칸 이름**만 적는다. 값은 적지 않는다.
STATE_PARTIAL = "일부만 설정됐습니다. 빠진 칸: %s"
# 다필드 제공자의 칸별 마스킹 표시를 잇는 형식.
STATE_FIELD_FMT = "%s %s"

# 고급 칸.
#
# 제목을 **두 줄로 적는다**(2026-10-21). 접힘 머리는 QToolButton 이고
# QToolButton 은 줄바꿈을 자동으로 하지 않는다 - 그래서 한 줄짜리 제목이
# 그대로 이 영역의 최소 폭이 되고, 키 패널이 가로 스크롤이 꺼진
# QScrollArea 안에 있어서 좁은 독에서는 넘치는 만큼이 **조용히 잘렸다**
# (하네스 88 W8: 뷰포트 311 px 에 제목 380 px). 문구에 개행을 넣으면
# QFontMetrics 가 여러 줄로 재어 최소 폭이 가장 긴 줄로 떨어진다(실측).
# 문구를 줄이지 않고 폭만 내리는 쪽을 고른 이유는 "엔드포인트 기본 주소"
# 가 이 칸이 무엇인지 말하는 유일한 설명이기 때문이다.
ADVANCED_TITLE = "고급: 엔드포인트\n기본 주소 바꾸기"
ADVANCED_NOTICE = (
    "레지스트리의 기본 주소 대신 쓸 주소입니다. 기관 프록시 대역이나 시험용 "
    "서버가 아니면 비워 두세요. 모든 데이터셋 요청에 함께 적용됩니다."
)
ADVANCED_SET = "설정됨: %s"
ADVANCED_UNSET = "설정되지 않았습니다(레지스트리 기본 주소를 씁니다)"

# 입력 칸 placeholder.
KEY_PLACEHOLDER = "키를 붙여 넣고 [저장] 을 누르세요"
URL_PLACEHOLDER = "https://..."

# ----------------------------------------------------------------------
# 섹션 3 - data.go.kr 데이터셋 등록 (설계 docs/8 5-3)
# ----------------------------------------------------------------------

# 두 줄로 적는 근거는 ADVANCED_TITLE 주석과 같다(실측 431 px -> 뷰포트 안).
REGISTER_TITLE = "고급: data.go.kr\n데이터셋 등록"

# **문구 2줄 고정**(설계 docs/8 5-3). 승인 축과 한도 축을 각각 한 줄로 말한다.
# 서버는 승인 상태도 한도도 알 수 없으므로 추정 진단을 하지 않고 이 두 줄로
# 사용자에게 먼저 알린다(설계 3-5 귀결).
#
# 정본은 **카탈로그 선언**이다(지휘자 결정 2026-10-17). 패널은
# `keystore.registration_notices()` 로 읽고, 선언이 없는 회차에서만 아래
# 상수로 떨어진다. 카탈로그 문면과 이 상수의 축자 일치는 하네스 24 가
# 판정한다(A6/A7/A11 과 같은 처방) - 두 곳이 어긋나면 그 행이 FAIL 한다.
REGISTER_NOTICE_APPROVAL = (
    "data.go.kr 은 API 마다 활용신청 승인이 있어야 호출됩니다."
)
REGISTER_NOTICE_QUOTA = (
    "일일 호출 한도는 API 마다 다르고 공개되지 않는 경우가 많습니다."
)

# 입력 라벨과 placeholder.
REGISTER_NAME_LABEL = "데이터셋 이름"
REGISTER_NAME_PLACEHOLDER = "목록에 보일 이름"
REGISTER_URL_LABEL = "엔드포인트 주소"
REGISTER_URL_PLACEHOLDER = "https://apis.data.go.kr/..."
REGISTER_PRESET_LABEL = "프리셋"
REGISTER_PARAMS_LABEL = "호출 파라미터"
REGISTER_PARAMS_PLACEHOLDER = (
    "한 줄에 하나. type=json 처럼 값을 적으면 고정값이고, "
    "이름만 적으면 모델이 채우는 칸입니다."
)
REGISTER_SAVE_TEXT = "등록"
REGISTER_DELETE_TEXT = "삭제"
REGISTER_EMPTY = "등록된 데이터셋이 없습니다."
REGISTER_NO_PRESET = "프리셋 정의가 없어 등록할 수 없습니다."
REGISTER_PRESET_EMPTY_ITEM = "프리셋 정의가 없습니다"
REGISTER_LIST_LABEL = "등록된 데이터셋"
REGISTER_VERIFIED_YES = "검증됨"
REGISTER_VERIFIED_NO = "미검증"
REGISTER_MESSAGE_FMT = "등록: %s"

# 등록 섹션의 고급(봉투) 칸. 프리셋이 채운 값을 고칠 수 있어야 한다 -
# 표본 2건의 봉투 일반성이 미확인이기 때문이다(설계 docs/8 3-5 U11).
# 등록 칸 **안쪽**의 접힘이다. 바깥 제목을 두 줄로 내린 뒤 남은 폭 제약이
# 이 제목 하나였다(실측: 등록 칸 최소 폭 312 px 중 300 px 이 이 버튼).
# 같은 이유로 두 줄이다.
REGISTER_ADVANCED_TITLE = "응답 봉투와\n페이징 고치기"
REGISTER_ADVANCED_NOTICE = (
    "비워 두면 프리셋 값을 그대로 씁니다. 기관마다 응답 모양이 달라서 "
    "맞지 않을 때만 고칩니다."
)
# (입력 이름, 라벨). 이름은 `userregistry.build_record` 의 advanced 키다.
REGISTER_ADVANCED_FIELDS = (
    ("items_path", "레코드 경로(items_path)"),
    ("code_path", "오류 코드 경로(code_path)"),
    ("ok", "성공 코드(쉼표로 여러 개)"),
    ("lon_field", "경도 필드"),
    ("lat_field", "위도 필드"),
    ("crs", "좌표계"),
    ("page_param", "페이지 번호 파라미터"),
    ("size_param", "페이지 크기 파라미터"),
    ("size", "페이지 크기"),
    ("total_path", "전체 건수 경로"),
)

# 파라미터 입력 칸의 높이 상한(px). 패널이 세로로만 늘어나는 것은 접힘과
# 스크롤로 풀지만(설계 5-2), 입력 칸 하나가 화면을 다 먹지 않게 둔다.
PARAMS_MAX_H = 72


class KeyPanel(QFrame):
    """제공자별 키를 넣고 지우는 비모달 패널.

    시그널 하나만 낸다.

        keys_changed(int)  저장/삭제가 성공했다. 인자는 **설정된 제공자 수**다.
            키 값은 시그널에도 담지 않는다.
    """

    keys_changed = pyqtSignal(int)

    def __init__(self, parent=None, providers=None, settings=None,
                 presets=None, registry_file=None):
        """행을 만들고 현재 상태를 읽어 그린다. 기본은 숨은 상태다.

        Args:
            parent: 부모 위젯.
            providers: 제공자 목록. None 이면 카탈로그에서 읽는다.
                하네스가 행 구성을 고정하는 주입점이다.
            settings: QSettings 호환 객체. None 이면 QgsSettings.
                하네스가 임시 INI 로 실제 Qt 저장/sync 를 재게 하는 주입점이다.
            presets: 등록 프리셋 목록. None 이면 카탈로그에서 읽는다.
                정의가 없으면 빈 목록이고 등록은 거절된다.
            registry_file: 등록 레코드 JSON 경로. None 이면 프로필 기본 경로.
        """
        super().__init__(parent)
        self.setObjectName("UpwiseChatKeyPanel")
        # qss 가 면과 테두리를 그린다. StyledPanel 을 함께 두면 Qt 기본 액자와
        # qss 테두리가 겹쳐 두 겹으로 보인다.
        self.setFrameShape(QFrame.NoFrame)

        self._settings = settings
        self._providers = tuple(providers) if providers is not None \
            else keystore.load_providers()
        self._presets = tuple(presets) if presets is not None \
            else keystore.load_registration_presets()
        self._registry_file = str(registry_file) if registry_file else ""
        self._rows = {}
        self._register_inputs = {}
        self._register_row_widgets = []
        self._register_rows = ()
        # 등록 목록은 **패널이 처음 보일 때** 읽는다. 구성 시점에 읽으면 독을
        # 만들 때마다 프로필 폴더를 만지고(파일 I/O), 등록 파일 경로를 구하려고
        # `qgis.core` 를 그 자리에서 import 하게 된다. 둘 다 패널이 숨어 있는
        # 동안에는 할 이유가 없는 일이다.
        self._registry_loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        head = QLabel(PANEL_HEADER, self)
        head.setObjectName("UpwiseChatKeyPanelHeader")
        theme_mod.set_role(head, theme_mod.ROLE_CAPTION)
        layout.addWidget(head)

        self._notice = QLabel(STORAGE_NOTICE, self)
        self._notice.setObjectName("UpwiseChatKeyPanelNotice")
        self._notice.setWordWrap(True)
        self._notice.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._notice)

        self._warning = QLabel(PASTE_WARNING, self)
        self._warning.setObjectName("UpwiseChatKeyPanelWarning")
        self._warning.setWordWrap(True)
        layout.addWidget(self._warning)

        layout.addWidget(self._build_rows())

        # 마지막 동작의 결과 한 줄. 모달을 쓸 수 없으므로 결과를 여기 적는다.
        self._message = QLabel("", self)
        self._message.setObjectName("UpwiseChatKeyPanelMessage")
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        layout.addWidget(self._build_advanced())
        layout.addWidget(self._build_register())

        self.refresh()
        self.setVisible(False)

    # ------------------------------------------------------------------
    # 위젯 구성
    # ------------------------------------------------------------------

    def _wrap_label(self, text, parent, role=None):
        """줄바꿈 라벨 하나. 최소 폭을 1 로 둔다.

        줄바꿈 라벨의 기본 최소 폭은 한 줄 전체라서 독의 최소 폭을 밀어
        올린다(README 5 실측). 그래서 모든 안내·라벨이 이 창구를 지난다.
        """
        label = QLabel(text, parent)
        label.setWordWrap(True)
        label.setMinimumWidth(1)
        if role is not None:
            theme_mod.set_role(label, role)
        return label

    def _build_rows(self):
        """제공자 행들. 그리드로 두어 라벨/칸/버튼이 세로로 맞는다.

        0.2.2 정돈: 제공자 하나가 **세 줄**을 쓴다.
            1줄  제공자 이름(3열 전체)
            2줄  입력 칸(늘어남) / [저장] / [삭제]
            3줄  상태 문구(3열 전체)

        전에는 상태 문구가 [삭제] **오른쪽 4번째 칸**에 있었다. 그 칸이 늘어나
        독의 최소 폭을 밀어 올렸고, 긴 상태 문구가 버튼과 같은 줄에서 줄바꿈
        되어 버튼 높이까지 흔들렸다.

        0.5.0 다필드(설계 docs/8 5-1): 칸이 둘 이상인 제공자는 둘째 칸부터
        **아래로 쌓인다**. 칸마다 라벨 한 줄이 앞에 붙고, 버튼은 첫 칸 줄에만
        둔다 - 열 구성이 그대로라 **폭은 중립**이고 세로만 늘어난다.
        단일 필드 제공자의 줄 구성은 **바뀌지 않는다**(objectName 도 그대로).
        """
        holder = QWidget(self)
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)

        top = 0
        for row in self._providers:
            pid = row["id"]
            needs = bool(row.get("needs_key", True))
            fields = tuple(row.get("fields") or ())
            if not fields:
                # 저장할 자리가 없는 제공자는 행을 만들지 않는다. 칸 없는
                # 행은 "왜 꺼져 있나" 에 답하지 못한다.
                continue
            save = None
            drop = None
            title = self._wrap_label(row.get("title") or pid, holder,
                                     theme_mod.ROLE_CAPTION)
            # 발급 안내 주소와 함정 문구는 툴팁에만 둔다. 패널에 링크 위젯을
            # 더하지 않는다(범위를 넓히지 않는다).
            title.setToolTip(self._row_tooltip(row))
            grid.addWidget(title, top, 0, 1, 3)
            top += 1

            cells = {}
            order = []
            for idx, field in enumerate(fields):
                name = field["name"]
                label = field.get("label") or ""
                if label:
                    # 라벨이 있는 칸만 머리 한 줄을 둔다. 다필드 제공자는
                    # 항상 라벨이 있고, 단일 필드 제공자는 카탈로그가
                    # `key_label` 을 선언했을 때만 생긴다. 선언이 없는
                    # 제공자(V-World)의 줄 구성은 바뀌지 않는다.
                    cap = self._wrap_label(label, holder,
                                           theme_mod.ROLE_MUTED)
                    grid.addWidget(cap, top, 0, 1, 3)
                    top += 1
                edit = QLineEdit(holder)
                # objectName 규약(설계 docs/8 5-1): 단일 필드는 종전 이름
                # 그대로, 다필드만 `__<field>` 가 붙는다.
                edit.setObjectName("UpwiseChatKeyField_" + pid
                                   + ("__" + name if name else ""))
                # 마스킹 표시. 입력 중에도 글자가 화면에 남지 않는다.
                edit.setEchoMode(QLineEdit.Password)
                edit.setPlaceholderText(KEY_PLACEHOLDER)
                edit.setEnabled(needs)
                # 칸 툴팁: 설정 경로 + 카탈로그가 선언한 안내 문면. 문면을
                # 패널이 쓰지 않는다(카탈로그가 정본이다).
                cell_tip = [field.get("setting") or "", field.get("hint") or ""]
                tip_text = "\n".join(t for t in cell_tip if t)
                if tip_text and (name or field.get("hint")):
                    edit.setToolTip(tip_text)
                # Enter 로도 저장된다. 버튼을 찾아 누르게 하지 않는다.
                edit.returnPressed.connect(
                    lambda pid=pid: self.save_provider(pid))
                grid.addWidget(edit, top, 0)

                if idx == 0:
                    save = QPushButton("저장", holder)
                    save.setObjectName("UpwiseChatKeySave_" + pid)
                    save.setMinimumWidth(BAR_BUTTON_MIN_W)
                    save.setEnabled(needs)
                    # clicked 는 bool 을 넘긴다. 기본값 인자로 삼킨다(S4 실측).
                    save.clicked.connect(
                        lambda _checked=False, pid=pid: self.save_provider(pid))
                    grid.addWidget(save, top, 1)

                    drop = QPushButton("삭제", holder)
                    drop.setObjectName("UpwiseChatKeyDelete_" + pid)
                    drop.setMinimumWidth(BAR_BUTTON_MIN_W)
                    drop.clicked.connect(
                        lambda _checked=False, pid=pid:
                        self.delete_provider(pid))
                    grid.addWidget(drop, top, 2)
                top += 1
                cells[name] = {"field": edit, "meta": field}
                order.append(name)

            state = QLabel("", holder)
            state.setObjectName("UpwiseChatKeyState_" + pid)
            state.setWordWrap(True)
            state.setMinimumWidth(1)
            theme_mod.set_role(state, theme_mod.ROLE_MUTED)
            grid.addWidget(state, top, 0, 1, 3)
            top += 1

            self._rows[pid] = {"cells": cells, "order": tuple(order),
                               "save": save, "delete": drop,
                               "state": state, "meta": row}
        grid.setColumnStretch(0, 1)
        return holder

    def _row_tooltip(self, row):
        """제공자 행의 툴팁. 설정 경로 / 발급 주소 / 함정 문구.

        함정 문구는 카탈로그의 데이터셋 notes 원문이다(설계 docs/8 7-2 (e)).
        여기서 문면을 새로 쓰지 않는다 - SGIS `adm_cd` 가 행정표준코드가
        아니라는 사실을 패널에서도 말해야 하고, 그 문장은 카탈로그가 정본이다.
        """
        tip = []
        for field in row.get("fields") or ():
            label = field.get("label") or ""
            setting = field.get("setting") or ""
            if not setting:
                continue
            tip.append(STATE_FIELD_FMT % (label, setting) if label
                       else setting)
        for field in row.get("fields") or ():
            hint = str(field.get("hint") or "")
            if hint and hint not in tip:
                tip.append(hint)
        if row.get("signup"):
            tip.append("발급: " + row["signup"])
        for note in row.get("tips") or ():
            tip.append(note)
        return "\n".join(t for t in tip if t)

    def _build_advanced(self):
        """고급 칸. 기본 접힘이다(설계 8 "고급, 접힘")."""
        section = CollapsibleSection(ADVANCED_TITLE, self, expanded=False,
                                     object_name="UpwiseChatAdvancedTitle")
        self._advanced = section

        body = QWidget(section)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        layout.addWidget(self._wrap_label(ADVANCED_NOTICE, body,
                                          theme_mod.ROLE_MUTED))

        row = QWidget(body)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        self._url_field = QLineEdit(row)
        self._url_field.setObjectName("UpwiseChatEndpointField")
        self._url_field.setPlaceholderText(URL_PLACEHOLDER)
        self._url_field.returnPressed.connect(self.save_endpoint)
        row_layout.addWidget(self._url_field, 1)
        self._url_save = QPushButton("저장", row)
        self._url_save.setObjectName("UpwiseChatEndpointSave")
        self._url_save.setMinimumWidth(BAR_BUTTON_MIN_W)
        self._url_save.clicked.connect(lambda _checked=False: self.save_endpoint())
        row_layout.addWidget(self._url_save)
        self._url_delete = QPushButton("삭제", row)
        self._url_delete.setObjectName("UpwiseChatEndpointDelete")
        self._url_delete.setMinimumWidth(BAR_BUTTON_MIN_W)
        self._url_delete.clicked.connect(
            lambda _checked=False: self.delete_endpoint())
        row_layout.addWidget(self._url_delete)
        layout.addWidget(row)

        self._url_state = QLabel("", body)
        self._url_state.setObjectName("UpwiseChatEndpointState")
        self._url_state.setWordWrap(True)
        self._url_state.setMinimumWidth(1)
        theme_mod.set_role(self._url_state, theme_mod.ROLE_MUTED)
        layout.addWidget(self._url_state)

        section.add_body_widget(body)
        return section

    def _build_register(self):
        """섹션 3. data.go.kr 데이터셋 등록. 기본 접힘이다(설계 5-2).

        접힘이라 **폭에 중립**이어야 한다 - 본문 위젯은 접힌 상태에서 숨어
        있고, 모든 라벨이 `_wrap_label` 을 지나 최소 폭 1 이다.
        """
        section = CollapsibleSection(REGISTER_TITLE, self, expanded=False,
                                     object_name="UpwiseChatRegisterTitle")
        self._register = section

        body = QWidget(section)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # 문구 2줄 고정(설계 5-3). 두 줄을 따로 두어 둘 다 보이게 한다.
        # 문면은 카탈로그에서 읽고, 선언이 없으면 모듈 상수로 떨어진다.
        approval, quota = keystore.registration_notices(self._providers)
        self._register_notice_approval = self._wrap_label(
            approval or REGISTER_NOTICE_APPROVAL, body, theme_mod.ROLE_MUTED)
        self._register_notice_approval.setObjectName(
            "UpwiseChatRegisterNoticeApproval")
        layout.addWidget(self._register_notice_approval)
        self._register_notice_quota = self._wrap_label(
            quota or REGISTER_NOTICE_QUOTA, body, theme_mod.ROLE_MUTED)
        self._register_notice_quota.setObjectName(
            "UpwiseChatRegisterNoticeQuota")
        layout.addWidget(self._register_notice_quota)

        layout.addWidget(self._wrap_label(REGISTER_NAME_LABEL, body,
                                          theme_mod.ROLE_MUTED))
        name = QLineEdit(body)
        name.setObjectName("UpwiseChatRegisterName")
        name.setPlaceholderText(REGISTER_NAME_PLACEHOLDER)
        layout.addWidget(name)
        self._register_inputs["title"] = name

        layout.addWidget(self._wrap_label(REGISTER_URL_LABEL, body,
                                          theme_mod.ROLE_MUTED))
        url = QLineEdit(body)
        url.setObjectName("UpwiseChatRegisterUrl")
        url.setPlaceholderText(REGISTER_URL_PLACEHOLDER)
        layout.addWidget(url)
        self._register_inputs["base_url"] = url

        layout.addWidget(self._wrap_label(REGISTER_PRESET_LABEL, body,
                                          theme_mod.ROLE_MUTED))
        combo = QComboBox(body)
        combo.setObjectName("UpwiseChatRegisterPreset")
        # 콤보가 가로를 먹지 않게 내용 기준 확장을 끄고 최소 폭을 1 로 둔다.
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(1)
        combo.setMinimumWidth(1)
        if self._presets:
            for preset in self._presets:
                combo.addItem(preset.get("label") or preset.get("name") or "")
        else:
            # 프리셋 정의가 없으면(서버측 정의 부재) 빈 목록으로 열화한다.
            # 사본을 여기 적어 두면 두 곳이 어긋난다.
            combo.addItem(REGISTER_PRESET_EMPTY_ITEM)
            combo.setEnabled(False)
        layout.addWidget(combo)
        self._register_preset = combo

        layout.addWidget(self._wrap_label(REGISTER_PARAMS_LABEL, body,
                                          theme_mod.ROLE_MUTED))
        params = QPlainTextEdit(body)
        params.setObjectName("UpwiseChatRegisterParams")
        params.setPlaceholderText(REGISTER_PARAMS_PLACEHOLDER)
        params.setMaximumHeight(PARAMS_MAX_H)
        params.setMinimumWidth(1)
        layout.addWidget(params)
        self._register_inputs["params"] = params

        layout.addWidget(self._build_register_advanced(body))

        save = QPushButton(REGISTER_SAVE_TEXT, body)
        save.setObjectName("UpwiseChatRegisterSave")
        save.setMinimumWidth(BAR_BUTTON_MIN_W)
        save.clicked.connect(lambda _checked=False: self.register_dataset())
        layout.addWidget(save)
        self._register_save = save

        layout.addWidget(self._wrap_label(REGISTER_LIST_LABEL, body,
                                          theme_mod.ROLE_MUTED))
        holder = QWidget(body)
        holder.setObjectName("UpwiseChatRegisterList")
        self._register_list_layout = QGridLayout(holder)
        self._register_list_layout.setContentsMargins(0, 0, 0, 0)
        self._register_list_layout.setHorizontalSpacing(6)
        self._register_list_layout.setVerticalSpacing(2)
        self._register_list_layout.setColumnStretch(0, 1)
        layout.addWidget(holder)
        self._register_list = holder

        section.add_body_widget(body)
        return section

    def _build_register_advanced(self, parent):
        """등록 섹션 안의 봉투 고급 칸. 기본 접힘이다(설계 5-3)."""
        section = CollapsibleSection(REGISTER_ADVANCED_TITLE, parent,
                                     expanded=False,
                                     object_name="UpwiseChatRegisterAdvTitle")
        self._register_advanced = section

        body = QWidget(section)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._wrap_label(REGISTER_ADVANCED_NOTICE, body,
                                          theme_mod.ROLE_MUTED))
        for name, label in REGISTER_ADVANCED_FIELDS:
            layout.addWidget(self._wrap_label(label, body,
                                              theme_mod.ROLE_MUTED))
            edit = QLineEdit(body)
            edit.setObjectName("UpwiseChatRegisterAdv_" + name)
            edit.setMinimumWidth(1)
            layout.addWidget(edit)
            self._register_inputs[name] = edit
        section.add_body_widget(body)
        return section

    # ------------------------------------------------------------------
    # 동작 - 키
    # ------------------------------------------------------------------

    def save_provider(self, provider):
        """한 제공자의 키를 저장한다. 성공한 칸은 비운다.

        다필드 제공자는 **값이 적힌 칸만** 저장한다 - 한 칸을 고치려고
        나머지 칸을 다시 입력하게 하지 않는다. 결과는 칸별로 한 줄에 적는다.

        Returns:
            bool: 하나라도 저장했고 실패가 없으면 True.
        """
        row = self._rows.get(provider)
        if row is None:
            return False
        results = []
        ok_any = False
        failed = False
        for name in row["order"]:
            cell = row["cells"][name]
            text = cell["field"].text()
            if not text.strip():
                continue
            # 칸의 검증 규칙으로 확인한다(제공자별 `key_re`·`key_form`).
            # 전역 식만 보는 `save_value` 를 쓰면 base64 계열 키가 거절된다.
            ok, why = keystore.save_field(cell["meta"], text,
                                          settings=self._settings)
            if ok:
                # 위젯에 값을 남기지 않는다. 지울 이유가 없는 사본이다.
                cell["field"].clear()
                ok_any = True
            else:
                failed = True
            label = cell["meta"].get("label") or ""
            results.append(STATE_FIELD_FMT % (label, why) if label else why)
        if not results:
            results.append(keystore.KEY_EMPTY_REASON)
        self._message.setText("%s: %s" % (provider, "; ".join(results)))
        self.refresh()
        if ok_any:
            self._emit_changed()
        return ok_any and not failed

    def delete_provider(self, provider):
        """한 제공자의 키를 지운다. 다필드 제공자는 칸 전부를 지운다.

        Returns:
            bool: 삭제 성공 여부.
        """
        row = self._rows.get(provider)
        if row is None:
            return False
        results = []
        ok_all = True
        for name in row["order"]:
            cell = row["cells"][name]
            ok, why = keystore.delete_value(cell["meta"]["setting"],
                                            settings=self._settings)
            ok_all = ok_all and ok
            cell["field"].clear()
            label = cell["meta"].get("label") or ""
            results.append(STATE_FIELD_FMT % (label, why) if label else why)
        # 단일 필드 제공자의 문구는 종전과 같다("vworld: 지웠습니다").
        self._message.setText("%s: %s" % (provider, "; ".join(results)))
        self.refresh()
        if ok_all:
            self._emit_changed()
        return ok_all

    def save_endpoint(self):
        """고급 칸의 엔드포인트 기본 주소를 저장한다.

        Returns:
            bool: 저장 성공 여부.
        """
        ok, why = keystore.save_endpoint_override(self._url_field.text(),
                                                  settings=self._settings)
        self._message.setText("엔드포인트: %s" % why)
        self.refresh()
        return ok

    def delete_endpoint(self):
        """고급 칸의 엔드포인트 기본 주소를 지운다.

        Returns:
            bool: 삭제 성공 여부.
        """
        ok, why = keystore.delete_endpoint_override(settings=self._settings)
        self._url_field.clear()
        self._message.setText("엔드포인트: %s" % why)
        self.refresh()
        return ok

    # ------------------------------------------------------------------
    # 동작 - 등록 섹션
    # ------------------------------------------------------------------

    def selected_preset(self):
        """콤보가 고른 프리셋. 정의가 없으면 None 이다."""
        if not self._presets:
            return None
        idx = int(self._register_preset.currentIndex())
        if idx < 0 or idx >= len(self._presets):
            return None
        return self._presets[idx]

    def register_dataset(self):
        """입력을 레코드로 만들어 등록 파일에 더한다.

        네트워크 호출은 하지 않는다 - 저장 시점 검증은 구조 검증까지다
        (설계 docs/8 4-3). 결과는 패널의 결과 한 줄에 적는다(모달 금지).

        Returns:
            bool: 등록 성공 여부.
        """
        preset = self.selected_preset()
        if preset is None:
            self._message.setText(REGISTER_MESSAGE_FMT % REGISTER_NO_PRESET)
            return False
        advanced = {name: self._register_inputs[name].text()
                    for name, _label in REGISTER_ADVANCED_FIELDS}
        rows, _why = userregistry.load_records(self._registry_file or None)
        record, why = userregistry.build_record(
            preset,
            self._register_inputs["title"].text(),
            self._register_inputs["base_url"].text(),
            self._register_inputs["params"].toPlainText(),
            advanced=advanced,
            existing=[r.get("id") for r in rows])
        if record is None:
            self._message.setText(REGISTER_MESSAGE_FMT % why)
            return False
        ok, why = userregistry.add_record(
            record, path=self._registry_file or None,
            provider_ids=[row["id"] for row in self._providers])
        self._message.setText(REGISTER_MESSAGE_FMT % why)
        if ok:
            # 성공하면 입력 칸을 비운다. 같은 값을 두 번 등록하는 실수를
            # 막고, 다음 등록이 남은 값을 물려받지 않게 한다.
            self._register_inputs["title"].clear()
            self._register_inputs["base_url"].clear()
            self._register_inputs["params"].clear()
            for name, _label in REGISTER_ADVANCED_FIELDS:
                self._register_inputs[name].clear()
        self.refresh_registration(force=True)
        return ok

    def delete_registered(self, record_id):
        """등록 레코드 하나를 지운다(편집은 삭제 후 재등록이다).

        Returns:
            bool: 삭제 성공 여부.
        """
        ok, why = userregistry.delete_record(record_id,
                                             path=self._registry_file or None)
        self._message.setText(REGISTER_MESSAGE_FMT % why)
        self.refresh_registration(force=True)
        return ok

    def refresh_registration(self, force=False):
        """등록 목록 표를 다시 그린다.

        패널이 아직 보인 적이 없고 `force` 도 아니면 **파일을 읽지 않는다**.
        등록 섹션은 접혀 있고 패널 자체가 숨어 있는 동안 목록을 그릴 이유가
        없다(구성 시점에 프로필을 만지지 않는다).

        Args:
            force: 지금 읽을 것인가. 등록/삭제 동작과 첫 표시가 참을 준다.

        Returns:
            int: 등록된 레코드 수. 아직 읽지 않았으면 마지막으로 읽은 수다.
        """
        if not (force or self._registry_loaded):
            return len(self._register_rows)
        self._registry_loaded = True
        for widget in self._register_row_widgets:
            self._register_list_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self._register_row_widgets = []

        rows, why = userregistry.load_records(self._registry_file or None)
        self._register_rows = tuple(
            {"id": str(r.get("id") or ""),
             "title": str(r.get("title") or ""),
             "provider": str(r.get("provider") or ""),
             "verified": bool(r.get("verified"))} for r in rows)
        if not self._register_rows:
            empty = self._wrap_label(REGISTER_EMPTY, self._register_list,
                                     theme_mod.ROLE_MUTED)
            self._register_list_layout.addWidget(empty, 0, 0, 1, 4)
            self._register_row_widgets.append(empty)
            return 0
        for i, rec in enumerate(self._register_rows):
            name = self._wrap_label(rec["title"] or rec["id"],
                                    self._register_list, theme_mod.ROLE_MUTED)
            name.setToolTip(rec["id"])
            self._register_list_layout.addWidget(name, i, 0)
            provider = self._wrap_label(rec["provider"], self._register_list,
                                        theme_mod.ROLE_MUTED)
            self._register_list_layout.addWidget(provider, i, 1)
            verified = self._wrap_label(
                REGISTER_VERIFIED_YES if rec["verified"]
                else REGISTER_VERIFIED_NO,
                self._register_list, theme_mod.ROLE_MUTED)
            self._register_list_layout.addWidget(verified, i, 2)
            drop = QPushButton(REGISTER_DELETE_TEXT, self._register_list)
            drop.setObjectName("UpwiseChatRegisterDelete_%d" % i)
            drop.setMinimumWidth(BAR_BUTTON_MIN_W)
            # clicked 는 bool 을 넘긴다. 기본값 인자로 삼킨다(S4 실측).
            drop.clicked.connect(
                lambda _checked=False, rid=rec["id"]:
                self.delete_registered(rid))
            self._register_list_layout.addWidget(drop, i, 3)
            self._register_row_widgets.extend([name, provider, verified, drop])
        if why not in ("ok", "absent"):
            self._message.setText(REGISTER_MESSAGE_FMT % why)
        return len(self._register_rows)

    def refresh(self):
        """설정에서 지금 상태를 읽어 상태 문구를 다시 그린다.

        Returns:
            int: 키가 설정된 제공자 수(required 칸이 전부 찬 제공자).
        """
        configured = 0
        for pid, row in self._rows.items():
            if not row["meta"].get("needs_key", True):
                row["state"].setText(STATE_NOT_NEEDED)
                row["delete"].setEnabled(False)
                continue
            state = keystore.provider_state(row["meta"],
                                            settings=self._settings)
            if state["configured"]:
                configured += 1
                row["state"].setText(STATE_SET % self._mask_text(row))
            elif state["any"]:
                # 부분 입력. 빠진 칸 **이름**만 적는다(설계 docs/8 5-1).
                row["state"].setText(
                    STATE_PARTIAL % ", ".join(state["missing_labels"]))
            else:
                row["state"].setText(STATE_UNSET)
            row["delete"].setEnabled(bool(state["any"]))
        override = keystore.read_endpoint_override(settings=self._settings)
        self._url_state.setText(ADVANCED_SET % override if override
                                else ADVANCED_UNSET)
        self._url_delete.setEnabled(bool(override))
        self.refresh_registration()
        return configured

    def showEvent(self, event):  # noqa: N802 - Qt API 이름
        """패널이 처음 보일 때 등록 목록을 읽는다.

        구성 시점에 읽지 않는 이유는 `refresh_registration` docstring 에 있다.
        독은 패널을 숨긴 채로 만들고 사용자가 머리글을 누를 때 보인다.
        """
        super(KeyPanel, self).showEvent(event)
        if not self._registry_loaded:
            self.refresh_registration(force=True)

    def _mask_text(self, row):
        """제공자 한 행의 마스킹 표시. 값의 글자를 하나도 내보내지 않는다."""
        parts = []
        for name in row["order"]:
            cell = row["cells"][name]
            value = keystore.read_value(cell["meta"]["setting"],
                                        settings=self._settings)
            shown = keystore.mask(value)
            label = cell["meta"].get("label") or ""
            parts.append(STATE_FIELD_FMT % (label, shown) if label else shown)
        return ", ".join(p for p in parts if p)

    def _emit_changed(self):
        """설정된 제공자 수를 실어 올린다. 키 값은 담지 않는다."""
        configured, _missing = keystore.key_state(self._providers,
                                                  settings=self._settings)
        self.keys_changed.emit(len(configured))

    # ------------------------------------------------------------------
    # 조회 (검증 하네스가 읽는다)
    # ------------------------------------------------------------------

    def providers(self):
        """패널이 띄운 제공자 id 들."""
        return tuple(row["id"] for row in self._providers)

    def provider_field_names(self, provider):
        """제공자 하나의 칸 이름들. 단일 필드 제공자는 ("",) 다."""
        row = self._rows.get(provider)
        return row["order"] if row else ()

    def field(self, provider, name=None):
        """제공자 입력 칸. 하네스가 키를 넣는다.

        Args:
            provider: 제공자 id.
            name: 칸 이름. None 이면 첫 칸이다(단일 필드 제공자 호환).

        Returns:
            QLineEdit 또는 None.
        """
        row = self._rows.get(provider)
        if not row:
            return None
        key = row["order"][0] if name is None else name
        cell = row["cells"].get(key)
        return cell["field"] if cell else None

    def field_tooltip(self, provider):
        """제공자 행 제목의 툴팁 전문. 함정 문구가 여기 있다."""
        row = self._rows.get(provider)
        return self._row_tooltip(row["meta"]) if row else ""

    def state_text(self, provider):
        """제공자 행의 상태 문구."""
        row = self._rows.get(provider)
        return row["state"].text() if row else ""

    def message_text(self):
        """마지막 동작 결과 한 줄."""
        return self._message.text()

    def notice_text(self):
        """저장 위치/평문 안내 한 줄."""
        return self._notice.text()

    def warning_text(self):
        """채팅 붙여넣기 금지 한 줄."""
        return self._warning.text()

    def advanced_expanded(self):
        """고급 칸이 펴져 있는가. 기본은 접힘이다."""
        return self._advanced.is_expanded()

    def endpoint_state_text(self):
        """고급 칸의 상태 문구."""
        return self._url_state.text()

    def registration_expanded(self):
        """등록 섹션이 펴져 있는가. 기본은 접힘이다(설계 5-2)."""
        return self._register.is_expanded()

    def registration_advanced_expanded(self):
        """등록 섹션 안의 봉투 고급 칸이 펴져 있는가. 기본은 접힘이다."""
        return self._register_advanced.is_expanded()

    def register_notice_texts(self):
        """등록 섹션에 실제로 그려진 안내 2줄(승인, 한도)."""
        return (self._register_notice_approval.text(),
                self._register_notice_quota.text())

    def register_input(self, name):
        """등록 섹션의 입력 위젯 하나. 하네스가 값을 넣는다."""
        return self._register_inputs.get(name)

    def preset_labels(self):
        """프리셋 콤보의 항목 문구들."""
        return tuple(self._register_preset.itemText(i)
                     for i in range(self._register_preset.count()))

    def preset_names(self):
        """읽어 들인 프리셋의 이름들. 정의가 없으면 빈 튜플이다."""
        return tuple(str(p.get("name") or "") for p in self._presets)

    def registered_rows(self):
        """등록 목록 표의 행들(이름·제공자·검증여부)."""
        return self._register_rows

    def registry_file(self):
        """등록 레코드 파일 경로."""
        return self._registry_file or userregistry.default_path()

    def stats(self):
        """패널 상태 요약. **키 값이 들어가지 않는다.**

        0.5.0: 키 이름은 유지하고 값만 늘렸다(설계 docs/8 5-1).
        `key_panel_echo_modes` 의 키는 다필드 제공자에서 `<pid>__<field>` 가
        된다 - 단일 제공자 키는 종전 그대로다.
        """
        echo_modes = {}
        for pid, row in self._rows.items():
            for name in row["order"]:
                label = pid + ("__" + name if name else "")
                echo_modes[label] = int(row["cells"][name]["field"].echoMode())
        return {
            "key_panel_visible": not self.isHidden(),
            "key_panel_providers": list(self.providers()),
            "key_panel_states": {pid: self.state_text(pid)
                                 for pid in self._rows},
            "key_panel_echo_modes": echo_modes,
            "key_panel_field_texts_empty": all(
                not row["cells"][name]["field"].text()
                for row in self._rows.values() for name in row["order"]),
            "key_panel_message": self.message_text(),
            "key_panel_advanced_expanded": self.advanced_expanded(),
            "key_panel_endpoint_state": self.endpoint_state_text(),
            "key_panel_register_expanded": self.registration_expanded(),
            "key_panel_register_adv_expanded":
                self.registration_advanced_expanded(),
            "key_panel_register_presets": list(self.preset_names()),
            "key_panel_register_rows": [dict(r) for r in self._register_rows],
        }
