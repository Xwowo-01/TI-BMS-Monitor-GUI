"""CAN interface identifiers shared by settings, monitoring and flashing."""

VECTOR_VN1630A = 'vector_vn1630a'
VECTOR_VN1610 = 'vector_vn1610'
PCAN = 'pcan'

INTERFACES = (
    (VECTOR_VN1630A, 'Vector VN1630A'),
    (VECTOR_VN1610, 'Vector VN1610'),
    (PCAN, 'PCAN'),
)
VECTOR_HW_TYPES = {VECTOR_VN1630A: 57, VECTOR_VN1610: 55}


def normalize_interface(value):
    # Original settings only distinguished Vector from PCAN. Preserve that
    # configuration as VN1630A; changing card requires choosing its model.
    if value == 'vector':
        return VECTOR_VN1630A
    if value not in (VECTOR_VN1630A, VECTOR_VN1610, PCAN):
        raise ValueError(f'不支持的 CAN 接口：{value!r}')
    return value


def interface_name(value):
    return dict(INTERFACES)[normalize_interface(value)]


def vector_hw_type(value):
    return VECTOR_HW_TYPES.get(normalize_interface(value))
