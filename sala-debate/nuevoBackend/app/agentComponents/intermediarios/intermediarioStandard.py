from .base_intermediario import BaseIntermediario
from ..pipelines.standardPipeline import StandardPipeline
from ..factory_agents import ReActAgentFactory
import time
import logging

logger = logging.getLogger("intermediario_standard")

class IntermediarioStandard(BaseIntermediario):
    def __init__(self, prompts: dict, sio, sala, room_session_id, config_multiagente=None):
        super().__init__(sio, sala, room_session_id)
        
        self.pipeLine = StandardPipeline(
            factory=ReActAgentFactory(),
            prompt_validador=prompts.get("Validador"),
            prompt_orientador=prompts.get("Orientador")
        )
        # nombre de sala para los logs
        self.pipeLine.sala_name = sala

        # Estado del Cooldown para @orientador
        self.ultima_intervencion_ts = 0
        self.cooldown_actual = 60
        self.min_cooldown = 60
        self.max_cooldown = 600

    def puede_intervenir(self) -> bool:
        """Devuelve True si el tiempo de enfriamiento ha pasado."""
        return (time.time() - self.ultima_intervencion_ts) >= self.cooldown_actual

    async def agregarMensage(self, userName, message, user_message_id):
        self.hubo_mensaje_desde_ultimo_callback = True

        # Reacción a mención @orientador respeta cooldown
        if self.contiene_mencion_orientador(message):
            if not self.puede_intervenir():
                # Está en cooldown, ignorar mención
                tiempo_restante = int(self.cooldown_actual - (time.time() - self.ultima_intervencion_ts))
                print(f"\n⏳ COOLDOWN ACTIVO - No se puede invocar LLM. Tiempo restante: {tiempo_restante}s\n")
                logger.info(f"[{self.sala}] @orientador mencionado pero en cooldown (resto: {tiempo_restante}s)")
                return None
            
            res = await self.pipeLine.reactiveResponse(userName, message)
            if res:
                self._insert_in_db("Orientador", res[0]["respuesta"])
                self.ultima_intervencion_ts = time.time()  # Actualizar timestamp de intervención
            return res

        # Flujo estándar
        respuesta_pipeline = await self.pipeLine.entrar_mensaje_a_la_sala(username=userName, mensaje=message)
        if respuesta_pipeline:
            for r in respuesta_pipeline:
                self._insert_in_db(r["agente"], r["respuesta"], parent_id=user_message_id)
            return respuesta_pipeline
        return None