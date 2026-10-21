"""사용자 등록 데이터셋 레코드 파일 (0.5.0, 설계 docs/8 4-1, 4-3, 5-3).

왜 QgsSettings 가 아니라 별도 JSON 파일인가
    서버의 `qsettings_unescape()` 는 역함수가 아니다 - 퍼센트 디코딩과
    바깥 따옴표 제거만 하고 백슬래시 이스케이프를 처리하지 않으며, 값에
    `%` 가 있으면 무조건 디코딩을 시도한다(설계 docs/8 4-1, 10). 왕복이
    보장되지 않는 통로에 구조화 값을 넣지 않는다. 그래서 레코드는
    `<프로필>/upwise_chat/collect_user_registry.json` 에 쓰고, **키는 이
    파일에 넣지 않는다**(키는 INI, `backend/keystore`).

누가 쓰고 누가 읽는가
    쓰는 쪽은 **플러그인 UI 하나**다(설계 docs/8 4-1 표). 읽기와 검증은
    수집 서버가 호출마다 mtime 을 보고 다시 한다. 이 모듈이 지키는 것은
    **저장 시점 구조 검증**(네트워크 0)과 **원자적 쓰기**다.

저장 시점 검증 (설계 docs/8 4-3)
    `https://` 강제 / 쿼리 문자열 포함 금지 / 경로 템플릿 `{}` 금지 /
    `provider` 열거형(동봉 정의에 있는 제공자만) / id 는 `user.` 접두.
    실제 호출은 하지 않는다 - 플러그인 프로세스에서 시험 호출을 하면
    egress 경로가 둘이 되고 URL 로그 지점이 하나 늘어난다. 검증은 첫 수집
    1회가 겸하고 그 결과로 `verified` 가 올라간다(서버 소관).

원자적 쓰기
    `<파일>.part` 에 전문을 쓰고 `os.replace` 로 이름을 바꾼다. 서버가
    호출마다 이 파일을 다시 읽으므로(핫리로드), 반쯤 쓰인 파일이 읽히는
    창을 두지 않는다.

설계 정본: docs/8.collect_expansion_design_v1.md 4-1, 4-3, 5-3
"""

import datetime as dt
import json
import os
import re

# 파일 스키마 번호. 서버와 같은 값이어야 한다(`"schema": 1`, 설계 4-3).
SCHEMA = 1

# 프로필 아래 경로. `collect_server.USER_CATALOG_SUBPATH` 와 **같아야
# 한다**(하네스 24 A12 가 일치를 판정한다). 서버는 `-I` 단일 파일이라
# import 할 수 없어 중복이 불가피하다.
USER_SUBPATH = ("upwise_chat", "collect_user_registry.json")

# 사용자 레코드 id 접두. `collect_server.USER_ID_PREFIX` 와 같아야 한다.
# 동봉 id 와 사용자 id 를 접두로 가르지 않으면 조용한 덮어쓰기가 "목록에는
# 보이는데 다른 데로 요청이 간다" 를 만든다(설계 4-1).
USER_ID_PREFIX = "user."

# 원자적 쓰기의 중간 파일 확장자.
PART_SUFFIX = ".part"

# id 로 쓸 수 있는 글자. 한글 이름에서는 아무 글자도 남지 않으므로 그때는
# 일련번호로 떨어진다(아래 `make_record_id`).
ID_SLUG_RE = re.compile(r"[^a-z0-9]+")

# 이름이 ASCII 로 환원되지 않을 때 쓰는 일련번호 형식.
ID_FALLBACK_FMT = "ds%02d"

# 거절 사유. 사용자가 무엇을 고칠지 알게 적는다.
REASON_NO_TITLE = "데이터셋 이름을 입력하세요."
REASON_NO_URL = "엔드포인트 주소를 입력하세요."
REASON_SCHEME = "https:// 로 시작하는 주소만 등록합니다."
REASON_QUERY = (
    "주소에 쿼리 문자열을 넣지 마세요. 호출 파라미터 칸에 한 줄씩 적습니다."
)
REASON_TEMPLATE = "주소에 경로 템플릿({}) 을 쓸 수 없습니다."
REASON_PROVIDER = "등록할 수 있는 제공자 정의가 없습니다."
REASON_PROVIDER_FMT = "제공자 %s 는 동봉 정의에 없습니다."
REASON_PREFIX = "등록 id 는 %s 로 시작해야 합니다." % USER_ID_PREFIX
REASON_COLLISION_FMT = "같은 id 가 이미 등록되어 있습니다: %s"
REASON_PARAM_LINE_FMT = "호출 파라미터 %d번째 줄을 읽을 수 없습니다."
REASON_UNREADABLE = (
    "기존 등록 파일을 읽을 수 없어 등록하지 않았습니다. 파일을 확인하세요."
)
REASON_WRITE_FMT = "등록 파일에 쓰지 못했습니다: %r"
REASON_NOT_FOUND_FMT = "등록 목록에 없는 id 입니다: %s"
REASON_SAVED = "등록했습니다"
REASON_DELETED = "삭제했습니다"


def default_path():
    """`<QGIS 프로필>/upwise_chat/collect_user_registry.json`.

    프로필 경로는 `logbook.qgis_profile_root()` 가 정본이다 - QGIS 밖에서
    import 될 수 있으므로 거기서 홈 폴더로 떨어뜨린다.
    """
    from . import logbook

    return str(logbook.qgis_profile_root().joinpath(*USER_SUBPATH))


def load_records(path=None):
    """등록 레코드를 읽는다.

    Args:
        path: 등록 파일 경로. None 이면 프로필 기본 경로.

    Returns:
        tuple: (레코드 리스트, 사유 문자열). 사유는 "ok"/"absent"/오류 설명.
            못 읽은 경우 리스트는 비고 사유가 "ok" 가 아니다 - 그 상태에서
            덮어쓰면 사용자 레코드가 사라지므로 쓰기 쪽이 사유를 본다.
    """
    target = str(path or default_path())
    if not os.path.isfile(target):
        return [], "absent"
    try:
        with open(target, "r", encoding="utf-8") as fh:
            body = json.load(fh)
    except Exception as exc:  # noqa: BLE001 - 사유로 돌려준다
        return [], "unreadable: %r" % (exc,)
    if not isinstance(body, dict):
        return [], "not a json object"
    rows = body.get("records")
    if rows is None:
        return [], "no records block"
    if not isinstance(rows, list):
        return [], "records is not a list"
    return [r for r in rows if isinstance(r, dict)], "ok"


def write_records(records, path=None):
    """레코드 전량을 **원자적으로** 쓴다(`.part` -> rename).

    Args:
        records: 레코드 dict 목록.
        path: 등록 파일 경로. None 이면 프로필 기본 경로.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    target = str(path or default_path())
    part = target + PART_SUFFIX
    body = {"schema": SCHEMA, "records": list(records)}
    try:
        folder = os.path.dirname(os.path.abspath(target))
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(part, "w", encoding="utf-8") as fh:
            json.dump(body, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            # 이름을 바꾸기 전에 내용이 디스크에 닿아 있어야 한다. 서버가
            # 호출마다 이 파일을 다시 읽으므로 반쯤 쓰인 사본이 읽히는 창을
            # 두지 않는다.
            os.fsync(fh.fileno())
        os.replace(part, target)
    except Exception as exc:  # noqa: BLE001 - 사유만 돌려준다
        try:
            if os.path.isfile(part):
                os.remove(part)
        except OSError:
            pass
        return False, REASON_WRITE_FMT % (exc,)
    return True, "ok"


def parse_params(text):
    """호출 파라미터 줄들을 읽는다(설계 docs/8 5-3).

    두 모양만 읽는다.
        `name=value`  값이 고정된 파라미터 -> `fixed_params`
        `name`        모델이 채울 파라미터 -> `params` + `required`

    값이 없는 줄을 선언으로 읽는 이유: 사용자가 이름만 적은 칸은 호출마다
    달라지는 값이고, 적어 둘 만큼 중요한 칸은 그 API 가 요구하는 칸이다.
    타입은 `str` 로 둔다 - 서버가 타입 위반을 거절하므로 좁게 두는 쪽이
    안전하고, 숫자 칸은 문자열로도 질의가 성립한다.

    Args:
        text: 줄 단위 입력 원문.

    Returns:
        tuple: (fixed_params dict, params dict, required list, 오류 사유)
            사유가 빈 문자열이면 정상이다.
    """
    fixed = {}
    params = {}
    required = []
    for i, raw in enumerate(str(text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, _sep, value = line.partition("=")
            name = name.strip()
            value = value.strip()
            if not name:
                return {}, {}, [], REASON_PARAM_LINE_FMT % i
            if value:
                fixed[name] = value
                continue
            # `name=` 는 `name` 과 같게 읽는다(붙여넣기 부산물).
        else:
            name = line
        if " " in name or "&" in name or "?" in name:
            return {}, {}, [], REASON_PARAM_LINE_FMT % i
        params[name] = {"type": "str"}
        if name not in required:
            required.append(name)
    return fixed, params, required, ""


def make_record_id(provider, title, existing=()):
    """레코드 id 를 만든다.

    규약은 `user.<provider>.<이름 slug>` 다. 한글 이름은 slug 가 비므로
    일련번호로 떨어진다. 같은 id 가 있으면 뒤에 숫자를 붙인다.

    Args:
        provider: 제공자 id.
        title: 사용자가 적은 데이터셋 이름.
        existing: 이미 쓰인 id 들.

    Returns:
        str
    """
    used = set(str(x) for x in existing)
    slug = ID_SLUG_RE.sub("_", str(title or "").lower()).strip("_")
    base = "%s%s.%s" % (USER_ID_PREFIX, provider, slug) if slug else ""
    if not base:
        n = 1
        while True:
            base = "%s%s.%s" % (USER_ID_PREFIX, provider,
                                ID_FALLBACK_FMT % n)
            if base not in used:
                return base
            n += 1
    if base not in used:
        return base
    n = 2
    while "%s_%d" % (base, n) in used:
        n += 1
    return "%s_%d" % (base, n)


def build_record(preset, title, base_url, params_text, advanced=None,
                 existing=()):
    """UI 입력과 프리셋을 합쳐 레코드 하나를 만든다(설계 docs/8 4-3).

    프리셋의 `record` 블록이 봉투 필드(auth·key_param·response·paging)를
    채우고, 사용자 입력이 그 위를 덮는다. 봉투 필드를 이 모듈에 사본으로
    적지 않는다 - 프리셋 정의가 정본이다.

    Args:
        preset: `keystore.load_registration_presets()` 의 한 항목.
        title: 데이터셋 이름.
        base_url: 엔드포인트 주소.
        params_text: 호출 파라미터 줄 원문.
        advanced: 고급 칸 입력 dict. 키는
            items_path/code_path/ok/lon_field/lat_field/crs/
            page_param/size_param/size/total_path.
        existing: 이미 쓰인 id 들(충돌 회피).

    Returns:
        tuple: (레코드 dict 또는 None, 사유 문자열)
    """
    if not isinstance(preset, dict) or not preset.get("provider"):
        return None, REASON_PROVIDER
    name = str(title or "").strip()
    if not name:
        return None, REASON_NO_TITLE
    url = str(base_url or "").strip()
    if not url:
        return None, REASON_NO_URL
    fixed, params, required, why = parse_params(params_text)
    if why:
        return None, why

    record = {}
    base = preset.get("record")
    if isinstance(base, dict):
        record = json.loads(json.dumps(base))
    record["id"] = make_record_id(preset["provider"], name, existing)
    record["provider"] = str(preset["provider"])
    record["title"] = name
    record["base_url"] = url
    # 프리셋이 고정 파라미터를 들고 있으면(예: type=json) 사용자 줄이 그
    # 위를 덮는다. 같은 이름을 두 곳에서 다르게 보내는 상태를 만들지 않는다.
    merged_fixed = dict(record.get("fixed_params") or {})
    merged_fixed.update(fixed)
    if merged_fixed:
        record["fixed_params"] = merged_fixed
    merged_params = dict(record.get("params") or {})
    merged_params.update(params)
    if merged_params:
        record["params"] = merged_params
    merged_required = list(record.get("required") or [])
    for key in required:
        if key not in merged_required:
            merged_required.append(key)
    if merged_required:
        record["required"] = merged_required

    adv = {k: str(v or "").strip() for k, v in (advanced or {}).items()}
    response = dict(record.get("response") or {})
    error = dict(response.get("error") or {})
    if adv.get("items_path"):
        response["items_path"] = adv["items_path"]
    if adv.get("code_path"):
        error["code_path"] = adv["code_path"]
    if adv.get("ok"):
        # 성공 코드는 쉼표로 여러 개 적는다(JSON 은 "00", XML 은 "000").
        error["ok"] = [v.strip() for v in adv["ok"].split(",") if v.strip()]
    if error:
        response["error"] = error
    for src, dst in (("lon_field", "lon_field"), ("lat_field", "lat_field"),
                     ("crs", "crs")):
        if adv.get(src):
            response[dst] = adv[src]
    if response:
        record["response"] = response

    paging = dict(record.get("paging") or {})
    for src, dst in (("page_param", "page_param"),
                     ("size_param", "size_param"),
                     ("total_path", "total_path")):
        if adv.get(src):
            paging[dst] = adv[src]
    if adv.get("size"):
        try:
            paging["size"] = int(adv["size"])
        except ValueError:
            # 숫자가 아니면 적힌 대로 두지 않는다 - 서버 타입 검증에서
            # 거절될 값을 저장해 두면 "등록은 됐는데 수집이 안 되는" 상태다.
            return None, "페이지 크기는 숫자만 적습니다."
    if paging:
        record["paging"] = paging

    record["registered_at"] = dt.date.today().isoformat()
    record["verified"] = False
    return record, "ok"


def validate_record(record, provider_ids=(), existing_ids=()):
    """저장 시점 구조 검증(설계 docs/8 4-3). 네트워크 호출 0회.

    Args:
        record: 레코드 dict.
        provider_ids: 동봉 정의에 있는 제공자 id 들(열거형).
        existing_ids: 이미 등록된 id 들.

    Returns:
        tuple: (통과 여부, 사유 문자열)
    """
    if not isinstance(record, dict):
        return False, REASON_NO_TITLE
    rec_id = str(record.get("id") or "")
    if not rec_id.startswith(USER_ID_PREFIX):
        return False, REASON_PREFIX
    if rec_id in set(str(x) for x in existing_ids):
        return False, REASON_COLLISION_FMT % rec_id
    if not str(record.get("title") or "").strip():
        return False, REASON_NO_TITLE
    provider = str(record.get("provider") or "")
    allowed = set(str(x) for x in provider_ids)
    if not allowed:
        return False, REASON_PROVIDER
    if provider not in allowed:
        return False, REASON_PROVIDER_FMT % provider
    url = str(record.get("base_url") or "")
    if not url:
        return False, REASON_NO_URL
    if not url.startswith("https://"):
        return False, REASON_SCHEME
    if "?" in url or "&" in url:
        return False, REASON_QUERY
    if "{" in url or "}" in url:
        return False, REASON_TEMPLATE
    return True, "ok"


def add_record(record, path=None, provider_ids=()):
    """레코드 하나를 검증해 파일에 더한다.

    Args:
        record: `build_record()` 가 만든 레코드.
        path: 등록 파일 경로. None 이면 프로필 기본 경로.
        provider_ids: 제공자 열거형.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    rows, why = load_records(path)
    if why not in ("ok", "absent"):
        # 읽을 수 없는 파일을 덮으면 사용자 레코드가 사라진다. 멈춘다.
        return False, REASON_UNREADABLE
    ok, reason = validate_record(record, provider_ids=provider_ids,
                                 existing_ids=[r.get("id") for r in rows])
    if not ok:
        return False, reason
    rows.append(record)
    wrote, write_why = write_records(rows, path)
    if not wrote:
        return False, write_why
    return True, REASON_SAVED


def delete_record(record_id, path=None):
    """id 하나를 지운다. 편집은 삭제 후 재등록이다(설계 docs/8 5-3).

    Args:
        record_id: 지울 레코드 id.
        path: 등록 파일 경로.

    Returns:
        tuple: (성공 여부, 사유 문자열)
    """
    rows, why = load_records(path)
    if why not in ("ok", "absent"):
        return False, REASON_UNREADABLE
    target = str(record_id or "")
    keep = [r for r in rows if str(r.get("id") or "") != target]
    if len(keep) == len(rows):
        return False, REASON_NOT_FOUND_FMT % target
    wrote, write_why = write_records(keep, path)
    if not wrote:
        return False, write_why
    return True, REASON_DELETED


def summary(path=None):
    """등록 목록 요약. **키 값이 들어가지 않는다**(레코드에 키가 없다).

    Returns:
        dict: 건수와 (id, 제공자, 검증 여부) 목록.
    """
    rows, why = load_records(path)
    return {
        "path": str(path or default_path()),
        "why": why,
        "n": len(rows),
        "records": [{"id": str(r.get("id") or ""),
                     "provider": str(r.get("provider") or ""),
                     "verified": bool(r.get("verified"))} for r in rows],
    }
