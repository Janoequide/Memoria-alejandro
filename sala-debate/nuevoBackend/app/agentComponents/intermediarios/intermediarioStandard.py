from .base_intermediario import BaseIntermediario
from ..pipelines.standardPipeline import StandardPipeline
from ..factory_agents import ReActAgentFactory
class IntermediarioStandard(BaseIntermediario):
    def __init__(self, prompts: dict, sio, sala, room_session_id, config_multiagente=None):
        super().__init__(sio, sala, room_session_id)
        
        self.pipeLine = StandardPipeline(
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