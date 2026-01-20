from .intermediario import Intermediario
from .intermediarioToulmin import IntermediarioToulmin

INTERMEDIARIO_MAP = {
    "standard": Intermediario,
    "toulmin": IntermediarioToulmin,
    "abogado del diablo": Intermediario
}

def get_intermediario_class(pipeline_type: str):
    """Devuelve la clase del intermediario o la estándar por defecto."""
    return INTERMEDIARIO_MAP.get(pipeline_type.lower(), Intermediario)