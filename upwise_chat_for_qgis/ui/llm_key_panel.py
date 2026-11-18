"""비모달 LLM 키/모델/base URL 패널 (docs/13 5-5).

왜 `key_panel.KeyPanel` 을 확장하지 않는가
    그 패널은 행 구성을 `keystore.load_providers()` 에서 받고, 그것은 수집
    카탈로그 3파일을 읽는다. LLM 제공자를 그 패널에 넣으려면 **수집
    카탈로그에 데이터셋 없는 가짜 제공자를 넣어야** 하고, 같은 파일을
    `collect_server` 도 읽는다(`keystore.CATALOG_SIBLINGS` 주석이 "서버가
    같은 순서로 같은 파일을 읽는다" 를 못박았다). 수집 서버가 데이터셋
    0개인 제공자를 어떻게 읽는지는 미측이고, 그 위험을 UI 편의로 사는 것은
    교환비가 나쁘다. 그래서 **별 패널**이다.

패턴은 그대로 가져간다(의도적 동형)
    QFrame + 비모달 + 독 안의 접히는 영역, `keys_changed(int)` 시그널,
    저장값을 **자릿수만** 마스킹 표시(`keystore.mask`), 저장 전 검증 ->
    사유 1줄(값 미포함), 저장 직후 `sync()`(keystore 가 한다).

키 값을 다루는 규칙 (`key_panel` 과 같다)
    * 입력 위젯은 `QLineEdit.Password` 다. 화면에 글자가 남지 않는다.
    * **저장 성공 즉시 입력 칸을 비운다.** 패널이 화면 공유나 캡처에 들어갈
      수 있고, 위젯에 남은 값은 지울 이유가 없는 사본이다.
    * 밖으로 내는 시그널 인자는 **설정된 제공자 수**다. 값이 아니다.

base URL 옆 고지 1줄
    입력한 주소로 **키가 전송된다.** 사용자가 임의 호스트를 적을 수 있는
    필드이므로 그 사실을 필드 옆에 상시 적는다. 기능 제한이 아니라 고지다.

[키 확인] 이 0토큰인 이유
    `GET /v1/models` 는 토큰을 쓰지 않고 401/200 을 준다. 사용자가 **과금
    없이** 키와 주소와 연결을 확인할 수 있다 - Claude 모드의 [연결 점검] 이
    모델 턴을 쓰지 않는 것과 같은 설계 축이다. 소켓 연산은 아래
    `_KeyProbeThread` **안에서만** 일어난다(docs/13 I-4).

금지 API(설계 3-5): QMessageBox, QDialog.exec(), QProgressDialog,
QFileDialog, 중첩 이벤트 루프. Qt import 는 전부 qgis.PyQt 셰임 경로로 한다.

설계 정본: docs/13.api_key_backend_design_v1.md 3-2, 3-4, 5-5
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..backend import adapter_registry, apiclient, keystore, llmkeys
from . import theme as theme_mod
from .approval_bar import BAR_BUTTON_MIN_W

# 패널 머리말과 안내.
PANEL_HEADER = "LLM API 키"

STORAGE_NOTICE = (
    "키는 QGIS 설정 파일(QGIS3.ini)에 평문으로 저장됩니다. 이 컴퓨터를 "
    "함께 쓰는 사람이 있으면 그 사실을 염두에 두세요."
)

# base URL 전송 고지(docs/13 3-2). 기능 제한이 아니라 고지다.
BASE_URL_NOTICE = (
    "여기 적은 주소로 API 키가 전송됩니다. 믿을 수 있는 주소만 넣으세요."
)

# 붙여넣기 경고. 수집 패널과 같은 축의 문면이다.
PASTE_WARNING = (
    "채팅 입력창에 키를 붙여 넣지 마세요. 입력창에 넣은 값은 모델에게 "
    "그대로 전달됩니다."
)

# 백엔드 선택 적용 시점. 모델 선택과 같은 규약이다(다음 스폰부터 적용).
BACKEND_NOTICE = "백엔드 선택은 [새 대화] 부터 적용됩니다."

BACKEND_SECTION = "백엔드"
BACKEND_LABEL_CLAUDE = "Claude Code CLI (지도 제어 가능)"

# 상태 문구.
STATE_SET = "저장됨 %s"
STATE_UNSET = "키가 설정되지 않았습니다"
STATE_OPTIONAL = "키 없이 쓸 수 있습니다(로컬 서버)"
STATE_MODEL = "모델 %s"
STATE_MODEL_UNSET = "모델명을 넣으세요"
STATE_BASE_URL = "base URL %s"
STATE_MAX_TOKENS = "토큰 상한 %d"
STATE_READY = "보낼 준비가 됐습니다"
STATE_NOT_READY = "아직 보낼 수 없습니다: %s"

# 칸 라벨과 자리표시.
KEY_PLACEHOLDER = "키를 붙여 넣고 [저장] 을 누르세요"
MODEL_PLACEHOLDER = "예: %s"
URL_PLACEHOLDER = "https://..."
TOKENS_PLACEHOLDER = "예: %d"

SAVE_TEXT = "저장"
DELETE_TEXT = "지우기"
PROBE_TEXT = "키 확인"

# [키 확인] 결과 문구. 0토큰이라는 사실을 함께 적는다.
PROBE_RUNNING = "키를 확인하는 중입니다(토큰을 쓰지 않습니다)."
PROBE_OK = "키가 받아들여졌습니다(HTTP %s). 토큰을 쓰지 않았습니다."
PROBE_BUSY = "이미 확인 중입니다."
PROBE_NEED_KEY = "확인할 키가 없습니다."

#: 패널 제목 접두. 메시지 한 줄에 어느 제공자인지 적는다.
MESSAGE_FMT = "%s: %s"


class _KeyProbeThread(QThread):
    """[키 확인] 1회를 UI 스레드 밖에서 돈다 (docs/13 I-4).

    **이 클래스가 패널에서 소켓을 만지는 유일한 자리다.** `urlopen` 은
    블로킹이고 UI 스레드에서 부르면 독이 그 시간 동안 얼어붙는다.
    하네스 110 A7 이 소스를 tokenize 해서 이 성질을 판정한다.

    보내는 요청은 `GET /v1/models` 하나이고 **모델 턴을 쓰지 않는다.**
    """

    done = pyqtSignal(str, str)

    def __init__(self, provider, material, parent=None):
        """제공자와 요청 재료를 받아 둔다.

        Args:
            provider: 제공자 이름. 결과 시그널에 그대로 실린다.
            material: `(url, headers, None)` 3-튜플.
            parent: QObject 부모.
        """
        super().__init__(parent)
        self._provider = str(provider)
        self._material = material

    def run(self):
        """요청 1회를 돌고 사용자 대면 한 줄을 시그널로 올린다."""
        url, headers, body = self._material
        resp = None
        try:
            resp = apiclient.open_stream(url, headers, body, method="GET")
            status = getattr(resp, "status", None)
            if status is None:
                status = getattr(resp, "code", 200)
            message = PROBE_OK % status
        except apiclient.ApiHttpError as exc:
            message = apiclient.http_notice(exc)
        except apiclient.ApiTransportError as exc:
            message = apiclient.transport_notice(exc)
        except Exception as exc:  # noqa: BLE001 - 확인 실패가 패널을 깨지 않는다
            message = apiclient.NOTICE_TRANSPORT % (
                "%s: %s" % (type(exc).__name__, exc))
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:  # noqa: BLE001 - 닫기 실패는 사유가 아니다
                    pass
        self.done.emit(self._provider, message)


class LlmKeyPanel(QFrame):
    """LLM 백엔드 선택과 제공자별 키/모델/base URL 을 넣는 비모달 패널.

    시그널 하나만 낸다.

        keys_changed(int)  저장/삭제가 성공했다. 인자는 **키가 설정된
            제공자 수**다. 키 값은 시그널에도 담지 않는다.
    """

    keys_changed = pyqtSignal(int)

    def __init__(self, parent=None, settings=None):
        """행을 만들고 현재 상태를 읽어 그린다. 기본은 숨은 상태다.

        Args:
            parent: 부모 위젯.
            settings: QSettings 호환 객체. None 이면 QgsSettings. 하네스가
                임시 INI 로 실제 Qt 저장과 sync 를 재게 하는 주입점이다.
        """
        super().__init__(parent)
        self.setObjectName("UpwiseChatLlmKeyPanel")
        # qss 가 면과 테두리를 그린다. StyledPanel 과 겹치면 액자가 두 겹이다.
        self.setFrameShape(QFrame.NoFrame)
        self._settings = settings
        self._rows = {}
        self._backend_buttons = {}
        self._probe = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        head = QLabel(PANEL_HEADER, self)
        head.setObjectName("UpwiseChatLlmKeyPanelHeader")
        theme_mod.set_role(head, theme_mod.ROLE_CAPTION)
        layout.addWidget(head)

        layout.addWidget(self._wrap_label(STORAGE_NOTICE, self))
        layout.addWidget(self._wrap_label(PASTE_WARNING, self))
        layout.addWidget(self._build_backend_choice())
        layout.addWidget(self._build_rows())

        # 마지막 동작의 결과 한 줄. 모달을 쓸 수 없으므로 결과를 여기 적는다.
        self._message = QLabel("", self)
        self._message.setObjectName("UpwiseChatLlmKeyPanelMessage")
        self._message.setWordWrap(True)
        self._message.setMinimumWidth(1)
        layout.addWidget(self._message)

        self.refresh()
        self.setVisible(False)

    # ------------------------------------------------------------------
    # 위젯 구성
    # ------------------------------------------------------------------

    def _wrap_label(self, text, parent, role=None):
        """줄바꿈 라벨 하나. 최소 폭을 1 로 둔다.

        줄바꿈 라벨의 기본 최소 폭은 한 줄 전체라서 독의 최소 폭을 밀어
        올린다(README 5 실측). 그래서 모든 안내와 라벨이 이 창구를 지난다.
        """
        label = QLabel(text, parent)
        label.setWordWrap(True)
        label.setMinimumWidth(1)
        theme_mod.set_role(label,
                           theme_mod.ROLE_MUTED if role is None else role)
        return label

    def _build_backend_choice(self):
        """백엔드 라디오 3개. 저장은 즉시, 적용은 다음 새 대화부터다."""
        holder = QWidget(self)
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)
        caption = self._wrap_label(BACKEND_SECTION, holder,
                                   theme_mod.ROLE_CAPTION)
        box.addWidget(caption)
        rows = ((llmkeys.BACKEND_CLAUDE, BACKEND_LABEL_CLAUDE),
                (llmkeys.PROVIDER_ANTHROPIC, ""),
                (llmkeys.PROVIDER_OPENAI, ""))
        for name, label in rows:
            text = label or adapter_registry.get(name).display_name
            button = QRadioButton(text, holder)
            button.setObjectName("UpwiseChatLlmBackend_" + name)
            button.toggled.connect(
                lambda checked, name=name: self._on_backend_toggled(
                    name, checked))
            box.addWidget(button)
            self._backend_buttons[name] = button
        box.addWidget(self._wrap_label(BACKEND_NOTICE, holder))
        return holder

    def _build_rows(self):
        """제공자 행들. 그리드로 두어 라벨/칸/버튼이 세로로 맞는다.

        제공자 하나가 쓰는 줄 구성은 `key_panel` 과 같은 축이다 - 제목 1줄,
        칸마다 라벨 1줄 + 입력 1줄, 버튼은 키 줄에만, 상태 문구 1줄.
        OpenAI 호환만 base URL 줄이 더 붙는다.
        """
        holder = QWidget(self)
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        top = 0
        for provider in llmkeys.PROVIDERS:
            adapter = adapter_registry.get(provider)
            title = self._wrap_label(adapter.display_name, holder,
                                     theme_mod.ROLE_CAPTION)
            grid.addWidget(title, top, 0, 1, 3)
            top += 1
            row = {}

            field = llmkeys.key_field(provider)
            grid.addWidget(self._wrap_label(field["label"], holder), top, 0,
                           1, 3)
            top += 1
            row["key"] = self._password_field(holder, provider)
            grid.addWidget(row["key"], top, 0)
            row["save"] = self._button(holder, SAVE_TEXT,
                                       "UpwiseChatLlmKeySave_" + provider,
                                       lambda p=provider: self.save_key(p))
            grid.addWidget(row["save"], top, 1)
            row["delete"] = self._button(
                holder, DELETE_TEXT, "UpwiseChatLlmKeyDelete_" + provider,
                lambda p=provider: self.delete_key(p))
            grid.addWidget(row["delete"], top, 2)
            top += 1

            model_field = llmkeys.model_field(provider)
            grid.addWidget(self._wrap_label(model_field["label"], holder),
                           top, 0, 1, 3)
            top += 1
            row["model"] = QLineEdit(holder)
            row["model"].setObjectName("UpwiseChatLlmModel_" + provider)
            row["model"].setPlaceholderText(
                MODEL_PLACEHOLDER % (llmkeys.MODEL_DEFAULT_ANTHROPIC
                                     if provider
                                     == llmkeys.PROVIDER_ANTHROPIC
                                     else "gpt-5"))
            row["model"].returnPressed.connect(
                lambda p=provider: self.save_model(p))
            grid.addWidget(row["model"], top, 0)
            row["model_save"] = self._button(
                holder, SAVE_TEXT, "UpwiseChatLlmModelSave_" + provider,
                lambda p=provider: self.save_model(p))
            grid.addWidget(row["model_save"], top, 1)
            row["probe"] = self._button(
                holder, PROBE_TEXT, "UpwiseChatLlmProbe_" + provider,
                lambda p=provider: self.probe_key(p))
            grid.addWidget(row["probe"], top, 2)
            top += 1

            if provider == llmkeys.PROVIDER_OPENAI:
                grid.addWidget(self._wrap_label("base URL", holder), top, 0,
                               1, 3)
                top += 1
                row["base_url"] = QLineEdit(holder)
                row["base_url"].setObjectName("UpwiseChatLlmBaseUrl")
                row["base_url"].setPlaceholderText(URL_PLACEHOLDER)
                row["base_url"].returnPressed.connect(self.save_base_url)
                grid.addWidget(row["base_url"], top, 0)
                row["base_url_save"] = self._button(
                    holder, SAVE_TEXT, "UpwiseChatLlmBaseUrlSave",
                    self.save_base_url)
                grid.addWidget(row["base_url_save"], top, 1)
                top += 1
                grid.addWidget(self._wrap_label(BASE_URL_NOTICE, holder),
                               top, 0, 1, 3)
                top += 1
            else:
                grid.addWidget(self._wrap_label(
                    llmkeys.max_tokens_field()["label"], holder), top, 0, 1, 3)
                top += 1
                row["max_tokens"] = QLineEdit(holder)
                row["max_tokens"].setObjectName("UpwiseChatLlmMaxTokens")
                row["max_tokens"].setPlaceholderText(
                    TOKENS_PLACEHOLDER % llmkeys.MAX_TOKENS_DEFAULT)
                row["max_tokens"].returnPressed.connect(self.save_max_tokens)
                grid.addWidget(row["max_tokens"], top, 0)
                row["max_tokens_save"] = self._button(
                    holder, SAVE_TEXT, "UpwiseChatLlmMaxTokensSave",
                    self.save_max_tokens)
                grid.addWidget(row["max_tokens_save"], top, 1)
                top += 1

            state = QLabel("", holder)
            state.setObjectName("UpwiseChatLlmKeyState_" + provider)
            state.setWordWrap(True)
            state.setMinimumWidth(1)
            theme_mod.set_role(state, theme_mod.ROLE_MUTED)
            grid.addWidget(state, top, 0, 1, 3)
            top += 1
            row["state"] = state
            self._rows[provider] = row
        grid.setColumnStretch(0, 1)
        return holder

    def _password_field(self, parent, provider):
        """키 입력 칸 하나. 입력 중에도 글자가 화면에 남지 않는다."""
        edit = QLineEdit(parent)
        edit.setObjectName("UpwiseChatLlmKeyField_" + provider)
        edit.setEchoMode(QLineEdit.Password)
        edit.setPlaceholderText(KEY_PLACEHOLDER)
        edit.setToolTip(llmkeys.key_field(provider)["setting"])
        edit.returnPressed.connect(lambda p=provider: self.save_key(p))
        return edit

    def _button(self, parent, text, name, slot):
        """패널 버튼 하나. `clicked` 의 bool 을 기본값 인자로 삼킨다."""
        button = QPushButton(text, parent)
        button.setObjectName(name)
        button.setMinimumWidth(BAR_BUTTON_MIN_W)
        button.clicked.connect(lambda _checked=False: slot())
        return button

    # ------------------------------------------------------------------
    # 동작
    # ------------------------------------------------------------------

    def _on_backend_toggled(self, name, checked):
        """라디오가 켜졌다. 설정에 적고 적용 시점을 알린다.

        Args:
            name: 백엔드 이름.
            checked: 켜졌는가. 꺼지는 쪽 신호는 버린다.

        Returns:
            bool: 저장했는가.
        """
        if not checked:
            return False
        ok, why = llmkeys.save_backend_name(name, settings=self._settings)
        self._message.setText(MESSAGE_FMT % (BACKEND_SECTION, why))
        if ok:
            self._emit_changed()
        return ok

    def save_key(self, provider):
        """한 제공자의 키를 저장한다. 성공하면 칸을 비운다.

        Returns:
            bool: 저장 성공 여부.
        """
        row = self._rows.get(provider)
        if row is None:
            return False
        ok, why = llmkeys.save_key(provider, row["key"].text(),
                                   settings=self._settings)
        if ok:
            # 위젯에 값을 남기지 않는다. 지울 이유가 없는 사본이다.
            row["key"].clear()
        self._message.setText(MESSAGE_FMT % (provider, why))
        self.refresh()
        if ok:
            self._emit_changed()
        return ok

    def delete_key(self, provider):
        """한 제공자의 키를 지운다.

        Returns:
            bool: 삭제 성공 여부.
        """
        row = self._rows.get(provider)
        if row is None:
            return False
        ok, why = llmkeys.delete_key(provider, settings=self._settings)
        row["key"].clear()
        self._message.setText(MESSAGE_FMT % (provider, why))
        self.refresh()
        if ok:
            self._emit_changed()
        return ok

    def save_model(self, provider):
        """한 제공자의 모델명을 저장한다.

        Returns:
            bool: 저장 성공 여부.
        """
        row = self._rows.get(provider)
        if row is None:
            return False
        ok, why = llmkeys.save_model(provider, row["model"].text(),
                                     settings=self._settings)
        self._message.setText(MESSAGE_FMT % (provider, why))
        self.refresh()
        if ok:
            self._emit_changed()
        return ok

    def save_base_url(self):
        """OpenAI 호환 base URL 을 저장한다.

        Returns:
            bool: 저장 성공 여부.
        """
        row = self._rows.get(llmkeys.PROVIDER_OPENAI)
        if row is None or "base_url" not in row:
            return False
        ok, why = llmkeys.save_base_url(row["base_url"].text(),
                                        settings=self._settings)
        self._message.setText(MESSAGE_FMT % ("base URL", why))
        self.refresh()
        if ok:
            self._emit_changed()
        return ok

    def save_max_tokens(self):
        """Anthropic 토큰 상한을 저장한다.

        Returns:
            bool: 저장 성공 여부.
        """
        row = self._rows.get(llmkeys.PROVIDER_ANTHROPIC)
        if row is None or "max_tokens" not in row:
            return False
        ok, why = llmkeys.save_max_tokens(row["max_tokens"].text(),
                                          settings=self._settings)
        self._message.setText(MESSAGE_FMT % ("토큰 상한", why))
        self.refresh()
        if ok:
            self._emit_changed()
        return ok

    def probe_key(self, provider):
        """0토큰 키 점검 1회. 결과는 메시지 줄에 적는다.

        한 번에 하나만 돈다 - 둘을 동시에 띄우면 결과 줄이 섞이고, 어느
        제공자의 답인지 사용자가 가를 수 없다.

        Returns:
            bool: 요청을 띄웠는가.
        """
        if self._probe is not None and self._probe.isRunning():
            self._message.setText(MESSAGE_FMT % (provider, PROBE_BUSY))
            return False
        adapter = adapter_registry.get(provider)
        material = adapter.probe_material(settings=self._settings)
        if provider == llmkeys.PROVIDER_ANTHROPIC and not llmkeys.key_present(
                provider, settings=self._settings):
            # 키 없이 보내면 401 이 올 것이 뻔하다. 요청을 아끼고 사유를
            # 그 자리에 적는다.
            self._message.setText(MESSAGE_FMT % (provider, PROBE_NEED_KEY))
            return False
        self._message.setText(MESSAGE_FMT % (provider, PROBE_RUNNING))
        self._probe = _KeyProbeThread(provider, material, self)
        self._probe.done.connect(self._on_probe_done)
        self._probe.start()
        return True

    def _on_probe_done(self, provider, message):
        """점검 결과 한 줄. **키 값이 들어가지 않는다.**"""
        self._message.setText(MESSAGE_FMT % (provider, message))
        probe = self._probe
        self._probe = None
        if probe is not None:
            probe.deleteLater()

    # ------------------------------------------------------------------
    # 표시 갱신
    # ------------------------------------------------------------------

    def refresh(self):
        """저장된 상태를 다시 읽어 라디오와 상태 문구를 맞춘다.

        키는 **마스킹 표시**로만 그린다(`keystore.mask`). 자릿수는 화면에만
        쓰고 로그에는 쓰지 않는다(docs/13 3-3 H-3).

        Returns:
            dict: 하네스가 읽는 요약(값 없음).
        """
        name = llmkeys.read_backend_name(settings=self._settings) \
            or llmkeys.BACKEND_CLAUDE
        for key, button in self._backend_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(key == name)
            button.blockSignals(blocked)
        for provider, row in self._rows.items():
            value = llmkeys.read_key(provider, settings=self._settings)
            parts = []
            if value:
                parts.append(STATE_SET % keystore.mask(value))
            elif provider == llmkeys.PROVIDER_OPENAI:
                parts.append(STATE_OPTIONAL)
            else:
                parts.append(STATE_UNSET)
            model = llmkeys.read_model(provider, settings=self._settings)
            parts.append(STATE_MODEL % model if model else STATE_MODEL_UNSET)
            if provider == llmkeys.PROVIDER_OPENAI:
                parts.append(STATE_BASE_URL
                             % llmkeys.read_base_url(settings=self._settings))
            else:
                parts.append(STATE_MAX_TOKENS
                             % llmkeys.read_max_tokens(
                                 settings=self._settings))
            ready, why = llmkeys.is_configured(provider,
                                               settings=self._settings)
            parts.append(STATE_READY if ready else STATE_NOT_READY % why)
            row["state"].setText(" . ".join(parts))
        return self.stats()

    def _emit_changed(self):
        """설정된 제공자 수를 올린다. 키 값은 담지 않는다."""
        count = sum(1 for provider in llmkeys.PROVIDERS
                    if llmkeys.key_present(provider, settings=self._settings))
        self.keys_changed.emit(count)
        return count

    def stats(self):
        """하네스가 읽는 요약. **값도 자릿수도 들어가지 않는다.**

        Returns:
            dict
        """
        return {
            "llm_panel_visible": not self.isHidden(),
            "llm_backend": llmkeys.read_backend_name(
                settings=self._settings),
            "llm_rows": len(self._rows),
            "llm_keys_set": [
                provider for provider in llmkeys.PROVIDERS
                if llmkeys.key_present(provider, settings=self._settings)],
            "llm_message": self._message.text(),
        }

    def showEvent(self, event):  # noqa: N802 - Qt API 이름
        """패널이 보일 때 상태를 다시 읽는다. 저장은 다른 창구로도 바뀐다."""
        super().showEvent(event)
        self.refresh()
