from .intermediarios.intermediarioStandard import IntermediarioStandard
from .intermediarios.intermediarioToulmin import IntermediarioToulmin

INTERMEDIARIO_MAP = {
    "standard": IntermediarioStandard,
    "toulmin": IntermediarioToulmin,
    "abogado del diablo": IntermediarioStandard
}

def get_intermediario_class(pipeline_type: str):
    """Devuelve la clase del intermediario o la estándar por defecto."""
    return INTERMEDIARIO_MAP.get(pipeline_type.lower(), IntermediarioStandard)