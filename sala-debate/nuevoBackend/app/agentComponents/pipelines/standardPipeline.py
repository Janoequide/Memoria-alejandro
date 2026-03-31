import logging
from datetime import datetime
from .base_pipeline import BasePipeline
from ..utils.utilsForAgents import *
from agentscope.message import Msg
from agentscope.pipeline import MsgHub

logger = logging.getLogger("standard_pipeline")

class StandardPipeline(BasePipeline):
    INACTIVITY_THRESHOLD_SECONDS = 180  # 3 minutos sin enviar mensaje
    INACTIVITY_MENTION_COOLDOWN_SECONDS = 300  # 5 minutos entre avisos del mismo usuario
    INACTIVITY_MIN_RELATIVE_PARTICIPATION = 0.25  # si menos del 25% de la sala está activa, avisar

    def __init__(self, factory, prompt_validador, prompt_orientador):
        super().__init__(timeout=15)
        # Agentes específicos de este pipeline
        self.agenteValidador = factory.create_agent("Validador", prompt_validador)
        self.agenteOrientador = factory.create_agent("Orientador", prompt_orientador)
        self.agentes = [self.agenteValidador, self.agenteOrientador]

        # métricas de actividad de los usuarios (para no invasivo y llamadas de atención)
        self.usuarios_sala = []
        self.user_activity = {}  # nickname -> {'last_msg': datetime, 'count': int, 'last_alert': datetime|None}

    async def start_session(self, tema_sala: str, usuarios_sala: list, idioma: str):
        await self.set_hub(tema_sala, usuarios_sala, idioma)

        # Inicializar métricas de inactividad por usuario (nombres sanitizados)
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
        nombre_limpio = sanitize_name(username)
        msg = Msg(name=nombre_limpio, role='user', content=mensaje)

        # Actualizar estado de actividad del usuario
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

        # difundir el mensaje de usuario en el hub para que quede en el log
        await self._broadcast(msg)

        # Mantenimiento de inactividad: no tomar acción inmediata en cada mensaje, se evalúa en evento_timer.
        return await self.evaluar_intervencion_en_cascada(msg)

    async def evaluar_intervencion_en_cascada(self, mensaje: Msg):
        await self._broadcast(mensaje)
        # solicitar evaluación al Validador y difundir su mensaje para que quede en el historial
        res_val = await self._call_agent(self.agenteValidador, mensaje)
        if not isinstance(res_val, Msg):
            res_val = Msg(name=self.agenteValidador.name, role="assistant", content=self.ensure_text(res_val))
        await self._broadcast(res_val)
        texto_val = self.ensure_text(self.extract_content(res_val))
        
        # Extraer últimos 5 mensajes de usuario para mostrar qué evaluó el Validador
        mensajes_evaluados = self._get_recent_user_messages(n=5)
        
        respuestas = [{
            "agente": "Validador", 
            "respuesta": texto_val,
            "mensajes_evaluados": mensajes_evaluados
        }]
        
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
        # Requiere al menos 1 usuario activo para considerar interpelar a los inactivos
        if total == 0:
            return []

        activos = [u for u, s in self.user_activity.items() if (ahora - s.get('last_msg', ahora)).total_seconds() < self.INACTIVITY_THRESHOLD_SECONDS]
        if len(activos) < max(1, int(total * self.INACTIVITY_MIN_RELATIVE_PARTICIPATION)):
            # no hay suficiente actividad para hacer un llamado directo por usuario
            return []

        return inactivos

    async def _alertar_usuarios_inactivos(self) -> list | None:
        inactivos = self._users_inactive()
        if not inactivos:
            return None

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

        # Pedir al orientador que formule un mensaje suave de apoyo a la inclusión
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

        # Fallback si no hay agente orientador
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
        Tu mensaje debe ser conciso (máximo 3-4 oraciones) y estar en el idioma de la conversación.
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
        # Ir directo al mensaje genérico de estímulo sin la ruta extra de alerta de usuarios inactivos
        msg = Msg(
            name="Host",
            role="system",
            content=(
                "Se ha detectado inactividad general. Orientador: motiva la participación con una "
                "pregunta breve o pide profundizar un punto pendiente. No tomes postura."
            )
        )

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