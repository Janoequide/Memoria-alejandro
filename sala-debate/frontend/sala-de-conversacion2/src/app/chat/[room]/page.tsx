'use client'

import { useParams, useRouter} from 'next/navigation'
import { useEffect, useState, useRef } from 'react'
import { io, Socket } from 'socket.io-client'

export default function ChatRoom() {
  type ChatMessage = {
    username?: string;
    content: string;
    system?: boolean;
  };
  
  type EvaluacionData = {
    agente: string;
    respuesta: string;
  };
  const [showMentionBar, setShowMentionBar] = useState(false)
  const [mentionTarget, setMentionTarget] = useState<string | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(0)
  const [remainingTime, setRemainingTime] = useState<number>(0)

  const [isTimerRunning, setIsTimerRunning] = useState(false);
  const params = useParams()
  const room = params.room as string
  const router = useRouter()
  const [evaluaciones, setEvaluaciones] = useState<string[]>([])
  const [username, setUsername] = useState('')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<{ username?: string; content: string; system?: boolean }[]>([])
  const [joined, setJoined] = useState(false)
  const socketRef = useRef<Socket | null>(null)
  const [tema, setTema] = useState('')
  const [agentMessages, setAgentMessages] = useState<ChatMessage[]>([])
  const [typingUsers,setTypingUsers] = useState<string[]>([])
  const chatContainerRef = useRef<HTMLDivElement | null>(null); 

  const backend = process.env.NEXT_PUBLIC_BACKEND_URL;
  useEffect(() => {
    const saved = sessionStorage.getItem('chatUser')
    if (!saved) {
      router.push(`/chat/${room}/lobby`)
      return
    }
    try {
      const parsed = JSON.parse(saved)
      if (!parsed || parsed.room !== room) {
        router.push(`/chat/${room}/lobby`)
      }
    } catch (e) {
      router.push(`/chat/${room}/lobby`)
    }
  }, [room, router])
  
  useEffect(() => {
    fetch(`${backend}/api/topics/${room}`)
    .then((res) => res.json())
    .then((data) => setTema(data.tema))
  }, [room])
// Hook para cargar mensajes históricos al unirse
useEffect(() => {
  if (!joined || !username) return;

  const fetchHistoricalMessages = async () => {
    try {
      const res = await fetch(`${backend}/api/rooms/${room}/messages`);
      if (!res.ok) return; // si no hay mensajes o error, no hacemos nada

      const data: {
        username?: string;
        content: string;
        system?: boolean;
        agente?: string;
        intervencion?: string;
        timestamp?: string;
      }[] = await res.json();

      if (!data || data.length === 0) return;

      // Separar mensajes de agentes y normales
      const normalMessages: ChatMessage[] = [];
      const agentMsgs: ChatMessage[] = [];

      data.forEach((m) => {
        if (m.agente) {
          // Curador -> panel de agentes
          if (m.agente.toLowerCase() === 'curador') {
            agentMsgs.push({ username: m.agente, content: m.content });
          } else {
            // Orientador -> chat normal
            normalMessages.push({ username: m.agente, content: m.content });
          }
        } else {
          // Mensajes históricos normales
          const isOwn = m.username === username; // Si coincide con el usuario actual
          normalMessages.push({
            username: m.username,
            content: m.content,
            system: m.system,
          });
        }
      });

      // Actualizar estado
      setMessages((prev) => [...normalMessages, ...prev]);
      setAgentMessages((prev) => [...agentMsgs, ...prev]);
    } catch (error) {
      console.error('Error al cargar mensajes históricos:', error);
    }
  };

  fetchHistoricalMessages();
}, [joined, room, backend, username]);


  // Inicializa el socket una sola vez
  useEffect(() => {
    socketRef.current = io(backend, {
      path: '/socket.io',
      transports: ['websocket'],
    });

    const socket = socketRef.current

    const handleMessage = (msg: ChatMessage) => {
      setMessages((prev) => [...prev, msg])
    }

    const handleStatus = (statusMsg: {msg:string}) => {
      setMessages((prev) => [...prev, { content: statusMsg.msg, system: true }])
    }

    const handleEvaluacion = (data: EvaluacionData[]|EvaluacionData) => {
      const mensajes = Array.isArray(data) ? data : [data];

      mensajes.forEach(({agente, respuesta}) => {
        if (!respuesta?.trim()) return;
    
        if (agente.toLowerCase() === "orientador") {
          //orientador -> chat general
          setMessages((prev) => [...prev, { username: agente, content: respuesta }]);
        } 
        // curador -> va al panel de agentes
        else if (agente.toLowerCase() === "curador") {
          setAgentMessages((prev) => [...prev, { username: agente, content: respuesta }]);
        }
        else if (agente.toLowerCase() === "resumidor") {
          // Resumidor -> chat general 
          setMessages((prev) => [...prev, { username: agente, content: respuesta }]);
        }
      })
    };

    // usuarios que escriben
    socket.on('typing', (data: { username: string }) => {
      setTypingUsers((prev) => {
        if (!prev.includes(data.username)) {
          return [...prev, data.username]
        }
        return prev
      })
    })

    socket.on('stop_typing', (data: { username: string }) => {
      setTypingUsers((prev) => prev.filter((u) => u !== data.username))
    })

    
    socket.on('message', handleMessage)
    socket.on('status', handleStatus)
    socket.on('evaluacion', handleEvaluacion)

    return () => {
      socket.disconnect()
    }
  }, [])
  useEffect(() => {
    const container = chatContainerRef.current;
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages]);
  

  const joinRoom = () => {
    if (username && socketRef.current) {
      socketRef.current.emit('join', { room, username })
      setJoined(true)
      sessionStorage.setItem('chatUser', JSON.stringify({ room, username }))
    }
  }
  useEffect(() => {
    const saved = sessionStorage.getItem('chatUser')
    if (saved) {
      const { room: savedRoom, username: savedUser } = JSON.parse(saved)
      if (savedRoom === room) {
        setUsername(savedUser)
        setJoined(true)
        socketRef.current?.emit('join', { room, username: savedUser })
      }
    }
  }, [room])

  const sendMessage = () => {
    if (input.trim() && socketRef.current && username) {
      socketRef.current.emit('message', { room, username, content: input.trim() })
      socketRef.current.emit('stop_typing',{room,username})
      setInput('')
    }
  }
  const agentesMencionables = ["orientador"]
  // Detectar cuando el usuario escribe
  const handleTyping = (e: React.ChangeEvent<HTMLInputElement>) => {
   

    const value = e.target.value
    setInput(value)
    const mentionMatch = value.match(/@(\w*)$/i); 
    if (mentionMatch) {
      const typed = mentionMatch[1].toLowerCase(); // lo que el usuario escribió después del @
      // Filtrar posibles agentes
      const matchAgent = agentesMencionables.find(a => a.startsWith(typed));
      if (matchAgent) {
        setShowMentionBar(true);
        setMentionTarget(matchAgent.charAt(0).toUpperCase() + matchAgent.slice(1));
      } else {
        setShowMentionBar(false);
        setMentionTarget(null);
      }
    } else {
      setShowMentionBar(false);
      setMentionTarget(null);
    }

    if (socketRef.current && username) {
      if (e.target.value.length > 0) {
        socketRef.current.emit('typing', { room, username })
      } else {
        socketRef.current.emit('stop_typing', { room, username })
      }
    }
  }

  useEffect(() => {
    const socket = socketRef.current;
    if (!socket || !username || !joined) return;
  
    const handleBeforeUnload = () => {
      socket.emit("leave", { room, username });
    };
  
    window.addEventListener("beforeunload", handleBeforeUnload);
  
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [joined, username, room]);
  

  const leaveRoom = () => {
    if (socketRef.current && username) {
      socketRef.current.emit("leave", { room, username });
      setJoined(false);
      setMessages([]);
      setAgentMessages([]);
      sessionStorage.removeItem('chatUser')
    }
  };
 // sincronización de tiempo
useEffect(() => {
  const socket = socketRef.current;
  if (!socket || !joined) return;

  const handleTimerUpdate = (data: {
    elapsed_time: number;
    remaining_time: number;
  }) => {
    const { elapsed_time, remaining_time} = data;

    if (!isTimerRunning) setIsTimerRunning(true);
    setRemainingTime((prev) =>
      prev === null || Math.abs(remaining_time - prev) > 1
        ? remaining_time
        : prev
    );
    setElapsedTime(elapsed_time);
  };

  // Escuchamos directamente los updates del timer desde la sala
  socket.on('timer_user_update', handleTimerUpdate);

  return () => {
    socket.off('timer_user_update', handleTimerUpdate);
  };
}, [joined]);
// Obtener el estado inicial del timer al unirse
useEffect(() => {
  if (!joined) return;

  async function fetchTimer() {
    try {
      const res = await fetch(`${backend}/api/rooms/${room}/timer`);
      if (!res.ok) return;

      const data = await res.json();

      setElapsedTime(data.elapsed_time);
      setRemainingTime(data.remaining_time);
      setIsTimerRunning(true);
    } catch (err) {
      console.error("Error obteniendo timer inicial", err);
    }
  }

  fetchTimer();
}, [joined]);


// Intervalo local para decrementar el contador cada segundo
useEffect(() => {
  if (!isTimerRunning || remainingTime === null) return;

  const interval = setInterval(() => {
    setRemainingTime((prev) => (prev && prev > 0 ? prev - 1 : 0));
    setElapsedTime((prev) => (prev !== null ? prev + 1 : 0));
  }, 1000);

  return () => clearInterval(interval);
}, [isTimerRunning, remainingTime]);

return (
  <main className="p-4 sm:p-6 md:p-8 w-full max-w-7xl mx-auto min-h-screen flex flex-col">
    <h1 className="text-2xl font-bold mb-4">Sala de chat: {room}</h1>

    {!joined ? (
      <div className="flex flex-col gap-3 max-w-sm mx-auto my-auto">
        <label className="font-medium">Nombre de usuario:</label>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Ingresa tu nombre"
          className="border border-gray-300 p-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <button
          onClick={joinRoom}
          className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 transition"
          disabled={!username.trim()}
        >
          Unirse a la sala
        </button>
      </div>
    ) : (
      <>
        {/* Header superior con fase y botón salir */}
        <div className="mb-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-blue-50 p-3 rounded-lg shadow-sm">
  <div className="text-xl font-semibold text-blue-700 flex flex-wrap items-baseline gap-2">
    🕒 Tiempo restante:
    <span
      className="text-green-700 font-mono font-bold ml-1 tracking-tight"
      style={{ fontVariantNumeric: "tabular-nums" }}
    >
      {Math.floor((remainingTime ?? 0) / 60)}:
      {String((remainingTime ?? 0) % 60).padStart(2, "0")}
    </span>
  </div>

  <button
    onClick={leaveRoom}
    className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700 transition"
  >
    Salir de la sala
  </button>
</div>

        {/* Grid principal responsivo */}
        <div
          className="grid grid-cols-1 md:grid-cols-[2fr_1fr] gap-4 flex-grow"
          style={{
            minHeight: "calc(100vh - 280px)",
          }}
        >
          {/* Chat principal */}
          <div className="flex flex-col w-full h-full border rounded-lg bg-white shadow-sm overflow-hidden">
            {/* Encabezado */}
            <div className="p-3 border-b bg-gray-100">
              <h2 className="font-semibold text-gray-800">Chat</h2>
            </div>

            {/* Área scrollable */}
            <div
              ref={chatContainerRef}
              className="flex-1 overflow-y-auto px-4 py-3 bg-gray-50 break-words scroll-smooth"
            >
              {messages.map((m, i) => {
                const isOwn = m.username === username;
                const isSystem = m.system;
                const isOrientador = m.username?.toLowerCase() === 'orientador';
                return (
                  <div
                    key={i}
                    className={`flex mb-2 ${
                      isSystem ? "justify-center" : isOwn ? "justify-end" : "justify-start"
                    }`}
                  >
                    <div
                      className={`px-3 py-2 rounded-2xl max-w-[80%] break-words ${
                        isSystem
                          ? "bg-gray-200 text-gray-700"
                          : isOwn
                          ? "bg-green-600 text-white"
                          : "bg-white border border-gray-200 text-gray-800"
                      }`}
                    >
                      {!isSystem && !isOwn && (
                        <b className="block text-sm mb-0.5">
                          {isOrientador ? '🤖' :""}
                          {m.username}</b>
                      )}
                      {m.content}
                    </div>
                  </div>
                );
              })}

              {/* Usuarios escribiendo */}
              {typingUsers.length > 0 && (
                <div className="flex justify-start mb-2">
                  <div className="bg-gray-200 text-gray-600 px-3 py-1 rounded-2xl italic text-sm">
                    💬 {typingUsers.join(", ")}{" "}
                    {typingUsers.length > 1 ? "están" : "está"} escribiendo...
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Panel del agente */}
          <div className="flex flex-col w-full h-full border rounded-lg bg-white shadow-sm overflow-hidden">
            <div className="p-3 border-b bg-blue-50">
              <h2 className="font-semibold text-blue-700">Agente</h2>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3 bg-gray-50 break-words scroll-smooth">
              {agentMessages.length === 0 ? (
                <p className="text-gray-500 text-sm">
                  Sin mensajes del agente todavía.
                </p>
              ) : (
                agentMessages.map((m, i) => (
                  <div
                    key={i}
                    className="p-2 rounded bg-blue-100 text-blue-800 text-sm w-full max-w-full break-words mb-2"
                  >
                    <b>{m.username}:</b> {m.content}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Input de mensajes */}
        <div className="mt-3 w-full">
          {showMentionBar && mentionTarget && (
            <div className="flex items-center gap-2 mb-2 bg-blue-50 border border-blue-300 text-blue-800 px-3 py-2 rounded-lg shadow-sm">
              💡 Mencionando a <b>@{mentionTarget}</b>
              <button
                onClick={() => {
                  setInput((prev) =>
                    prev.replace(/@\w*$/i, `@${mentionTarget}`)
                  );
                  setShowMentionBar(false);
                }}
                className="ml-auto text-sm text-blue-600 hover:underline"
              >
                Usar
              </button>
            </div>
          )}

          <div className="flex items-center gap-2 w-full">
            <input
              type="text"
              value={input}
              onChange={handleTyping}
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
              placeholder="Escribe tu mensaje..."
              className="flex-1 border border-gray-300 rounded-l-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <button
              onClick={sendMessage}
              className="bg-blue-500 text-white px-4 py-2 rounded-r-lg hover:bg-blue-600 transition"
            >
              Enviar
            </button>
          </div>
        </div>
      </>
    )}
  </main>
);


}
