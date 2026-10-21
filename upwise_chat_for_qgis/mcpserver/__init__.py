# --- UPWISE vendor header -------------------------------------------------
# Source: qgis_mcp_plugin 0.15.0 - Copyright (c) Nicolas Karasiak
# Upstream: https://github.com/nkarasiak/qgis-mcp, tag v0.15.0, taken 2026-10-11
# License: GPL-2.0-or-later (see LICENSE.upstream). UPWISE is a licensee here,
#   not the copyright holder, and redistributes under the same terms.
# Changed by UPWISE 2026-10-11 (GPLv2 section 2(a) notice): contents replaced -
#   design 3-3 point 8. Upstream was `from .plugin import classFactory`.
# --- end UPWISE vendor header ---------------------------------------------
"""QGIS 측 소켓 서버와 도구 실행 코드 (상류 vendor, 설계 5 S3-1).

이 패키지는 **QGIS 플러그인이 아니다.** 상류 `__init__.py` 는
`classFactory` 를 re-export 해서 QGIS 플러그인 진입점이었지만, 여기서는
`upwise_chat_for_qgis` 가 진입점이고 이 패키지는 그 안의 한 모듈이다.
진입점이 중첩되어 있으면 "어느 쪽이 플러그인인가" 가 헷갈리므로 제거했다
(설계 3-3 수정 8). 상류 `plugin.py`·`configurator.py` 자체를 가져오지
않았으므로 import 할 대상도 없다(설계 3-2).

무엇이 여기 있나
    server.py       소켓·프레이밍·인증·디스패치·저널
    handlers/       도구 실행 126종 (우리가 노출하는 것은 78종 - exposure.py)
    compat.py       QGIS 3.28~4.99 enum 표기 차이 런타임 해석
    wire.py         길이 접두 프레이밍·송신 백로그·batch 차단 목록
    exposure.py     **우리 저작.** 노출 집합 78종과 제외 6종

상류와의 관계
    0.15.0 고정이고 자동 추적하지 않는다(설계 D-B10). 수정 지점과 파일별
    sha256 은 VENDOR.md 가 정본이다. 상류 새 버전과의 diff 는 VENDOR.md 의
    원본 sha256 으로 기계적으로 낸다.
"""
