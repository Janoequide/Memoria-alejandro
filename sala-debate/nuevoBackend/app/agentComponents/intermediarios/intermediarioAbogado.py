from .base_intermediario import BaseIntermediario
from ..pipelines.abogadoPipeline import AbogadoPipeline
from ..factory_agents import ReActAgentFactory

class IntermediarioAbogado(BaseIntermediario):
    """
    Intermediario para el sistema "Abogado-del-Diablo".
    Usa los mismos agentes que Standard (Validador + Orientador),
    pero con prompts específicos orientados al cuestionamiento y desafío.
    """
    def __init__(self, prompts: dict, sio, sala, room_session_id, config_multiagente=None):
        super().__init__(sio, sala, room_session_id)
        
        # Los prompts deben venir de la BD con claves específicas del sistema "abogado-del-diablo"
        self.pipeLine = AbogadoPipeline(
            factory=ReActAgentFactory(),
            prompt_validador=prompts.get("Validador"),
            prompt_orientador=prompts.get("Orientador")
        )

    async def agregarMensage(self, userName, message, user_message_id):
        self.hubo_mensaje_desde_ultimo_callback = True

        # Reacción a mención @orientador
        if self.contiene_mencion_orientador(message):
            res = await self.pipeLine.reactiveResponse(userName, message)
            if res:
                self._insert_in_db("Orientador", res[0]["respuesta"])
            return res

        # Flujo estándar
        respuesta_pipeline = await self.pipeLine.entrar_mensaje_a_la_sala(username=userName, mensaje=message)
        if respuesta_pipeline:
            for r in respuesta_pipeline:
                self._insert_in_db(r["agente"], r["respuesta"], parent_id=user_message_id)
            return respuesta_pipeline
        return None