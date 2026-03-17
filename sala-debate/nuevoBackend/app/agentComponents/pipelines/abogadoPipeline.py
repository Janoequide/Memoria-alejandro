import logging
from datetime import datetime
from .base_pipeline import BasePipeline
from ..utils.utilsForAgents import *
from agentscope.message import Msg
from agentscope.pipeline import MsgHub

logger = logging.getLogger("abogado_pipeline")

class AbogadoPipeline(BasePipeline):
    """
    Pipeline del sistema "Abogado-del-Diablo".
    Estructura idéntica al StandardPipeline (2 agentes: Validador + Orientador),
    pero orientado a cuestionar y desafiar argumentos.
    
    La diferencia principal está en los prompts que recibe de la BD,
    que deben estar diseñados para fomentar el pensamiento crítico y la contraargumentación.
    """
    INACTIVITY_THRESHOLD_SECONDS = 60 # Definir a un usuario como inactivo
    INACTIVITY_MENTION_COOLDOWN_SECONDS = 75 #Si fue mencionado como inactivo, en "x" segundos se volverá a contar como inactivo
    INACTIVITY_MIN_RELATIVE_PARTICIPATION = 0.0

    def __init__(self, factory, prompt_validador, prompt_orientador, window_size: int = 5):
        super().__init__(timeout=15)
        # Agentes específicos de este pipeline
        self.agenteValidador = factory.create_agent("Validador", prompt_validador)
        self.agenteOrientador = factory.create_agent("Orientador", prompt_orientador)
        self.agentes = [self.agenteValidador, self.agenteOrientador]

        # métricas de actividad de los usuarios (inactividad + invitados suaves)
        self.usuarios_sala = []
        self.user_activity = {}

        # Ventanas de mensajes: buffer deslizante con tamaño configurable.
        # Cuando el buffer alcanza `window_size` se dispara `evento_ventana`
        self.window_size = window_size
        self._window_buffer = []
        # Callback para notificar al intermediario cuando se dispara la ventana
        self._on_window_event_callback = None
        # Callback para ver el cooldown
        self.check_cooldown_callback = None

    async def start_session(self, tema_sala: str, usuarios_sala: list, idioma: str):
        await self.set_hub(tema_sala, usuarios_sala, idioma)

        # Inicializar seguimiento de actividad de usuarios
        self.usuarios_sala = [sanitize_name(u) for u in (usuarios_sala or [])]
        ahora = datetime.now()
        self.user_activity = {
            u: {
                'last_msg': ahora,
                'count': 0,
                'last_alert': None
            }
            for u in self.usuarios_sala
        }

        # Lógica de bienvenida
        mensaje = Msg(name="Host", role="system", content="Sesión iniciada. Orientador, explica el objetivo.")
        await self._broadcast(mensaje)
        res = await self._call_agent(self.agenteOrientador)

        return [{"agente": "Orientador", "respuesta": self.ensure_text(self.extract_content(res))}]

    async def entrar_mensaje_a_la_sala(self, username: str, mensaje: str):
        """
        Flujo de mensaje: difunde el mensaje y lo añade a la ventana.
        La evaluación/intervención ocurre solo cuando la ventana se llena,
        no por cada mensaje individual.
        """

        nombre_limpio = sanitize_name(username)
        msg = Msg(name=nombre_limpio, role='user', content=mensaje)

        # Actualizar actividad del usuario
        ahora = datetime.now()
        if nombre_limpio not in self.user_activity:
            self.user_activity[nombre_limpio] = {
                'last_msg': ahora,
                'count': 1,
                'last_alert': None
            }
            if nombre_limpio not in self.usuarios_sala:
                self.usuarios_sala.append(nombre_limpio)
        else:
            self.user_activity[nombre_limpio]['last_msg'] = ahora
            self.user_activity[nombre_limpio]['count'] += 1

        await self._broadcast(msg)

        # Añadir a la ventana y disparar evento si se completa
        await self._add_to_window(msg)

        # Devolver confirmación vacía: la evaluación ocurre internamente en _add_to_window
        return []

    async def _add_to_window(self, msg: Msg):
        """
        Añade un mensaje al buffer de la ventana y dispara `evento_ventana`
        cuando se alcanza `self.window_size`.
        El buffer funciona de forma deslizante (pop por la izquierda).
        """
        self._window_buffer.append(msg)
        # Mantener tamaño deslizante
        if len(self._window_buffer) > self.window_size:
            self._window_buffer.pop(0)

        # Disparar evento cuando se alcanza exactamente el tamaño de ventana
        if len(self._window_buffer) == self.window_size:
            if self.check_cooldown_callback and not self.check_cooldown_callback():
                print("Estoy en cooldown!!!!!!!!!!!")
                # Si hay cooldown, NO evaluamos y NO vaciamos el buffer.
                # Así, el próximo mensaje que llegue volverá a intentar disparar la ventana.
                logger.info("[Ventana] Evaluación pospuesta por Cooldown activo.")
                return
            try:
                logger.info(f"[Ventana completa] Se disparó evento_ventana con {self.window_size} mensajes")
                # Construir un mensaje-síntesis indicando que la ventana se completó
                contenido = (
                    f"Se ha alcanzado una ventana de {self.window_size} mensajes. "
                    "Por favor, el agente Validador evalúe si es necesario intervenir.\n"
                    "Últimos mensajes:\n"
                )
                for m in self._window_buffer:
                    contenido += f"- {getattr(m, 'name', 'anon')} : {str(m.content)}\n"

                msg_ventana = Msg(name="host", role="system", content=contenido)
                # Ejecutar la evaluación de ventana (cascada) - devuelve respuestas de agentes
                respuestas = await self.evaluar_intervencion_en_cascada(msg_ventana)
                logger.info(f"[Ventana] Respuestas obtenidas: {len(respuestas)} agentes respondieron")
                
                # Notificar al intermediario si hay un callback
                if self._on_window_event_callback:
                    await self._on_window_event_callback(respuestas)
                
                # Limpiar la ventana después de procesar
                self._window_buffer.clear()
            except Exception as e:
                logger.exception(f"Error al procesar evento de ventana: {e}")

    async def evaluar_intervencion_en_cascada(self, mensaje: Msg):
        await self._broadcast(mensaje)

        res_val = await self._call_agent(self.agenteValidador, mensaje)
        if not isinstance(res_val, Msg):
            res_val = Msg(name=self.agenteValidador.name, role="assistant", content=self.ensure_text(res_val))

        extra = self._inactive_followup_text()
        if extra:
            res_val = Msg(name=res_val.name, role=res_val.role, content=f"{self.ensure_text(res_val.content)}{extra}")

        await self._broadcast(res_val)
        texto_val = self.ensure_text(self.extract_content(res_val))

        respuestas = [{"agente": "Validador", "respuesta": texto_val}]

        if filter_agents(texto_val, self.agentes):
            res_ori = await self._call_agent(self.agenteOrientador)
            if not isinstance(res_ori, Msg):
                res_ori = Msg(name=self.agenteOrientador.name, role="assistant", content=self.ensure_text(res_ori))


            await self._broadcast(res_ori)
            respuestas.append({"agente": "Orientador", "respuesta": self.ensure_text(self.extract_content(res_ori))})

        return respuestas

    def _users_inactive(self) -> list:
        ahora = datetime.now()
        inactivos = []
        total = len(self.user_activity)

        for usuario, stats in self.user_activity.items():
            diff = (ahora - stats.get('last_msg', ahora)).total_seconds()
            if diff >= self.INACTIVITY_THRESHOLD_SECONDS:
                cooldown = stats.get('last_alert')
                if cooldown is None or (ahora - cooldown).total_seconds() >= self.INACTIVITY_MENTION_COOLDOWN_SECONDS:
                    inactivos.append(usuario)

        if total == 0:
            return []

        activos = [u for u, s in self.user_activity.items() if (ahora - s.get('last_msg', ahora)).total_seconds() < self.INACTIVITY_THRESHOLD_SECONDS]

        if self.INACTIVITY_MIN_RELATIVE_PARTICIPATION <= 0:
            min_activos = 0
        else:
            min_activos = max(1, int(total * self.INACTIVITY_MIN_RELATIVE_PARTICIPATION))

        if len(activos) < min_activos:
            # no hay suficiente participación para hacer llamadas individuales
            return []

        return inactivos

    def _inactive_followup_text(self) -> str:
        inactivos = self._users_inactive()
        if not inactivos:
            return ""

        menciones = ", ".join(f"@{u}" for u in inactivos)
        return (
            "\n\n💬 _Incluyamos a quienes han hablado menos:_ "
            f"{menciones}. "
            "Invitalos a participar, menciona a algunos por nombre pidiendo su opinion/postura"
        )

    async def _alertar_usuarios_inactivos(self) -> list | None:
        inactivos = self._users_inactive()
        if not inactivos:
            return None
        print("INACTIVOOOO")
        for u in inactivos:
            self.user_activity[u]['last_alert'] = datetime.now()

        menciones = ", ".join(f"@{u}" for u in inactivos)
        mensaje = (
            "__Recordatorio de inclusión:__ "
            "Para equilibrar la conversación, sería muy valioso que los siguientes participantes compartan su punto de vista: "
            f"{menciones}. "
            "No es una crítica; es una invitación breve y respetuosa."
        )

        msg_alerta = Msg(name="Host", role="system", content=mensaje)
        await self._broadcast(msg_alerta)

        if self.agenteOrientador:
            prompt = (
                "A partir del siguiente estado, genera un mensaje motivador y suave. "
                "No seas intrusivo, no obligues. Enfócate en animar la participación.\n"
                f"Usuarios a mencionar: {menciones}.\n"
                "Tu respuesta debe ser breve (1-2 oraciones)."
            )
            directive = Msg(name="Host", role="system", content=prompt)
            await self._broadcast(directive)
            resp_ori = await self._call_agent(self.agenteOrientador, directive)
            if resp_ori:
                if not isinstance(resp_ori, Msg):
                    resp_ori = Msg(name=self.agenteOrientador.name, role="assistant", content=self.ensure_text(resp_ori))
                await self._broadcast(resp_ori)
                return [{"agente": "Orientador", "respuesta": self.ensure_text(self.extract_content(resp_ori))}]

        return [{"agente": "Host", "respuesta": mensaje}]

    async def mensaje_hito_temporal(self, hito: int, mensaje_base: str, elapsed_time: int, remaining_time: int):
        """
        Genera una instrucción para que el Orientador reaccione a un hito (25%, 50%, etc.).
        """
        instruccion = f"""
        **HITO TEMPORAL ALCANZADO: {hito}% del tiempo completado**
        Tiempo transcurrido: {self.formato_tiempo(elapsed_time)}
        Tiempo restante: {self.formato_tiempo(remaining_time)}
        {mensaje_base}
        
        Por favor, como Orientador:
        1. Haz una breve reflexión sobre el progreso del debate hasta ahora
        2. Motiva a los participantes según el momento de la sesión
        3. Da recomendaciones específicas para aprovechar el tiempo {"restante" if hito < 100 else "que tuvieron"}
        4. Debes ser crítico con el avance. Si no han avanzado lo suficiente, indícaselo a los participantes.
        5. Debes indicarle en que momento de la sesión se encuentran (inicio, mitad, casi finalizado, finalización).
        Tu mensaje debe ser conciso (máximo una oración) y estar en el idioma de la conversación.
        """

        msg_hito = Msg(name="Host", role="system", content=instruccion)

        try:
            # Informamos a la sala sobre el hito
            await self._broadcast(msg_hito)
            
            # Solicitamos la respuesta específica del Orientador
            agente_orientador = next((a for a in self.agentes if a.name == "Orientador"), None)
            if not agente_orientador:
                return [{"agente": "Orientador", "respuesta": mensaje_base}]

            respuesta = await self._call_agent(agente_orientador, msg_hito)
            if not isinstance(respuesta, Msg):
                respuesta = Msg(name=self.agenteOrientador.name, role="assistant", content=self.ensure_text(respuesta))
            await self._broadcast(respuesta)
            texto = self.ensure_text(self.extract_content(respuesta))
            
            return [{"agente": "Orientador", "respuesta": texto or mensaje_base}]
            
        except Exception as e:
            logger.error(f"[Error hito temporal]: {e}")
            return [{"agente": "Orientador", "respuesta": mensaje_base}]

    async def evento_timer(self):
        """
        Intervención por inactividad: el Orientador motiva la participación.
        """
        msg = Msg(
            name="Host",
            role="system",
            content=(
                "Se ha detectado inactividad. Orientador: motiva la participación con una "
                "pregunta breve o pide profundizar un punto pendiente. No tomes postura."
                "Tu mensaje debe ser conciso (máximo una oración) y estar en el idioma de la conversación."
            )
        )
        
        # Siempre ir directo al Orientador para motivar la participación sin rutinas adicionales.
        await self._broadcast(msg)
        
        agente_orientador = next((a for a in self.agentes if a.name == "Orientador"), None)
        if agente_orientador:
            respuesta = await self._call_agent(agente_orientador, msg)
            if not isinstance(respuesta, Msg):
                respuesta = Msg(name=self.agenteOrientador.name, role="assistant", content=self.ensure_text(respuesta))
            await self._broadcast(respuesta)
            return [{
                "agente": "Orientador", 
                "respuesta": self.ensure_text(self.extract_content(respuesta))
            }]
        return []