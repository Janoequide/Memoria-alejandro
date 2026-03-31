from .intermediarios.intermediarioStandard import IntermediarioStandard
from .intermediarios.intermediarioToulmin import IntermediarioToulmin
from .intermediarios.intermediarioAbogado import IntermediarioAbogado
from .intermediarios.intermediarioNoIA import IntermediarioNoIA

INTERMEDIARIO_MAP = {
    "standard": IntermediarioStandard,
    "toulmin": IntermediarioToulmin,
    "abogado-del-diablo": IntermediarioAbogado,
    "No_IA": IntermediarioNoIA
}

def get_intermediario_class(pipeline_type: str):
    """Devuelve la clase del intermediario o la estándar por defecto."""
    return INTERMEDIARIO_MAP.get(pipeline_type.lower(), IntermediarioStandard)