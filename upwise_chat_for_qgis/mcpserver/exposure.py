"""내장 서버가 소켓에서 받아들이는 명령 집합 (UPWISE 저작, 설계 5 S4-2).

Copyright (c) 2026 UPWISE. GPL-2.0-or-later.

이 파일이 있는 이유
    상류 핸들러는 126종이고 우리 제품이 쓰는 것은 78종이다. 나머지 48종을
    "안 광고한다" 로만 닫으면 가드가 CLI 플래그 하나에 걸린다 -
    `--disallowedTools` 는 **CLI 측 필터라 소켓에는 무효**다. 소켓은 같은
    사용자의 아무 프로세스나 닿을 수 있으므로, 서버가 이름으로 직접 거절해야
    한다(설계 4-2, D-B4). 그래서 `server._dispatch` 가 `COMMANDS` 멤버십에
    이어 이 집합의 교집합을 한 번 더 본다.

왜 포스처별로 줄이지 않나
    상승 사다리가 **"광고는 되고 allowlist 에는 없는"** 상태에 걸려 있다
    (설계 4-2·E26). R 에서 W 도구를 부르면 `permission_denied` -> 거부 바 ->
    "허용하고 다시 요청" -> W 재spawn 으로 간다. 포스처마다 노출을 줄이면
    같은 호출이 `No such tool available`(제외 신호)로 와서 **거부 바가 뜨지
    않는다.** 그래서 세 포스처가 같은 78종을 본다.

backend/posture.py 와의 결합 (고의로 두 곳이다)
    여기의 78종은 `posture.QGIS_READ_TOOLS` 와 `QGIS_WRITE_TOOLS` 의 합집합과
    **집합 일치**해야 한다(적재 3종은 W 의 부분집합이다). 자동 유도하지 않고
    별 목록으로 둔 것은, allowlist 에 이름을 더하는 변경이 **노출 집합과
    스키마 자산에도 더해져야 함**을 눈에 보이게 하려는 것이다(설계 6-2 근거 4).
    누락은 하네스 32 의 집합 일치 검사가 잡는다.

stdlib 전용이다 - `qgis` 를 import 하지 않는다. 하네스가 QGIS 밖에서 이
집합을 읽어야 하고, 정합 게이트도 그렇다.
"""

# 제품 allowlist 의 QGIS 도구 표면 78종(설계 E21).
#
# 분해: 포스처 R 읽기 41 + 포스처 W 변경 37. 적재 3종(add_vector_layer·
# add_raster_layer·create_layer_group)은 W 의 부분집합이라 합이 78 이다.
#
# `list_qgis_instances` 는 이 목록에 있으나 **QGIS 측 핸들러가 없다**(E22).
# 브리지가 로컬에서 답하므로 소켓에 오지 않는다. 그래도 남겨 두는 이유는
# allowlist 41종의 이름을 바꾸지 않기 위함이다(설계 4-4 끝).
EXPOSED_COMMANDS = frozenset({
    "add_features",
    "add_field",
    "add_raster_layer",
    "add_table_join",
    "add_vector_layer",
    "apply_style_qml",
    "commit_edits",
    "create_checkpoint",
    "create_layer_group",
    "create_memory_layer",
    "delete_features",
    "delete_field",
    "diagnose",
    "execute_processing",
    "field_calculator",
    "find_layer",
    "get_active_layer",
    "get_algorithm_help",
    "get_bookmarks",
    "get_canvas_extent",
    "get_canvas_scale",
    "get_edit_status",
    "get_field_statistics",
    "get_layer_crs",
    "get_layer_extent",
    "get_layer_features",
    "get_layer_labeling",
    "get_layer_tree",
    "get_layers",
    "get_layout_info",
    "get_map_themes",
    "get_message_log",
    "get_plugin_info",
    "get_processing_job",
    "get_processing_providers",
    "get_project_info",
    "get_project_variables",
    "get_qgis_info",
    "get_raster_info",
    "get_selection",
    "get_setting",
    "get_unique_values",
    "identify_features",
    "list_checkpoints",
    "list_connection_tables",
    "list_connections",
    "list_layouts",
    "list_plugins",
    "list_processing_algorithms",
    "list_processing_models",
    "list_qgis_instances",
    "move_layer_to_group",
    "ping",
    "raster_calculator",
    "remove_layer",
    "rename_field",
    "restore_checkpoint",
    "rollback_edits",
    "sample_raster_values",
    "save_project",
    "select_features",
    "set_active_layer",
    "set_layer_crs",
    "set_layer_labeling",
    "set_layer_order",
    "set_layer_property",
    "set_layer_style",
    "set_layer_visibility",
    "set_project_crs",
    "set_raster_style",
    "spatial_join",
    "start_editing",
    "transform_coordinates",
    "undo_edits",
    "update_feature_geometry",
    "update_features",
    "validate_expression",
    "zonal_statistics",
})

# 명시로 닫는 6종. **감산이 아니라 부재 단정**이다(설계 4-2) - 위 78종과의
# 교집합이 공집합임을 하네스가 단정하므로, 나중에 누가 78종을 늘릴 때 그
# 단정이 자동으로 다시 돈다.
#
# 앞 5종은 `posture.DISALLOWED_TOOLS` 와 같다(임의 코드·SQL·원격 레이어).
# `reload_plugin` 은 거기에 없고 **내장화가 만드는 새 위험**이다: 내장 서버에서
# 그 명령은 자기 숙주를 디스패치 도중에 재적재한다(자기 파괴). 상류에서는
# 서버가 다른 플러그인이었으므로 위험이 아니었다(설계 4-2·함정 5).
BLOCKED_COMMANDS = frozenset({
    "execute_code",
    "execute_sql",
    "execute_connection_sql",
    "import_layer_to_connection",
    "add_web_layer",
    "reload_plugin",
})


def is_exposed(name):
    """이 명령을 소켓에서 받아들이는가.

    `server._dispatch` 가 `COMMANDS` 멤버십 검사 **다음에** 부른다. 두 겹인
    이유는 상류 멤버십이 "핸들러가 존재하는가" 이고 이쪽이 "우리가 노출하기로
    했는가" 라서다 - 상류에 새 핸들러가 생겨도 자동으로 열리지 않는다.

    Args:
        name: 소켓에서 온 명령 이름. 신뢰할 수 없는 입력이라 타입을 본다.

    Returns:
        bool: 노출 집합에 있고 차단 목록에 없으면 True.
    """
    if not isinstance(name, str):
        return False
    return name in EXPOSED_COMMANDS and name not in BLOCKED_COMMANDS
