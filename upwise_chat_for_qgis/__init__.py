"""UPWISE Chat for QGIS - QGIS 플러그인 진입점.

QGIS 플러그인 로더는 플러그인 폴더의 `__init__.py` 에서 `classFactory(iface)` 를
찾아 호출한다. 이 모듈은 그 한 가지 일만 한다.

플러그인 본체 import 를 최상단이 아니라 `classFactory` 안에 둔 이유:
패키지를 import 하는 것만으로 Qt 위젯 모듈이 올라오지 않게 하려는 것이다.
그래야 QApplication 없이도 패키지 import 가 성립하고, 골격 검증을
QGIS GUI 없이 돌릴 수 있다.

설계 정본: docs/1.mvp_design_v1.md 7-4(리포 레이아웃), 10(S1 범위와 완료 판정)
"""


def classFactory(iface):  # noqa: N802 - QGIS 로더가 요구하는 고정 이름이다
    """QGIS 가 플러그인을 적재할 때 호출하는 팩토리.

    Args:
        iface: QgisInterface 인스턴스. QGIS 가 넘겨준다.

    Returns:
        UpwiseChatPlugin: initGui / unload 를 가진 플러그인 객체.
    """
    from .plugin import UpwiseChatPlugin

    return UpwiseChatPlugin(iface)
