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
        window_size = config_multiagente.ventana_mensajes if config_multiagente else 5
        self.pipeLine = AbogadoPipeline(
            factory=ReActAgentFactory(),
            prompt_validador=prompts.get("Validador"),
            prompt_orientador=prompts.get("Orientador"),
            window_size=window_size
        )
        # Registrar callback para eventos de ventana
        self.pipeLine._on_window_event_callback = self._manejar_evento_ventana

    async def _manejar_evento_ventana(self, respuestas: list):
        """Maneja las respuestas cuando se dispara un evento de ventana."""
        if respuestas:
            for r in respuestas:
                self._insert_in_db(r["agente"], r["respuesta"])
            # Emitir las respuestas al frontend
            await self.sio.emit("evaluacion", respuestas, room=self.sala)

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