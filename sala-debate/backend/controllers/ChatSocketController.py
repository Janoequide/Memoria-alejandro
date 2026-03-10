import asyncio
from threading import Lock
from flask import request
from flask_socketio import join_room, leave_room, emit
from flask_socketio import SocketIO, join_room, leave_room, emit
from models.models import *
from agentsComponents.clases.intermediador import Intermediario

# Estructura: lobby_users[room][username] = set(socket_ids)
lobby_users: dict[str, set[str]] = {}  
_lobby_lock = Lock()    
def add_user(room: str, username: str, sid: str):
    """
    Agrega un usuario a la estructura de usuarios en el lobby.
    """
    with _lobby_lock:
        room_map = lobby_users.setdefault(room, {})
        sockets = room_map.setdefault(username, set())
        sockets.add(sid)

def remove_user(room: str, username: str, sid: str):
    with _lobby_lock:
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

def get_user_list(room: str):
    with _lobby_lock:
        room_map = lobby_users.get(room, {})
        return list(room_map.keys())


def emitir_resultado_socket(socketio: SocketIO, evento:str,resultado, sala:str):
    """Emitir resultados de intermediario de forma segura usando el contexto del servidor."""
    def _emit():
        try:
            socketio.emit(evento, resultado, room=sala)
        except Exception as e:
            print("Error emitiendo resultado desde background task:", e)
    # start_background_task corre la función en el contexto del servidor (thread/greenlet según async_mode)
    socketio.start_background_task(_emit)



def register_sockets(socketio,salas_activas):
# esta es la funcion para poder usar los socketsEvents  para el chat.
    usuarios_por_sala = {}  # {room_name: set(username1, username2, ...)}

    @socketio.on('join')
    def on_join(data):
        username = data['username']
        room = data['room']
        join_room(room)
        add_user(room, username, request.sid)
        emit('status', {'msg': f'{username} ha entrado a la sala {room}.'}, room=room)
        # Emitir la lista actualizada de usuarios a todos los del room
        emit('users_update', get_user_list(room), room=room)
        emit('users_update', get_user_list(room), to=request.sid)
    '''
    def on_join(data):
        username = data['username']
        room = data['room']
        
        intermediario:Intermediario = salas_activas.get(room)
        # Inicializar el set si no existe
        if room not in usuarios_por_sala:
            usuarios_por_sala[room] = set()
        join_room(room)

        if username not in usuarios_por_sala[room]:
            emit('status', {'msg': f'{username} ha entrado a la sala {room}.'}, room=room)
            #Avisamos al sistema multiagente que ha entrado un participante
            asyncio.run(intermediario.anunciar_entrada_participante(username))
        # Agregamos al usuario al set, el set no permite duplicados
        usuarios_por_sala[room].add(username)
        if intermediario:
            try:
                timer_state = {}
                if getattr(intermediario, "timer", None) is not None:
                    timer_state = intermediario.timer.get_state()
                # Emitir solo al socket que realizó el join (emit sin room => solo al emisor)
                emit('timer_user_update', {
                    "fase_actual": timer_state.get("fase_actual", 0),
                    "elapsed_phase": timer_state.get("elapsed_phase", 0),
                    "remaining_phase": timer_state.get("remaining_phase", 0)
                })
            except Exception as e:
                print("Error al enviar estado inicial del timer en on_join:", e)
    '''
    @socketio.on('disconnect')
    def on_disconnect():
        sid = request.sid
        # Buscar en qué sala y usuario estaba
        for room, users in list(lobby_users.items()):
            for username, sockets in list(users.items()):
                if sid in sockets:
                    remove_user(room, username, sid)
                    emit('status', {'msg': f'{username} se desconectó.'}, room=room)
                    emit('users_update', get_user_list(room), room=room)
                    break
    @socketio.on('leave')
    def on_leave(data):
        username = data['username']
        room = data['room']
        leave_room(room)
        remove_user(room, username, request.sid)

        intermediario: Intermediario = salas_activas.get(room)
        if intermediario:
            asyncio.run(intermediario.anunciar_salida_participante(username))

        # Emitir la lista actualizada de usuarios a todos los del room
        emit('users_update', get_user_list(room), room=room)

    @socketio.on('message')
    def handle_message(data):
        room = data['room']
        username = data['username']
        content = data['content']
        emit('message', {'username': username, 'content': content}, room=room)
        id_room_session = get_active_room_session_id(room)
        if not id_room_session:
            emit('error', {'msg': f"No hay sesión activa para la sala {room}"}, room=room)
            return
        user_message_id = insert_message(
            room_session_id=id_room_session,
            user_id=username,
            agent_name=None,
            sender_type=SenderType.user,
            content=content
        )

        intermediario: Intermediario = salas_activas.get(room)
        if not intermediario:
            emit('error', {'msg': 'La sala no está inicializada con agentes.'}, room=room)
            return
        intermediario.enqueue_message(username,content,user_message_id)


    @socketio.on('typing')
    def handle_typing(data):
        username = data['username']
        room = data['room']
        # Enviamos a todos los demás de la sala que este usuario está escribiendo
        emit('typing', {'username': username}, room=room, include_self=False)

    # Nuevo: cuando alguien deja de escribir
    @socketio.on('stop_typing')
    def handle_stop_typing(data):
        username = data['username']
        room = data['room']
        # Avisamos a todos los demás que este usuario dejó de escribir
        emit('stop_typing', {'username': username}, room=room, include_self=False)
    
    @socketio.on('subscribe_monitor')
    def handle_monitor_subscription(data):
        room = f"monitor_{data['room']}"
        join_room(room)
        emit('status',{'msg':f'Monitor susbrito a la sala {room}'})
    
    @socketio.on('unsubscribe_monitor')
    def handle_monitor_unsubscribe(data):
        room = f"monitor_{data['room']}"
        leave_room(f"monitor_{room}")

    @socketio.on('subscribe_timer_user')
    def handle_user_timer_subscription(data):
        room = data['room']
        join_room(room)
        emit('status',{'msg':f'Usuario suscrito al temporizador de {room}.'})
    '''
    @socketio.on("ready")
        def on_ready(data):
            username = data.get("username")
            room = data.get("room")

            if not username or not room:
                emit("error", {"msg": "Faltan datos de username/room"}, room=room)
                return

            sala_data = salas_activas.get(room)
            if not sala_data:
                emit("error", {"msg": "Sala no encontrada"}, room=room)
                return

            sala_data["ready_users"].add(username)
            emit("status", {"msg": f"{username} está listo "}, room=room)
            emit("ready_update", {"ready_users": list(sala_data["ready_users"])}, room=room)
    '''

    @socketio.on("start_session")
    def on_start_session(data):
        room = data.get("room")
        username = data.get("username")

        sala_data = salas_activas.get(room)
        if not sala_data:
            emit("error", {"msg": "Sala no encontrada"}, room=room)
            return

        if sala_data.get("active"):
            emit("status", {"msg": "La sala ya fue iniciada."}, room=room)
            return

        # opcional: verificar que haya al menos 2 listos o alguna condición
        if len(sala_data["ready_users"]) == 0:
            emit("status", {"msg": "No hay usuarios listos aún."}, room=room)
            return
        sala_data["active"] = True

        emit("status", {"msg": f"{username} ha iniciado la sesión 🟢"}, room=room)
        emit(
        "start_session",
        {
            "room": room,
            "users": list(sala_data["ready_users"])
        },
        room=room,
        )
        intermediario: Intermediario = salas_activas.get(room)
        if intermediario:
            try:
                timer_state = {}
                if getattr(intermediario, "timer", None) is not None:
                    timer_state = intermediario.timer.get_state()
                # Emitir solo al socket que realizó el join (emit sin room => solo al emisor)
                emit('timer_user_update', {
                    "fase_actual": timer_state.get("fase_actual", 0),
                    "elapsed_phase": timer_state.get("elapsed_phase", 0),
                    "remaining_phase": timer_state.get("remaining_phase", 0)
                })
            except Exception as e:
                print("Error al enviar estado inicial del timer en on_join:", e)
    

