"""공공 API 키 저장소 (0.5.0, 설계 docs/2 5-2, 5-3 + docs/8 5-1).

이 모듈만 키 **값**을 만진다
    키를 읽고 쓰는 창구를 하나로 묶는다. UI 는 이 모듈을 통해서만 값을
    만지고, 진단 로그와 요약에는 `summary()` 가 돌려주는 **불리언**만 나간다.
    값이 두 군데서 다뤄지면 한쪽이 언젠가 로그에 찍힌다.

저장 위치: `QgsSettings`(QGIS3.ini). 설계 5-2 의 결정이다
    사본이 하나뿐이고 플러그인 설정의 표준 자리다. **평문**이라는 한계는
    설정 패널의 안내 한 줄과 이 docstring 에 적는다. 암호화 저장
    (`QgsAuthManager`)은 0.2.x 후보다 - 마스터 비밀번호 프롬프트가 모달일
    위험이 있고(모달 금지), 자식 프로세스가 복호화해 읽을 수 없다.

    cwd 의 평문 파일(`.env`)은 **금지**다. 0.1.4 가 내장 읽기 3종을
    사전승인했으므로 cwd 의 파일은 모델이 `Read` 로 읽을 수 있다(S9a M-5
    실측). cwd 에 키를 두는 것은 키를 모델에 주는 것과 같다.

다필드 키 (0.5.0, 설계 docs/8 5-1)
    제공자 하나가 값 둘을 요구할 수 있다 - SGIS 는 `service_id` +
    `security_key` 가 둘 다 있어야 토큰이 나온다. 그래서 제공자 정의에
    `fields` 배열을 둔다. `fields` 가 없는 제공자는 **지금처럼**
    `upwise_chat/keys/<provider>` 한 칸으로 동작한다(V-World 가 그것이다).
    제공자 판정은 **required 필드 전부 채워졌을 때만** configured 이고,
    부분 입력은 missing 이다. 사유에는 빠진 필드 **이름**만 적고 값은 적지
    않는다.

카탈로그 파일 (0.5.0, 설계 docs/8 4-1)
    제공자 정의는 동봉 파일 셋(레지스트리 + 스냅샷 2개)에 흩어져 있고
    서버가 **같은 순서로 병합**해 읽는다(`collect_server.load_catalog`,
    먼저 등재한 정의가 이긴다). 이 모듈도 같은 순서로 같은 파일들을 읽는다.
    한쪽만 읽으면 "서버는 아는 제공자인데 키 패널에는 칸이 없는" 상태가
    되고, 그 상태가 바로 0.4.2 의 SGIS 였다.

전달: 서버가 INI 를 직접 읽는다(K6). 플러그인은 경로와 접두사만 넘긴다
    그래서 **저장 직후 `sync()` 를 반드시 부른다**(설계 5-3 단서 2).
    `QgsSettings` 는 메모리에 캐시하므로 sync 없이는 파일에 값이 없고,
    서버가 빈 값을 읽어 "키가 설정되지 않았습니다" 로 끝난다.

형식 검사
    `KEY_RE` 는 `collect_server.KEY_RE` 와 같은 식이다. 서버가 받아들이지
    않는 값을 저장해 두면 "저장은 됐는데 수집이 안 되는" 상태가 된다.
    그래서 저장 시점에 거절하고 허용 문자를 사유에 적는다. 추측하지 않는다
    (설계 5-3 단서 1).

설계 정본: docs/2.collect_feature_design_v1.md 4-2, 5-2, 5-3 /
docs/8.collect_expansion_design_v1.md 4-1, 5-1
"""

import json
import os
import re

from . import posture

# 키를 담는 QgsSettings 경로 접두사. posture 가 정본이고(서버에 넘기는 env 와
# 같은 값이어야 한다) 여기서 다시 적지 않는다.
KEY_PREFIX = posture.COLLECT_KEY_PREFIX

# 엔드포인트 기본 URL 오버라이드(고급). `collect_server.SETTING_ENDPOINT_OVERRIDE`
# 와 같은 경로다. 서버는 이 값이 있으면 레지스트리의 base_url 대신 쓴다.
ENDPOINT_OVERRIDE_KEY = "upwise_chat/collect/endpoint_override"

# 레지스트리 JSON 파일명. 패키지 폴더 안에 있고 서버도 같은 파일을 읽는다.
REGISTRY_FILENAME = "collect_registry.json"

# 동봉 카탈로그 형제 파일. **`collect_server.CATALOG_SIBLINGS` 와 같은
# 순서, 같은 이름이어야 한다**(하네스 24 A11 이 일치를 판정한다). 서버는
# `-I` 단일 파일이라 import 할 수 없어 중복이 불가피하다 - A6/A7 과 같은
# 이유, 같은 처방이다.
CATALOG_SIBLINGS = ("collect_catalog_vworld.json", "collect_catalog_sgis.json",
                    "collect_catalog_datago.json")

# 등록 프리셋 블록 이름(설계 docs/8 3-5 "프리셋 2종"). 카탈로그 파일의
# **최상위** 목록이고 항목마다 `preset_id`·`title`·`record` 를 갖는다.
# 프리셋 **정의는 서버측 카탈로그 소관**이고 이 모듈은 읽기만 한다. 블록이
# 없는 파일에서는 아무것도 올리지 않는다 - 하드코딩 사본을 만들면 두 곳이
# 어긋난다.
PRESET_BLOCK = "presets"
PRESET_ID_FIELD = "preset_id"
PRESET_LABEL_FIELD = "title"

# 형식 검사식. collect_server.KEY_RE 와 **같은 식이어야 한다**(하네스 판정).
# **이 식을 넓히지 않는다.** 넓히면 V-World·SGIS 가 받아들이는 집합까지 함께
# 넓어져 오타 방어가 사라진다(설계 docs/8 3-5). 더 넓은 문자집합이 필요한
# 제공자는 카탈로그에 `key_re` 를 선언한다.
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

# 제공자별 키 검증 선언(설계 docs/8 3-5). 카탈로그가 말하는 것만 쓴다.
#   key_re    그 제공자의 허용 집합. 없으면 전역 KEY_RE 로 떨어진다
#   key_form  "decoding" 이면 퍼센트 인코딩이 섞인 값을 저장 시점에 거절한다
#   key_label 칸 라벨. 단일 필드 제공자도 라벨을 가질 수 있다
#   key_hint  거절 사유에 붙일 안내 문면. 문면을 이 모듈이 쓰지 않는다
PROVIDER_KEY_RE_FIELD = "key_re"
PROVIDER_KEY_FORM_FIELD = "key_form"
PROVIDER_KEY_LABEL_FIELD = "key_label"
PROVIDER_KEY_HINT_FIELD = "key_hint"

# 등록 섹션 안내 문구의 선언 이름(지휘자 결정 2026-10-17: 카탈로그가 정본).
PROVIDER_APPROVAL_FIELD = "approval_notice"
PROVIDER_QUOTA_FIELD = "quota_notice"

# 퍼센트 인코딩 탐지식. `key_form="decoding"` 제공자에서 저장 시점에 거절한다.
# **읽기 시점에는 가릴 수 없다** - 서버의 `qsettings_unescape` 가 읽을 때
# 퍼센트 디코딩을 해버려 Encoding 키와 Decoding 키가 구별되지 않는다
# (서버측 측정 N7u7). 그래서 입구에서 막는 것이 유일한 자리다.
PERCENT_RE = re.compile(r"%[0-9A-Fa-f]{2}")
KEY_FORM_DECODING = "decoding"

# 거절 사유 문구. 허용 문자를 적어 사용자가 무엇을 고칠지 알게 한다.
KEY_FORMAT_REASON = (
    "키 형식이 맞지 않습니다. 영문/숫자/밑줄/하이픈 8-128자만 저장합니다."
)
# 제공자가 안내 문면을 선언했을 때 쓰는 형식. 문면은 카탈로그에서 온다.
KEY_FORMAT_REASON_FMT = "키 형식이 맞지 않습니다. %s"
# `key_form="decoding"` 제공자에서 퍼센트 인코딩이 섞였을 때. 제공자가
# `key_hint` 를 선언하면 그 문면을 쓰고, 없으면 이 한 줄로 떨어진다.
KEY_ENCODED_REASON = (
    "퍼센트 인코딩(%XX)이 섞인 값은 저장하지 않습니다. Decoding 키를 넣으세요."
)
KEY_EMPTY_REASON = "키를 입력하세요."
SETTINGS_UNAVAILABLE_REASON = (
    "QGIS 설정을 열 수 없습니다. QGIS 안에서 다시 시도하세요."
)
URL_FORMAT_REASON = "http:// 또는 https:// 로 시작하는 주소만 저장합니다."

# 마스킹 표시. 값의 어느 글자도 보여주지 않는다 - 패널이 화면 공유나 캡처에
# 들어갈 수 있어서, 끝 몇 자리를 보여 주는 흔한 UX 를 쓰지 않는다.
MASK_BODY = "*" * 8
MASK_FMT = "%s (%d자)"

# 데이터셋 notes 의 함정 문단을 꺼내는 식(설계 docs/8 7-2 (e)). 문면을 새로
# 쓰지 않고 카탈로그에 있는 문장을 **그대로** 패널 툴팁으로 올린다.
TIP_SEGMENT_RE = re.compile(r"\[함정\s*\d+\]")

# 함정 문단 가운데 패널에 올릴 것을 고르는 열쇠말. 조인키 함정이 (e) 의
# 대상이다 - 조용히 틀린 결과가 나오는 축이라 키 자리에서 경고해야 한다.
TIP_KEYWORD = "조인"

# 제공자 하나에 올릴 함정 문단 수 상한. SGIS 는 두 데이터셋이 같은 함정
# 둘(low_search 단계와 adm_cd 코드 체계)을 되풀이 적으므로, 첫 데이터셋의
# 두 문단으로 끊는다. 전부 붙이면 툴팁이 읽히지 않는다.
TIP_MAX = 2


def registry_path():
    """패키지가 동봉한 레지스트리 JSON 경로."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        REGISTRY_FILENAME)


def catalog_paths(path=None):
    """제공자 정의를 읽을 동봉 파일들을 **적재 순서대로** 돌려준다.

    서버의 `collect_server.catalog_paths` 와 같은 순서다(레지스트리 ->
    동봉 스냅샷). 사용자 등록 파일은 여기서 보지 않는다 - 사용자 파일은
    제공자를 만들지 못하므로(설계 docs/8 4-3) 키 칸과 무관하다.

    Args:
        path: 레지스트리 경로. None 이면 동봉본.

    Returns:
        tuple: 파일 경로 문자열들. 존재 여부는 보지 않는다.
    """
    base = str(path or registry_path())
    folder = os.path.dirname(os.path.abspath(base))
    return tuple([base] + [os.path.join(folder, name)
                           for name in CATALOG_SIBLINGS])


def _read_json(path):
    """JSON 파일 하나를 읽는다. 못 읽으면 None 이다(패널은 떠야 한다)."""
    try:
        with open(str(path), "r", encoding="utf-8") as fh:
            body = json.load(fh)
    except Exception:  # noqa: BLE001 - 카탈로그를 못 읽어도 패널은 떠야 한다
        return None
    return body if isinstance(body, dict) else None


def _dataset_rows(body):
    """카탈로그 본문에서 데이터셋 행들을 꺼낸다.

    V-World 158 스냅샷은 `local` 블록 안에 우리 필드를 둔다(설계 docs/8
    4-2). 여기서 보는 것은 `auth` 와 `notes` 뿐이라 두 모양을 합쳐 본다.

    Args:
        body: 카탈로그 JSON 본문.

    Returns:
        list[dict]: {"provider","auth","notes","id"} 평면 행들.
    """
    file_provider = str(body.get("provider") or "")
    out = []
    for entry in body.get("datasets") or ():
        if not isinstance(entry, dict):
            continue
        local = entry.get("local") if isinstance(entry.get("local"),
                                                 dict) else {}
        row = {
            "id": str(entry.get("id") or ""),
            "provider": str(entry.get("provider") or file_provider),
            "auth": entry.get("auth", local.get("auth")),
            "notes": str(entry.get("notes") or local.get("notes") or ""),
        }
        if row["provider"]:
            out.append(row)
    return out


def _tips_from_notes(notes):
    """notes 한 덩이에서 함정 문단들을 끊어 낸다.

    Args:
        notes: 데이터셋 notes 원문.

    Returns:
        list[str]: `[함정 n]` 으로 시작하는 문단들(원문 축자).
    """
    text = str(notes or "")
    marks = [m.start() for m in TIP_SEGMENT_RE.finditer(text)]
    out = []
    for i, start in enumerate(marks):
        end = marks[i + 1] if i + 1 < len(marks) else len(text)
        seg = text[start:end].strip()
        if seg:
            out.append(seg)
    return out


def compile_key_pattern(pattern):
    """제공자가 선언한 `key_re` 를 컴파일한다. 못 읽으면 None 이다.

    선언이 깨져 있으면 전역 식으로 떨어진다 - 임의로 넓힌 식을 만들지
    않는다(깨진 선언을 "전부 허용" 으로 읽으면 검증이 사라진다).

    Args:
        pattern: 정규식 문자열.

    Returns:
        컴파일된 정규식 또는 None.
    """
    text = str(pattern or "")
    if not text:
        return None
    try:
        return re.compile(text)
    except re.error:
        return None


def provider_fields(meta, provider):
    """제공자 하나의 입력 칸 정의를 돌려준다(설계 docs/8 5-1, 3-5).

    `fields` 가 없는 제공자는 한 칸(`upwise_chat/keys/<provider>`)이다.
    그 칸의 `name` 은 빈 문자열이고, 위젯 objectName 규약이 그것으로
    단일/다필드를 가른다(단일은 `UpwiseChatKeyField_<pid>` 그대로).

    검증 선언(`key_re`·`key_form`)과 안내 문면(`key_label`·`key_hint`)은
    **제공자 수준 선언을 칸이 물려받는다.** 칸이 자기 것을 적었으면 그것이
    이긴다. 선언이 없으면 전역 `KEY_RE` 로 떨어진다(하위 호환).

    Args:
        meta: 제공자 정의 dict.
        provider: 제공자 id.

    Returns:
        tuple: ({"name","label","setting","required","key_re","form","hint"},
            ...). 최소 1개.
    """
    meta = meta or {}
    base_re = str(meta.get(PROVIDER_KEY_RE_FIELD) or "")
    base_form = str(meta.get(PROVIDER_KEY_FORM_FIELD) or "")
    base_hint = str(meta.get(PROVIDER_KEY_HINT_FIELD) or "")
    rows = []
    for item in meta.get("fields") or ():
        if not isinstance(item, dict):
            continue
        setting = str(item.get("setting") or "")
        name = str(item.get("name") or "")
        if not setting or not name:
            # 설정 경로나 이름이 없으면 저장할 자리가 없다. 추측하지 않는다.
            continue
        rows.append({
            "name": name,
            "label": str(item.get("label") or name),
            "setting": setting,
            "required": bool(item.get("required", True)),
            "key_re": str(item.get(PROVIDER_KEY_RE_FIELD) or base_re),
            "form": str(item.get(PROVIDER_KEY_FORM_FIELD) or base_form),
            "hint": str(item.get(PROVIDER_KEY_HINT_FIELD) or base_hint),
        })
    if rows:
        return tuple(rows)
    single = str(meta.get("key_setting") or "") or key_setting(provider)
    return ({"name": "",
             # 단일 필드 제공자도 라벨을 가질 수 있다(카탈로그 `key_label`).
             # 선언이 없으면 빈 문자열이고 패널 줄 구성은 종전과 같다.
             "label": str(meta.get(PROVIDER_KEY_LABEL_FIELD) or ""),
             "setting": single, "required": True,
             "key_re": base_re, "form": base_form, "hint": base_hint},)


def field_pattern(field):
    """칸 하나에 적용할 형식 검사식. 선언이 없으면 전역 `KEY_RE` 다."""
    return compile_key_pattern((field or {}).get("key_re")) or KEY_RE


def validate_field_value(field, value):
    """칸 하나의 저장 전 검증(설계 docs/8 3-5).

    순서가 규칙이다. 빈 값 -> 퍼센트 인코딩 -> 형식 검사식. 퍼센트 검사를
    먼저 두는 이유: Encoding 키는 제공자가 선언한 식도 통과할 수 있어서
    (`%` 는 허용 집합 밖이지만 식이 넓으면 통과한다), 사유가 "형식" 으로
    뭉개지면 사용자가 무엇을 고칠지 모른다.

    Args:
        field: `provider_fields()` 의 한 칸.
        value: 사용자가 넣은 값.

    Returns:
        tuple: (통과 여부, 사유 문자열, 다듬은 값). 사유에 **값을 넣지 않는다.**
    """
    text = ("" if value is None else str(value)).strip()
    if not text:
        return False, KEY_EMPTY_REASON, text
    hint = str((field or {}).get("hint") or "")
    form = str((field or {}).get("form") or "").lower()
    if form == KEY_FORM_DECODING and PERCENT_RE.search(text):
        return False, hint or KEY_ENCODED_REASON, text
    if not field_pattern(field).match(text):
        return (False,
                KEY_FORMAT_REASON_FMT % hint if hint else KEY_FORMAT_REASON,
                text)
    return True, "", text


def load_providers(path=None):
    """동봉 카탈로그들에서 제공자 목록을 읽는다.

    설정 패널의 행 순서가 여기서 나온다. 카탈로그가 정본이므로 제공자를
    UI 코드에 적지 않는다 - 데이터셋을 더해도 패널이 따라온다.

    0.5.0: 레지스트리 **한 파일만** 읽던 것을 서버와 같은 파일 집합으로
    넓혔다(설계 docs/8 4-1). 같은 pid 가 여러 파일에 있으면 **먼저 온
    쪽**이 이긴다 - 서버의 `providers.setdefault` 와 같은 규칙이다.

    Args:
        path: 레지스트리 경로. None 이면 동봉본.

    Returns:
        tuple: ({"id","title","signup","key_setting","fields","multi",
            "needs_key","tips"}, ...) id 알파벳 순.
    """
    providers = {}
    needs = {}
    tips = {}
    for target in catalog_paths(path):
        body = _read_json(target)
        if body is None:
            continue
        for pid, meta in (body.get("providers") or {}).items():
            if isinstance(meta, dict):
                providers.setdefault(str(pid), meta)
        # 키가 필요한 제공자인가. auth="none" 인 데이터셋만 가진 제공자는 키
        # 행을 띄울 이유가 없다.
        for row in _dataset_rows(body):
            pid = row["provider"]
            needs[pid] = needs.get(pid, False) or (row["auth"] != "none")
            for seg in _tips_from_notes(row["notes"]):
                if TIP_KEYWORD in seg and seg not in tips.get(pid, []):
                    tips.setdefault(pid, []).append(seg)
    out = []
    for pid in sorted(providers):
        meta = providers[pid] or {}
        fields = provider_fields(meta, pid)
        multi = bool(meta.get("fields"))
        out.append({
            "id": pid,
            "title": str(meta.get("title") or pid),
            "signup": str(meta.get("signup") or ""),
            # 다필드 제공자에는 단일 경로가 없다. 빈 문자열로 둔다 - 없는
            # 경로를 지어내면 그 경로에 값이 저장될 수 있다.
            "key_setting": "" if multi else fields[0]["setting"],
            "fields": fields,
            "multi": multi,
            "needs_key": bool(needs.get(pid, True)),
            "tips": tuple(tips.get(pid, [])[:TIP_MAX]),
            # 등록 섹션 안내 문구. 카탈로그가 정본이고 패널은 읽어 쓴다.
            "approval_notice": str(meta.get(PROVIDER_APPROVAL_FIELD) or ""),
            "quota_notice": str(meta.get(PROVIDER_QUOTA_FIELD) or ""),
        })
    return tuple(out)


def registration_notices(providers=None):
    """등록 섹션의 안내 2줄. 카탈로그 선언이 정본이다.

    선언한 제공자가 여럿이면 **먼저 오는 제공자**(id 알파벳 순)의 문면을
    쓴다. 선언이 없으면 빈 문자열을 돌려주고, 패널이 자기 상수로 떨어진다.

    Args:
        providers: `load_providers()` 의 행들. None 이면 읽는다.

    Returns:
        tuple: (승인 문구, 한도 문구). 없으면 빈 문자열.
    """
    rows = providers if providers is not None else load_providers()
    approval = ""
    quota = ""
    for row in rows:
        if not approval:
            approval = str(row.get("approval_notice") or "")
        if not quota:
            quota = str(row.get("quota_notice") or "")
    return approval, quota


def load_registration_presets(path=None):
    """등록 섹션의 프리셋 정의를 읽는다(설계 docs/8 3-5, 5-3).

    **정의는 이 모듈이 만들지 않는다.** 동봉 카탈로그의 최상위 `presets`
    목록을 읽어 올리고, 블록이 없으면 빈 목록이다. 프리셋이 없으면 등록
    섹션은 콤보가 비고 저장이 거절된다 - 봉투 필드를 여기에 사본으로 적어
    두면 서버측 정의와 어긋나는 날이 온다.

    제공자는 `record.provider` 에서 나온다. 레코드가 가리키는 제공자와
    프리셋이 말하는 제공자가 갈리는 상태를 만들지 않는다.

    Args:
        path: 레지스트리 경로. None 이면 동봉본.

    Returns:
        tuple: ({"provider","name","label","record"}, ...) 정의 순서.
    """
    out = []
    seen = set()
    for target in catalog_paths(path):
        body = _read_json(target)
        if body is None:
            continue
        for item in body.get(PRESET_BLOCK) or ():
            if not isinstance(item, dict):
                continue
            name = str(item.get(PRESET_ID_FIELD) or "")
            record = item.get("record")
            record = dict(record) if isinstance(record, dict) else {}
            provider = str(record.get("provider")
                           or item.get("provider") or "")
            if not name or not provider or name in seen:
                continue
            seen.add(name)
            out.append({
                "provider": provider,
                "name": name,
                "label": str(item.get(PRESET_LABEL_FIELD) or name),
                "record": record,
            })
    return tuple(out)


def key_setting(provider):
    """제공자 하나의 단일 설정 경로. 서버가 찾는 것과 같은 문자열이다."""
    return KEY_PREFIX + str(provider)


def settings_object():
    """QgsSettings 하나. QGIS 밖에서는 None 이다.

    logbook.qgis_profile_root 와 같은 방식이다 - qgis.core 를 함수 안에서
    import 하고 실패하면 떨어뜨린다. 설정을 못 열어서 독이 안 뜨는 일은 없다.
    """
    try:
        from qgis.core import QgsSettings

        return QgsSettings()
    except Exception:  # noqa: BLE001 - 설정 객체 생성 실패는 사유로 돌려준다
        return None


def _resolve(settings):
    """주입된 설정 객체 또는 QgsSettings. 하네스가 1번 인자를 쓴다."""
    return settings if settings is not None else settings_object()


def read_value(setting, settings=None):
    """설정 경로 하나를 읽는다. 없으면 빈 문자열이다.

    다필드 제공자의 칸 하나가 이 창구를 쓴다(설계 docs/8 5-1).

    Args:
        setting: QgsSettings 경로.
        settings: QSettings 호환 객체. None 이면 QgsSettings.

    Returns:
        str
    """
    store = _resolve(settings)
    if store is None or not setting:
        return ""
    try:
        value = store.value(str(setting), "")
    except Exception:  # noqa: BLE001 - 읽기 실패를 "키 없음" 으로 떨어뜨린다
        return ""
    return "" if value is None else str(value)


def save_value(setting, value, settings=None):
    """설정 경로 하나에 저장하고 **곧바로 sync() 한다**.

    Args:
        setting: QgsSettings 경로.
        value: 저장할 키.
        settings: QSettings 호환 객체. None 이면 QgsSettings.

    Returns:
        tuple: (성공 여부, 사유 문자열). 사유에 **키 값을 넣지 않는다.**
    """
    text = ("" if value is None else str(value)).strip()
    if not text:
        return False, KEY_EMPTY_REASON
    if not KEY_RE.match(text):
        return False, KEY_FORMAT_REASON
    store = _resolve(settings)
    if store is None:
        return False, SETTINGS_UNAVAILABLE_REASON
    if not setting:
        return False, SETTINGS_UNAVAILABLE_REASON
    try:
        store.setValue(str(setting), text)
        store.sync()
    except Exception as exc:  # noqa: BLE001 - 사유만 돌려준다
        return False, "설정에 쓰지 못했습니다: %r" % (exc,)
    return True, "저장했습니다"


def save_field(field, value, settings=None):
    """칸 하나를 **그 칸의 검증 규칙으로** 확인한 뒤 저장한다.

    전역 식만 보는 `save_value` 와 다르다. data.go.kr 처럼 base64 계열 키를
    쓰는 제공자는 카탈로그가 선언한 `key_re` 로 검증되고, `key_form` 선언이
    있으면 퍼센트 인코딩이 섞인 값이 저장 시점에 거절된다(설계 docs/8 3-5).

    Args:
        field: `provider_fields()` 의 한 칸.
        value: 저장할 키.
        settings: QSettings 호환 객체. None 이면 QgsSettings.

    Returns:
        tuple: (성공 여부, 사유 문자열). 사유에 **키 값을 넣지 않는다.**
    """
    ok, why, text = validate_field_value(field, value)
    if not ok:
        return False, why
    setting = str((field or {}).get("setting") or "")
    if not setting:
        return False, SETTINGS_UNAVAILABLE_REASON
    store = _resolve(settings)
    if store is None:
        return False, SETTINGS_UNAVAILABLE_REASON
    try:
        store.setValue(setting, text)
        store.sync()
    except Exception as exc:  # noqa: BLE001 - 사유만 돌려준다
        return False, "설정에 쓰지 못했습니다: %r" % (exc,)
    return True, "저장했습니다"


def delete_value(setting, settings=None):
    """설정 경로 하나를 지우고 곧바로 sync() 한다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    store = _resolve(settings)
    if store is None:
        return False, SETTINGS_UNAVAILABLE_REASON
    if not setting:
        return False, SETTINGS_UNAVAILABLE_REASON
    try:
        store.remove(str(setting))
        store.sync()
    except Exception as exc:  # noqa: BLE001
        return False, "설정에서 지우지 못했습니다: %r" % (exc,)
    return True, "지웠습니다"


def read_key(provider, settings=None):
    """단일 필드 제공자의 키를 읽는다. 없으면 빈 문자열이다.

    다필드 제공자는 이 창구로 읽을 수 없다(칸이 둘 이상이다). 그런 제공자는
    `provider_values()` 나 `read_value()` 를 쓴다.

    Args:
        provider: 제공자 이름.
        settings: QSettings 호환 객체. None 이면 QgsSettings.

    Returns:
        str
    """
    return read_value(key_setting(provider), settings=settings)


def save_key(provider, value, settings=None):
    """단일 필드 제공자의 키를 저장하고 **곧바로 sync() 한다**.

    sync 를 안 부르면 서버가 빈 값을 읽는다(설계 5-3 단서 2). 그 집행
    지점은 `save_value()` 이고 하네스가 sync 호출 수를 센다.

    Args:
        provider: 제공자 이름.
        value: 저장할 키.
        settings: QSettings 호환 객체. None 이면 QgsSettings.

    Returns:
        tuple: (성공 여부, 사유 문자열). 사유에 **키 값을 넣지 않는다.**
    """
    return save_value(key_setting(provider), value, settings=settings)


def delete_key(provider, settings=None):
    """단일 필드 제공자의 키를 지우고 곧바로 sync() 한다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    return delete_value(key_setting(provider), settings=settings)


def provider_values(row, settings=None):
    """제공자 한 행의 칸별 저장값.

    **반환값은 레다크터와 마스킹에만 들어간다.** 로그·진단·UI 문구에 쓰지
    않는다.

    Args:
        row: `load_providers()` 의 한 행.
        settings: QSettings 호환 객체.

    Returns:
        dict: 필드 이름(단일 필드는 "") -> 값.
    """
    out = {}
    for field in row.get("fields") or ():
        out[field["name"]] = read_value(field["setting"], settings=settings)
    return out


def provider_state(row, settings=None):
    """제공자 한 행의 충족 상태(설계 docs/8 5-1).

    required 필드가 **전부** 채워졌을 때만 configured 다. 부분 입력은
    configured 가 아니고, 빠진 칸은 **이름/라벨**로만 돌려준다(값 금지).

    Args:
        row: `load_providers()` 의 한 행.
        settings: QSettings 호환 객체.

    Returns:
        dict: {"configured": bool, "any": bool, "filled": tuple,
            "missing": tuple, "missing_labels": tuple}
    """
    filled = []
    missing = []
    missing_labels = []
    any_value = False
    for field in row.get("fields") or ():
        value = read_value(field["setting"], settings=settings)
        if value:
            any_value = True
            filled.append(field["name"])
        elif field.get("required", True):
            missing.append(field["name"])
            missing_labels.append(field.get("label") or field["name"])
    return {
        "configured": not missing,
        "any": any_value,
        "filled": tuple(filled),
        "missing": tuple(missing),
        "missing_labels": tuple(missing_labels),
    }


def read_endpoint_override(settings=None):
    """엔드포인트 기본 URL 오버라이드. 없으면 빈 문자열."""
    return read_value(ENDPOINT_OVERRIDE_KEY, settings=settings)


def save_endpoint_override(url, settings=None):
    """오버라이드를 저장한다. http(s) 가 아니면 거절한다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    text = ("" if url is None else str(url)).strip()
    if not text:
        return False, URL_FORMAT_REASON
    if not (text.startswith("http://") or text.startswith("https://")):
        return False, URL_FORMAT_REASON
    store = _resolve(settings)
    if store is None:
        return False, SETTINGS_UNAVAILABLE_REASON
    try:
        store.setValue(ENDPOINT_OVERRIDE_KEY, text)
        store.sync()
    except Exception as exc:  # noqa: BLE001
        return False, "설정에 쓰지 못했습니다: %r" % (exc,)
    return True, "저장했습니다"


def delete_endpoint_override(settings=None):
    """오버라이드를 지운다.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    return delete_value(ENDPOINT_OVERRIDE_KEY, settings=settings)


def mask(value):
    """저장된 값의 마스킹 표시. 값의 글자를 하나도 내보내지 않는다.

    Returns:
        str: 예 "******** (25자)". 빈 값이면 빈 문자열.
    """
    text = "" if value is None else str(value)
    if not text:
        return ""
    return MASK_FMT % (MASK_BODY, len(text))


def secrets(providers=None, settings=None):
    """레다크션에 넘길 키 값들.

    **이 함수의 반환값은 레다크터에만 들어간다.** 로그, 진단, UI 문구에
    쓰지 않는다. 0.5.0: 다필드 제공자의 칸 전부를 센다 - 한 칸만 넣으면
    나머지 칸 값이 레다크션 집합에서 빠진다.

    Returns:
        tuple: 저장된 키 값들(중복 제거).
    """
    rows = providers if providers is not None else load_providers()
    out = []
    for row in rows:
        for value in provider_values(row, settings=settings).values():
            if value and value not in out:
                out.append(value)
    return tuple(out)


def key_state(providers=None, settings=None):
    """어느 제공자에 키가 있고 어느 쪽이 비었는가.

    **이 함수는 사실만 돌려주고 판정하지 않는다.** 전제조건 판정은
    `detect.Prerequisites.refresh_keys` 가 하고, 그 판정은 0.5.0 부터
    **ANY** 다 - 설정된 제공자가 하나라도 있으면 수집은 활성이고 키가 없는
    제공자의 데이터셋만 목록에서 비활성이다(설계 docs/8 2-1). 판정을 두 군데
    두지 않으려고 여기서는 두 묶음을 그대로 올린다.

    0.5.0 다필드: required 필드가 **전부** 채워진 제공자만 configured 다.
    부분 입력은 missing 으로 간다(설계 docs/8 5-1).

    Returns:
        tuple: (설정된 제공자 id 튜플, 비어 있는 제공자 id 튜플)
            키가 필요없는 제공자(auth=none 전용)는 양쪽에 들어가지 않는다.
    """
    rows = providers if providers is not None else load_providers()
    configured = []
    missing = []
    for row in rows:
        if not row.get("needs_key", True):
            continue
        if provider_state(row, settings=settings)["configured"]:
            configured.append(row["id"])
        else:
            missing.append(row["id"])
    return tuple(configured), tuple(missing)


def summary(providers=None, settings=None):
    """진단 로그가 찍는 요약. **키 값이 들어가지 않는다.**

    Returns:
        dict: 제공자별 설정 여부, 부분 입력의 빠진 칸 이름, 오버라이드 존재.
    """
    rows = providers if providers is not None else load_providers()
    configured, missing = key_state(rows, settings=settings)
    # 부분 입력을 요약에서 구분할 수 있게 **빠진 칸 이름**만 함께 올린다.
    # 값은 올리지 않는다(하네스 24 K7 이 전문 grep 으로 단정한다).
    gaps = {}
    for row in rows:
        if not row.get("needs_key", True):
            continue
        state = provider_state(row, settings=settings)
        if state["missing"] and state["any"]:
            gaps[row["id"]] = list(state["missing"])
    return {
        "providers": [row["id"] for row in rows],
        "configured": list(configured),
        "missing": list(missing),
        "partial_fields": gaps,
        "endpoint_override": bool(read_endpoint_override(settings=settings)),
    }
