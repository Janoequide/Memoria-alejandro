from .base_intermediario import BaseIntermediario
from .standardPipeline import StandardPipeline
from .factory_agents import ReActAgentFactory

class Intermediario(BaseIntermediario):
    def __init__(self, prompt_validador, prompt_orientador, sio, sala, room_session_id):
        super().__init__(sio, sala, room_session_id)
        self.pipeLine = StandardPipeline(
            factory=ReActAgentFactory(),
            prompt_validador=prompt_validador,
            prompt_orientador=prompt_orientador
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