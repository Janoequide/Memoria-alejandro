import asyncio
import socketio
from app.models.models import (
    get_active_room_session_id,
    insert_message,
    SenderType,
    add_participant_to_room,
    remove_participant_from_room,
    participant_exists_in_session
)
from app.agentComponents.intermediarios.base_intermediario import BaseIntermediario

# Estructura: lobby_users[room][username] = set(sid)
lobby_users: dict[str, dict[str, set[str]]] = {}
# Estructura: sid_to_participant[sid] = participant_id (para poder marcar como left)
sid_to_participant: dict[str, int] = {}
lobby_lock = asyncio.Lock()   
async def add_user(room: str, username: str, sid: str):
    """
    Agrega un usuario a la estructura de usuarios en el lobby.
    """
    async with lobby_lock:
        room_map = lobby_users.setdefault(room, {})
        sockets = room_map.setdefault(username, set())
        sockets.add(sid)

async def remove_user(room: str, username: str, sid: str):
    async with lobby_lock:
        room_map = lobby_users.get(room)
        if not room_map:
            return

        sockets = room_map.get(username)
        if not sockets:
            return

        sockets.discard(sid)
        if len(sockets) == 0:
            room_map.pop(username, None)

        if len(room_map) == 0:
            lobby_users.pop(room, None)

async def get_user_list(room: str):
    async with lobby_lock:
        room_map = lobby_users.get(room, {})
        return list(room_map.keys())


def register_sockets(sio:socketio.AsyncServer, salas_activas):
    """
    Registra todos los eventos de socket.io con versión ASGI/async.
    """
    @sio.event
    async def connect(sid, environ):
        print(f"Cliente conectado: {sid}")
    @sio.event
    async def disconnect(sid):
        # Marcar participante como salido en BD
        try:
            participant_id = sid_to_participant.get(sid)
            if participant_id:
                remove_participant_from_room(participant_id)
                del sid_to_participant[sid]
        except Exception as e:
            print(f"Error removiendo participante de BD: {str(e)}")
        
        # Buscamos en qué sala está este SID
        for room, users in list(lobby_users.items()):
            for username, sockets in list(users.items()):
                if sid in sockets:
                    await remove_user(room, username, sid)

                    await sio.emit(
                        "status",
                        {"msg": f"{username} se desconectó."},
                        room=room
                    )

                    updated = await get_user_list(room)
                    await sio.emit("users_update", updated, room=room)
                    break

        print("Cliente desconectado:", sid)

    @sio.on('join')
    async def on_join(sid, data):
        username = data['username']
        room = data['room']

        await sio.enter_room(sid, room)
        await add_user(room, username, sid)
        
        # Registrar participante en la BD SOLO si no está registrado
        try:
            session_id = get_active_room_session_id(room)
            if session_id:
                # Verificar si el participante ya existe
                if not participant_exists_in_session(session_id, username):
                    result = add_participant_to_room(
                        room_session_id=session_id,
                        username=username,
                        user_id=None
                    )
                    if result["success"] and result["participant_id"]:
                        sid_to_participant[sid] = result["participant_id"]
                    print(f"[DEBUG] Nuevo participante registrado: {username}")
                else:
                    print(f"[DEBUG] Participante ya existe: {username}, no se registra nuevamente")
        except Exception as e:
            print(f"Error registrando participante en BD: {str(e)}")
        
        await sio.emit(
            "status",
            {"msg": f"{username} ha entrado a la sala {room}."},
            room=room
        )
        updated = await get_user_list(room)
        await sio.emit("users_update", updated, room=room)
        await sio.emit("users_update", updated, to=sid)

    @sio.on("leave")
    async def on_leave(sid, data):
        username = data["username"]
        room = data["room"]

        # Marcar participante como salido en BD
        try:
            participant_id = sid_to_participant.get(sid)
            if participant_id:
                remove_participant_from_room(participant_id)
                del sid_to_participant[sid]
        except Exception as e:
            print(f"Error removiendo participante de BD: {str(e)}")

        await sio.leave_room(sid, room)
        await remove_user(room, username, sid)

        """
        # Avisar al Intermediario
        intermediario: Intermediario = salas_activas.get(room)
        if intermediario:
            await intermediario.anunciar_salida_participante(username)
        """
        updated = await get_user_list(room)
        await sio.emit("users_update", updated, room=room)

    @sio.on("message")
    async def handle_message(sid, data):
        room = data["room"]
        username = data["username"]
        content = data["content"]

        # Reemitir a la sala el mensaje crudo
        await sio.emit(
            "message",
            {"username": username, "content": content},
            room=room
        )

        # Guardar en DB
        id_room_session = get_active_room_session_id(room)
        if not id_room_session:
            await sio.emit(
                'error',
                {"msg": f"No hay sesión activa para la sala {room}"},
                room=room
            )
            return

        user_message_id = insert_message(
            room_session_id=id_room_session,
            user_id=username,
            agent_name=None,
            sender_type=SenderType.user,
            content=content
        )

        # Enviar al Intermediario
        intermediario: BaseIntermediario = salas_activas.get(room)
        if not intermediario:
            await sio.emit(
                "error",
                {"msg": "La sala no está inicializada con agentes."},
                room=room
            )
            return

        await intermediario.enqueue(username, content, user_message_id)


    @sio.on("typing")
    async def on_typing(sid, data):
        room = data["room"]
        username = data["username"]

        await sio.emit(
            "typing",
            {"username": username},
            room=room,
            skip_sid=sid
        )

    @sio.on("stop_typing")
    async def on_stop_typing(sid, data):
        room = data["room"]
        username = data["username"]

        await sio.emit(
            "stop_typing",
            {"username": username},
            room=room,
            skip_sid=sid
        )
    

        # Evento: start_session
    @sio.on("start_session")
    async def on_start_session(sid, data):
        room = data.get("room")
        username = data.get("username")

        sala_data = salas_activas.get(room)
        if not sala_data:
            await sio.emit("error", {"msg": "Sala no encontrada"}, room=room)
            return

        if sala_data.get("active"):
            await sio.emit("status", {"msg": "La sala ya fue iniciada."}, room=room)
            return

        # validar usuarios listos
        if len(sala_data.get("ready_users", [])) == 0:
            await sio.emit("status", {"msg": "No hay usuarios listos aún."}, room=room)
            return

        sala_data["active"] = True

        # mensaje de inicio
        await sio.emit(
            "status",
            {"msg": f"{username} ha iniciado la sesión 🟢"},
            room=room
        )

        # evento start_session para todos
        await sio.emit(
            "start_session",
            {
                "room": room,
                "users": list(sala_data["ready_users"])
            },
            room=room,
        )

        # enviar estado inicial del timer SOLO al que inició la sesión
        intermediario: BaseIntermediario = salas_activas.get(room)

        if intermediario:
            try:
                timer_state = {}
                if getattr(intermediario, "timer", None) is not None:
                    timer_state = intermediario.timer.get_state()

                # emit al usuario que ejecutó start_session
                await sio.emit(
                    "timer_user_update",
                    {
                        "fase_actual": timer_state.get("fase_actual", 0),
                        "elapsed_phase": timer_state.get("elapsed_phase", 0),
                        "remaining_phase": timer_state.get("remaining_phase", 0)
                    },
                    to=sid
                )
            except Exception as e:
                print("Error enviando estado inicial de timer:", e)

    

