"""Enum canónico de tipos PII — fuente única (SPEC 7, FORMATS-SPEC 9).

El gateway (Slice 1) y el meta-schema de formatos deben coincidir con esta lista.
`make validate-formats` cruza cada `pii_tipo` de formats/*.yaml contra este enum.
"""

from enum import Enum


class PIIType(str, Enum):
    NOMBRE_NNA = "NOMBRE_NNA"
    NOMBRE_ADULTO = "NOMBRE_ADULTO"
    DNI = "DNI"
    DIRECCION = "DIRECCION"
    DISTRITO = "DISTRITO"
    TELEFONO = "TELEFONO"
    EDAD = "EDAD"
    FECHA_NAC = "FECHA_NAC"
    CORREO = "CORREO"
    INSTITUCION = "INSTITUCION"
    CENTRO_SALUD = "CENTRO_SALUD"


PII_TYPES: frozenset[str] = frozenset(t.value for t in PIIType)
