from .base_intermediario import BaseIntermediario
from ..pipelines.abogadoPipeline import AbogadoPipeline
from ..factory_agents import ReActAgentFactory
import time

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
        # salvar nombre de sala en pipeline para exportaciones
        self.pipeLine.sala_name = sala
        # Sincronizamos el Pipeline con el estado del Intermediario
        self.pipeLine._on_window_event_callback = self._manejar_evento_ventana
        self.pipeLine.check_cooldown_callback = self.puede_intervenir # Nueva función de chequeo

        # Estado del Cooldown
        self.ultima_intervencion_ts = 0
        self.cooldown_actual = 60
        self.min_cooldown = 60
        self.max_cooldown = 600

    def puede_intervenir(self) -> bool:
        """Devuelve True si el tiempo de enfriamiento ha pasado."""
        return (time.time() - self.ultima_intervencion_ts) >= self.cooldown_actual

    async def _manejar_evento_ventana(self, respuestas: list):
        """Se ejecuta cuando la ventana del Pipeline se completa y los agentes responden."""
        if respuestas:
            # ¿El Orientador realmente intervino? (No solo el Validador analizando)
            orientador_hablo = any(r["agente"] == "Orientador" for r in respuestas)
            
            for r in respuestas:
                self._insert_in_db(r["agente"], r["respuesta"])
            
            await self.sio.emit("evaluacion", respuestas, room=self.sala)

            # Si la IA intervino, recalculamos el cooldown dinámico
            if orientador_hablo:
                # Obtenemos la ventana actual directamente del pipeline
                mensajes_ventana = getattr(self.pipeLine, '_window_buffer', [])
                self.cooldown_actual = self.calcular_cooldown_dinamico(mensajes_ventana)
                self.ultima_intervencion_ts = time.time()
                print(f"--- Cooldown actualizado: {int(self.cooldown_actual)}s ---")

    async def agregarMensage(self, userName, message, user_message_id):
        self.hubo_mensaje_desde_ultimo_callback = True

        # Menciones: Saltan el cooldown por ser órdenes directas
        if self.contiene_mencion_orientador(message):
            res = await self.pipeLine.reactiveResponse(userName, message)
            if res:
                self._insert_in_db("Orientador", res[0]["respuesta"])
                self.ultima_intervencion_ts = time.time() # Reseteamos tras hablar
            return res

        # Flujo estándar: Siempre alimentar al pipeline para que la ventana avance
        # El Pipeline internamente consultará 'puede_intervenir' antes de evaluar.
        return await self.pipeLine.entrar_mensaje_a_la_sala(username=userName, mensaje=message)

    def calcular_cooldown_dinamico(self, mensajes_recientes):
        """Ajustado para procesar objetos Msg de Agentscope."""
        if not mensajes_recientes: return self.min_cooldown
        
        # Extraemos autores y contenido de los objetos Msg
        autores_unicos = len(set(getattr(m, 'name', 'anon') for m in mensajes_recientes))
        total_palabras = sum(len(str(getattr(m, 'content', '')).split()) for m in mensajes_recientes)
        
        # +60s por autor, +30s por cada 50 palabras
        nuevo_cooldown = (autores_unicos * 60) + (total_palabras // 50 * 30)
        return max(self.min_cooldown, min(nuevo_cooldown, self.max_cooldown))