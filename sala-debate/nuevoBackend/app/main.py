import socketio
import io
import matplotlib.pyplot as plt
from datetime import datetime
from uuid import UUID
from pathlib import Path
from fastapi import FastAPI,Request, Query
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv

# Cargar variables de entorno
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from app.controllers.ChatSocketController import register_sockets, get_user_list
from app.agentComponents.intermediarios.base_intermediario import BaseIntermediario
from app.agentComponents.registry import INTERMEDIARIO_MAP, get_intermediario_class
from app.models.models import (
    get_latest_room_statuses,
    get_or_create_Active_room_session,
    get_all_agents_by_pipeline,
    get_multiagent_config,
    close_active_room_session,
    get_temas,
    get_active_room_topic,
    get_rooms,
    get_active_room_session_id,
    get_messages_by_room,
    get_prompts_by_system,
    create_prompt_for_system,
    update_multiagent_config,
    get_all_session_days_from_db,
    get_sessions_by_day_from_db,
    get_messages_by_session_from_db,
    insert_tema,
    update_tema,
    create_room_names_batch,
    export_session_logs,
    add_participant_to_room,
    get_participants_count_for_active_rooms,
    get_room_with_least_participants,
    remove_participant_from_room,
    participant_exists_in_session
    )
from pydantic import BaseModel
from typing import Optional

class MultiAgentConfigSchema(BaseModel):
    ventana_mensajes: int
    fase_segundos: int
    update_interval: int
class TemaCreate(BaseModel):
    titulo: str
    tema_text: str

class TemaUpdate(BaseModel):
    id: int
    titulo: str
    tema_text: str


load_dotenv()
# Guardamos las salas activas , room_name -> Intermediario
salas_activas: dict[str, BaseIntermediario] = {}

# ---------------------------------------------------------
# 1) Crear servidor socket.io en modo ASGI (async nativo)
# ---------------------------------------------------------
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*"
)

# Adapter ASGI → permite montar socketio dentro de FastAPI
socket_app = socketio.ASGIApp(sio)

# ---------------------------------------------------------
# 2) Crear instancia FastAPI
# ---------------------------------------------------------
app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# 3) Registrar eventos de sockets
# ---------------------------------------------------------
register_sockets(sio, salas_activas)


# ---------------------------------------------------------
# 4) Montar socketio dentro de FastAPI
# ---------------------------------------------------------
# NOTA: /socket.io será manejado por python-socketio
app.mount("/socket.io", socket_app)


@app.get("/api/rooms/status")
def estado_salas():
    try:
        statuses = get_latest_room_statuses()
        return statuses
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rooms/{room_name}/sessions", status_code=201)
async def create_session(room_name: str, payload: dict):
    topic = payload.get("prompt_inicial")
    pipeline_type = payload.get("pipeline_type", "standard")

    room_session = get_or_create_Active_room_session(room_name, topic)
    if not room_session.get("primera_inicializacion", False):
        return {"status": "ya_inicializado"}

    current_prompts = get_prompts_by_system(pipeline_type)

    prompts_preparados = {k: v.replace("{tema}", topic) for k, v in current_prompts.items()}
    
    config_ma = get_multiagent_config()

    IntermediarioClass = get_intermediario_class(pipeline_type)
    
    intermediario = IntermediarioClass(
        prompts=prompts_preparados,
        sio=sio,
        sala=room_name,
        room_session_id=room_session["id"],
        config_multiagente=config_ma
    )

    salas_activas[room_name] = intermediario
    usuarios_sala = await get_user_list(room_name)
    
    await intermediario.start_session(topic, usuarios_sala, payload.get("idioma", "español"))
    await intermediario.start_timer(config_ma.fase_segundos, config_ma.update_interval)

    return {"status": "created", "room": room_name}

@app.post("/api/rooms/bulk", status_code=201)
async def create_rooms_bulk(payload: dict):
    """
    Crea y inicializa múltiples salas en un solo request.
    Payload: {quantity: int, base_name: str, topic: str, pipeline_type: str, idioma: str}
    """
    try:
        quantity = payload.get("quantity", 1)
        base_name = payload.get("base_name", "Sala")
        topic = payload.get("topic", "")
        pipeline_type = payload.get("pipeline_type", "standard")
        idioma = payload.get("idioma", "español")
        
        # Validar cantidad
        if not isinstance(quantity, int) or quantity < 1 or quantity > 20:
            raise HTTPException(status_code=400, detail="Quantity must be between 1 and 20")
        
        if not topic or not pipeline_type:
            raise HTTPException(status_code=400, detail="topic and pipeline_type are required")
        
        # Generar nombres de salas
        room_names = [f"{base_name}-{i}" for i in range(1, quantity + 1)]
        
        # Crear salas en la BD
        result = create_room_names_batch(room_names)
        
        # NUEVA: Inicializar cada sala creada
        created_rooms_initialized = []
        for room_name in [r["name"] for r in result["rooms_created"]]:
            try:
                # Obtener o crear sesión activa para la sala
                room_session = get_or_create_Active_room_session(room_name, topic)
                
                if not room_session.get("primera_inicializacion", False):
                    print(f"⚠️ Sala {room_name} ya tenía sesión activa, saltando")
                    continue
                
                # Obtener prompts según pipeline_type
                current_prompts = get_prompts_by_system(pipeline_type)
                prompts_preparados = {k: v.replace("{tema}", topic) for k, v in current_prompts.items()}
                
                # Obtener configuración multiagente
                config_ma = get_multiagent_config()
                
                # Crear instancia del intermediario
                IntermediarioClass = get_intermediario_class(pipeline_type)
                intermediario = IntermediarioClass(
                    prompts=prompts_preparados,
                    sio=sio,
                    sala=room_name,
                    room_session_id=room_session["id"],
                    config_multiagente=config_ma
                )
                
                # Guardar en diccionario de salas activas
                salas_activas[room_name] = intermediario
                
                # Obtener lista de usuarios en el lobby (probablemente vacía ahora)
                usuarios_sala = await get_user_list(room_name)
                
                # Iniciar sesión del intermediario
                await intermediario.start_session(topic, usuarios_sala, idioma)
                
                # Iniciar temporizador de turnos
                await intermediario.start_timer(config_ma.fase_segundos, config_ma.update_interval)
                
                created_rooms_initialized.append({
                    "name": room_name,
                    "status": "initialized",
                    "session_id": str(room_session["id"])
                })
                
                print(f"✓ Sala {room_name} inicializada correctamente")
                
            except Exception as e:
                print(f"✗ Error inicializando sala {room_name}: {str(e)}")
                created_rooms_initialized.append({
                    "name": room_name,
                    "status": "created_but_failed_init",
                    "error": str(e)
                })
        
        # Obtener lista actualizada de salas y estados
        statuses = get_latest_room_statuses()
        
        # Emitir a todos los clientes conectados
        await sio.emit("rooms_updated", statuses)
        
        return {
            "status": "created_and_initialized",
            "quantity_created": result["created"],
            "quantity_failed": result["failed"],
            "quantity_initialized": len([r for r in created_rooms_initialized if r.get("status") == "initialized"]),
            "rooms": created_rooms_initialized
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error creating rooms: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/rooms/{room_name}/sessions/active")
async def terminate_session(room_name: str):
    try:
        # Obtener ID de sesión activa ANTES de cerrar
        session_id = get_active_room_session_id(room_name)
        
        result = close_active_room_session(room_name)
        if not result:
            raise HTTPException(status_code=404, detail="No active session found")

        # Exportar logs automáticamente si tenemos session_id
        log_result = None
        if session_id:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            logs_dir = Path(__file__).parent / "logs"
            log_filepath = logs_dir / f"{room_name}_{timestamp}.json"
            
            log_result = export_session_logs(session_id, str(log_filepath))
            if log_result["success"]:
                print(f"✓ Logs exportados a: {log_result['filepath']}")
            else:
                print(f"✗ Error al exportar logs: {log_result['error']}")

        if room_name in salas_activas:
            await salas_activas[room_name].stop_session()
            del salas_activas[room_name]

        # Emitir evento Socket.io para notificar que se actualizó el estado de salas
        statuses = get_latest_room_statuses()
        await sio.emit("rooms_updated", statuses)

        return {
            "status": "terminated",
            "log_saved": log_result["success"] if log_result else False,
            "log_path": log_result["filepath"] if log_result else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/rooms")
def listar_salas():
    rooms = get_rooms()
    return rooms

@app.get("/api/rooms/{room_name}/messages")
def get_room_messages(room_name: str):

    id_session = get_active_room_session_id(room_name)

    if not id_session:
        raise HTTPException(status_code=404, detail="No hay sesión activa")

    messages = get_messages_by_room(id_session)

    return messages

@app.get("/api/rooms/{room_name}/timer")
async def get_room_timer(room_name: str):
    if room_name not in salas_activas:
        raise HTTPException(404, "Room not found or inactive")
    return salas_activas[room_name].get_timer_state()

@app.get("/api/prompts")
async def get_prompts(request: Request):
    """
    GET /api/prompts?pipeline=standard
    Devuelve los prompts del tipo de sistema seleccionado.
    """
    pipeline = request.query_params.get("pipeline", "standard")

    try:
        prompts = get_prompts_by_system(pipeline)
        return JSONResponse(prompts)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/prompts")
async def save_prompt(request: Request):
    """
    Guarda un nuevo prompt asociándolo al tipo de sistema (pipeline)
    Body esperado:
      { "agent_name": "...", "prompt": "texto..." }
    Header:
      X-Pipeline: standard | toulmin
    """
    pipeline = request.headers.get("X-Pipeline", "standard")

    try:
        payload = await request.json()

        if "agent_name" not in payload or "prompt" not in payload:
            raise HTTPException(status_code=400, detail="Formato inválido")

        agent_name = payload["agent_name"]
        prompt_text = payload["prompt"]

        create_prompt_for_system(agent_name, prompt_text, pipeline)

        return {"status": "ok"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/agents")
def get_agents(pipeline: str = Query("standard")):
    """
    Retorna los agentes disponibles filtrados por pipeline.
    """
    agents = get_all_agents_by_pipeline(pipeline)
    return {"agents": agents}

@app.get("/api/multiagent-config",response_model=MultiAgentConfigSchema)
def get_config():
    config = get_multiagent_config()
    if not config:
        raise HTTPException(status_code=404, detail="No existe configuración")
    return {
        "ventana_mensajes": config.ventana_mensajes,
        "fase_segundos": config.fase_segundos,
        "update_interval": config.update_interval
    }

@app.post("/api/multiagent-config",response_model=MultiAgentConfigSchema)
def post_config(data: MultiAgentConfigSchema):
    try:
        config = update_multiagent_config(
            ventana_mensajes=data.ventana_mensajes,
            fase_segundos=data.fase_segundos,
            update_interval=data.update_interval
        )
        return {
            "ventana_mensajes": config.ventana_mensajes,
            "fase_segundos": config.fase_segundos,
            "update_interval": config.update_interval
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@app.get("/api/sessions/days")
def get_all_session_days():
    try:
        days = get_all_session_days_from_db()
        return {"days": days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/by-day/{day}")
def get_sessions_by_day(day: str):
    """
    day = 'YYYY-MM-DD'
    """
    try:
        sessions = get_sessions_by_day_from_db(day)
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/messages/{session_id}")
def get_messages_by_session(session_id: UUID):
    try:
        msgs = get_messages_by_session_from_db(session_id)
        return {"messages": msgs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def generate_day_plot(day: str) -> io.BytesIO:
    # 1. Obtener sesiones del día
    sessions = get_sessions_by_day_from_db(day)
    if not sessions:
        raise ValueError("No hay sesiones para este día")

    plt.figure(figsize=(13, max(len(sessions) * 1.5, 4)))
    plt.title(f"Timeline de sesiones del día {day}")
    plt.xlabel("Timestamp")
    plt.ylabel("Sesiones")

    session_labels = []
    all_points = {"x": [], "y": [], "color": [], "marker": []}

    user_color = "blue"
    orientador_color = "orange"
    other_agents_color = "green"

    for idx, s in enumerate(sessions):
        created_at = s.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        session_labels.append(f"{s.room_name} ({created_at.strftime('%H:%M')})")

        msgs = get_messages_by_session_from_db(s.id)
        for m in msgs:
            ts = m["created_at"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)

            if m.get("agent_name") and m["agent_name"].lower() == "orientador":
                color = orientador_color
                marker = "o"
            elif m.get("agent_name"):
                color = other_agents_color
                marker = "s"
            else:
                color = user_color
                marker = "o"

            all_points["x"].append(ts)
            all_points["y"].append(idx)
            all_points["color"].append(color)
            all_points["marker"].append(marker)

    for x, y, c, m in zip(all_points["x"], all_points["y"], all_points["color"], all_points["marker"]):
        plt.scatter(x, y, color=c, marker=m, s=80, edgecolor="black" if m=="s" else "none")

    plt.yticks(range(len(session_labels)), session_labels)
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf

@app.get("/api/sessions/plot-day/{day}")
def plot_sessions_day(day: str):
    """
    Devuelve un gráfico PNG con todas las sesiones de un día.
    day = 'YYYY-MM-DD'
    """
    try:
        buf = generate_day_plot(day)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/topics")
def list_topics():
    return get_temas()

@app.get("/api/topics/{room}")
def obtener_tema(room: str):
    topic = get_active_room_topic(room)
    if topic is None:
        raise HTTPException(status_code=404, detail={"tema": "sin tema definido"})
    return {"tema": topic}

@app.post("/api/topics", status_code=201)
def create_topic(data: TemaCreate):
    topic_id = insert_tema(data.titulo, data.tema_text)
    return {"id": topic_id, "status": "created"}

@app.put("/api/topics/{topic_id}")
def update_topic_by_id(topic_id: int, data: TemaCreate):
    actualizado = update_tema(topic_id, data.titulo, data.tema_text)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"status": "updated"}

@app.get("/api/pipelines")
def get_pipelines():
    """
    Retorna la lista de identificadores de pipelines registrados
    para que el frontend pueda llenar un selector/dropdown.
    """
    return list(INTERMEDIARIO_MAP.keys())


# ==================== ENDPOINTS PARA DISTRIBUCION AUTOMATICA ====================

@app.get("/api/rooms/participants/count")
def get_participants_count():
    """
    Obtiene el conteo de participantes activos por cada sala.
    Retorna lista: [{room_name, session_id, participants_count}, ...]
    """
    try:
        counts = get_participants_count_for_active_rooms()
        return {"rooms": counts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AutoJoinRequest(BaseModel):
    username: str
    user_id: Optional[int] = None  # Opcional

@app.post("/api/rooms/auto-join")
def auto_join_room(request: AutoJoinRequest):
    """
    Sirve automáticamente al usuario a la sala con menos participantes.
    Si hay múltiples salas con el mismo mínimo, retorna la de menor índice.
    Retorna: {room_name, session_id, participants_count}
    Si no hay salas activas, retorna error 404.
    """
    try:
        best_room = get_room_with_least_participants()
        
        if not best_room:
            raise HTTPException(
                status_code=404,
                detail="No open rooms available"
            )
        
        # Agregar participante a la BD
        result = add_participant_to_room(
            room_session_id=best_room["session_id"],
            username=request.username,
            user_id=request.user_id
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=f"Error adding participant: {result['error']}"
            )
        
        return {
            "room_name": best_room["room_name"],
            "session_id": best_room["session_id"],
            "participants_count": best_room["participants_count"],
            "participant_id": result["participant_id"]
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))