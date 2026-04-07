from .base_intermediario import BaseIntermediario
from ..pipelines.abogadoPipeline import AbogadoPipeline
from ..factory_agents import ReActAgentFactory
import time
import logging

logger = logging.getLogger("intermediario_abogado")

class IntermediarioAbogado(BaseIntermediario):
    """
    Intermediario para el sistema "Abogado-del-Diablo".
    Usa los mismos agentes que Standard (Validador + Orientador),
    pero con prompts específicos orientados al cuestionamiento y desafío.
    """
    def __init__(self, prompts: dict, sio, sala, room_session_id, config_multiagente=None):
        super().__init__(sio, sala, room_session_id)
        
        # Nombre personalizado del orientador para AbogadoPipeline
        self.nombre_orientador = "Abogado-Del-Diablo"
        
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
            
            # Transformar respuestas con nombre personalizado y debug payload
            respuestas_transformadas = self._transformar_respuestas(respuestas)
            await self.sio.emit("evaluacion", respuestas_transformadas, room=self.sala)

            # Si la IA intervino, recalculamos el cooldown dinámico
            if orientador_hablo:
                # Obtenemos la ventana actual directamente del pipeline
                mensajes_ventana = getattr(self.pipeLine, '_window_buffer', [])
                self.cooldown_actual = self.calcular_cooldown_dinamico(mensajes_ventana)
                self.ultima_intervencion_ts = time.time()
                print(f"\n✓ LLM LLAMADA EXITOSA - Cooldown actualizado: {int(self.cooldown_actual)}s\n")

    def _transformar_respuestas(self, respuestas: list) -> list:
        """Transforma respuestas para incluir nombre personalizado y debug payload."""
        if not respuestas:
            return []
        
        respuestas_transformadas = []
        for r in respuestas:
            agente_nombre = self.nombre_orientador if r.get("agente", "").lower() == "orientador" else r.get("agente")
            payload = {
                "agente": agente_nombre,
                "respuesta": r.get("respuesta"),
                "debug": agente_nombre.lower() not in ["orientador", "abogado-del-diablo"]  # debug=True si es Validador, False si es Abogado-Del-Diablo/Orientador
            }
            if "mensajes_evaluados" in r:
                payload["mensajes_evaluados"] = r["mensajes_evaluados"]
            respuestas_transformadas.append(payload)
        return respuestas_transformadas

    async def agregarMensage(self, userName, message, user_message_id):
        self.hubo_mensaje_desde_ultimo_callback = True

        # Menciones a @orientador respetan el cooldown
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
                self.ultima_intervencion_ts = time.time() # Reseteamos tras hablar
                return self._transformar_respuestas(res)
            return None

        # Flujo estándar: Siempre alimentar al pipeline para que la ventana avance
        # El Pipeline internamente consultará 'puede_intervenir' antes de evaluar.
        res = await self.pipeLine.entrar_mensaje_a_la_sala(username=userName, mensaje=message)
        return self._transformar_respuestas(res) if res else None

    def calcular_cooldown_dinamico(self, mensajes_recientes):
        """Ajustado para procesar objetos Msg de Agentscope."""
        if not mensajes_recientes: return self.min_cooldown
        
        # Extraemos autores y contenido de los objetos Msg
        autores_unicos = len(set(getattr(m, 'name', 'anon') for m in mensajes_recientes))
        total_palabras = sum(len(str(getattr(m, 'content', '')).split()) for m in mensajes_recientes)
        
        # +60s por autor, +30s por cada 50 palabras
        nuevo_cooldown = (autores_unicos * 60) + (total_palabras // 50 * 30)
        return max(self.min_cooldown, min(nuevo_cooldown, self.max_cooldown))