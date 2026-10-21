"""값 기반 레다크션 (0.2.1, 설계 docs/2 5-4).

무엇을 막는가
    E4 구조에서 키는 모델 스트림에 실리지 않는다(키를 아는 것은 수집 서버
    프로세스 하나다). 그래도 **사용자가 키를 채팅에 직접 붙여 넣는 경로**가
    남아 있다. 그 순간 L1(모델 컨텍스트)과 L3(CLI 자체 세션 저장소)은 이미
    깨지지만, 우리가 지울 수 있는 L4(`session_<uuid>.jsonl`)와 L5(전사 위젯),
    그리고 진단 로그는 막을 수 있다. 비용이 작아서 둔다.

규칙 (설계 5-4 그대로. 완화하지 않는다)
    * 설정에 저장된 키 값과 **완전 일치하는 부분문자열**만 치환한다.
      정규식으로 "키처럼 보이는 것" 을 찾지 않는다 - 오탐이 본문을 깨뜨린다.
    * 길이 12자 미만 값은 대상에서 제외한다. 짧은 값은 본문을 잠식한다.
    * **비가역이다.** 원본을 따로 보존하지 않는다. 감사 경로가 필요하면
      "레다크션 n건" 카운터만 남긴다(logbook 이 그 줄을 쓴다).

변형 집합 (0.5.0, 설계 docs/8 2-2)
    치환 대상은 저장값 하나가 아니라 **인코딩 변형 전체**다
    `{ v, quote(v, safe=""), quote_plus(v), unquote(v) if unquote(v) != v }`.
    지금 키가 영숫자뿐이라 네 변형이 같은 문자열로 접히지만, base64 계열 키
    (`+` `/` `=`)를 받는 순간 URL 에는 `%2B...` 가 들어가고 저장값과의 완전
    일치가 0건이 된다. 마스킹이 지금 맞는 것은 문자집합 제약 덕분이지 규칙이
    옳아서가 아니었다.

적용 지점 3곳
    1. jsonl 기록 전      backend/logbook.SessionLogbook.write_stdout_line
    2. 전사 위젯 전        ui/chat_view.ChatView (말풍선, 블록, 도구 카드,
                           "전문 보기" 임시 파일)
    3. 진단 번들 전        backend/logbook.SessionLogbook.diag

수집 서버에도 같은 규칙의 `mask()` 가 따로 있다(collect_server.mask). 그쪽은
`-I` 로 뜨는 단일 파일이라 이 모듈을 import 할 수 없다 - 상수 2개가 양쪽에
중복되므로, 검증 하네스가 두 값의 일치를 판정한다.

설계 정본: docs/2.collect_feature_design_v1.md 5-1, 5-4
"""

import threading
import urllib.parse

# 치환 토큰과 최소 길이. collect_server.REDACT_TOKEN / REDACT_MIN_LEN 과 **같은
# 값이어야 한다**(하네스 판정 항목). 한쪽만 바꾸면 서버가 마스킹한 URL 과
# 전사의 치환 표기가 달라져 사용자가 두 가지 표기를 보게 된다.
REDACT_TOKEN = "***REDACTED***"
REDACT_MIN_LEN = 12


def secret_variants(value, min_len=REDACT_MIN_LEN):
    """비밀 하나에서 치환해야 할 변형 전체를 만든다(설계 docs/8 2-2).

    `collect_server.secret_variants` 와 **같은 규칙**이다. 두 구현이 분리돼
    있는 것은 서버가 `-I` 로 뜨는 단일 파일이라 이 모듈을 import 할 수 없기
    때문이고, 규칙 문면이 어긋나면 한쪽만 새는 상태가 된다.

    Args:
        value: 비밀 원문.
        min_len: 이 길이 미만 변형은 버린다(설계 5-4 안전장치).

    Returns:
        tuple: 길이 내림차순 변형들.
    """
    raw = "" if value is None else str(value)
    if not raw:
        return ()
    cands = [raw, urllib.parse.quote(raw, safe=""),
             urllib.parse.quote_plus(raw)]
    plain = urllib.parse.unquote(raw)
    if plain != raw:
        cands.append(plain)
    kept = []
    for text in cands:
        if len(text) >= int(min_len) and text not in kept:
            kept.append(text)
    kept.sort(key=len, reverse=True)
    return tuple(kept)


class Redactor:
    """키 값 목록을 들고 문자열에서 그 값만 지우는 객체.

    스레드 둘이 같은 객체를 쓴다. 리더 스레드가 jsonl 줄을, GUI 스레드가 전사와
    진단 줄을 넘긴다. 그래서 카운터에 락을 둔다 - 치환 자체는 불변 목록 읽기라
    락이 필요 없지만, 카운터는 두 스레드가 더한다.
    """

    def __init__(self, secrets=(), min_len=REDACT_MIN_LEN, token=REDACT_TOKEN):
        """
        Args:
            secrets: 지울 값들. 길이 미달 값은 생성 시 버린다.
            min_len: 치환 대상 최소 길이(설계 5-4 안전장치).
            token: 치환 문자열.
        """
        self._min_len = int(min_len)
        self._token = str(token)
        self._lock = threading.Lock()
        self._count = 0
        self._dropped = 0
        self._secrets = ()
        self.set_secrets(secrets)

    def set_secrets(self, values):
        """지울 값 목록을 갈아끼운다. 키 저장/삭제 직후에 불린다.

        값 하나마다 **인코딩 변형 전체**를 넣는다(0.5.0, 설계 docs/8 2-2).
        긴 값을 먼저 지운다. 한 키가 다른 키의 부분문자열인 경우에 짧은 쪽을
        먼저 치환하면 긴 쪽이 토큰에 섞여 남는다.

        Args:
            values: 문자열 iterable. None 과 길이 미달 값은 버린다.

        Returns:
            int: 받아들인 값(변형 포함)의 수.
        """
        kept = []
        dropped = 0
        for value in values or ():
            text = "" if value is None else str(value)
            variants = secret_variants(text, min_len=self._min_len)
            if not variants:
                # 길이 미달은 **원본 1건**으로 센다. 변형 수로 세면 사용자가
                # 짧은 키 하나를 넣었는데 카운터가 여러 건으로 보인다.
                if text:
                    dropped += 1
                continue
            for item in variants:
                if item not in kept:
                    kept.append(item)
        kept.sort(key=len, reverse=True)
        with self._lock:
            self._secrets = tuple(kept)
            self._dropped = dropped
        return len(kept)

    def redact(self, text):
        """문자열에서 키 값을 지운다. 값이 없으면 원문을 그대로 돌려준다.

        Args:
            text: 임의 문자열. 문자열이 아니면 str() 로 바꾼다.

        Returns:
            str: 치환된 문자열.
        """
        secrets = self._secrets
        if not secrets:
            return text if isinstance(text, str) else (
                "" if text is None else str(text))
        body = text if isinstance(text, str) else (
            "" if text is None else str(text))
        hits = 0
        for secret in secrets:
            if secret in body:
                hits += body.count(secret)
                body = body.replace(secret, self._token)
        if hits:
            with self._lock:
                self._count += hits
        return body

    # 호출 가능 객체로도 쓴다. 전사 쪽은 함수 하나만 들고 있으면 되므로
    # 모듈 의존을 늘리지 않기 위해 콜러블을 넘긴다.
    __call__ = redact

    @property
    def count(self):
        """지금까지 치환한 **건수**. 값은 어디에도 남기지 않는다."""
        with self._lock:
            return self._count

    @property
    def secrets_n(self):
        """지울 값의 수. 값 자체는 노출하지 않는다."""
        return len(self._secrets)

    @property
    def dropped_n(self):
        """길이 미달로 버린 값의 수. 사용자가 짧은 키를 넣었을 때의 단서다."""
        with self._lock:
            return self._dropped

    def summary(self):
        """진단 로그와 하네스가 읽는 dict. **키 값이 들어가지 않는다.**"""
        return {"secrets_n": self.secrets_n,
                "dropped_n": self.dropped_n,
                "redactions": self.count,
                "min_len": self._min_len}
