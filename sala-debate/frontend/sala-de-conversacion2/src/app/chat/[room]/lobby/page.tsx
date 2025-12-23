'use client'

import { useParams, useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { io, Socket } from 'socket.io-client'

export default function LobbyPage() {
  const params = useParams()
  const room = params.room as string
  const router = useRouter()
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL
  const socketRef = useRef<Socket | null>(null)

  const [username, setUsername] = useState('')
  const [joined, setJoined] = useState(false)
  const [participants, setParticipants] = useState<string[]>([])
  const [statusMessages, setStatusMessages] = useState<string[]>([])
  const [starting, setStarting] = useState(false)

  // Conexión socket (solo en el lobby)
  useEffect(() => {
    socketRef.current = io(backend, {
      path: '/socket.io',
      transports: ['websocket'],
    })
    const socket = socketRef.current

    socket.on('connect', () => {
      console.log('Lobby socket connected', socket.id)
    })

    socket.on('status', (data: { msg: string }) => {
      setStatusMessages(prev => [...prev, data.msg])
    })

    // Lista de participantes (requiere que el backend emita 'users_update')
    socket.on('users_update', (users: string[]) => {
      setParticipants(users || [])
    })

    // Evento que indica que la sala ya fue inicializada (requiere backend)
    socket.on('start_session', (data: any) => {
      // navegar al chat principal
      router.push(`/chat/${room}`)
    })

    return () => {
      socket.disconnect()
    }
  }, [room])

  const joinLobby = () => {
    if (!username.trim() || !socketRef.current) return
    socketRef.current.emit('join', { room, username })
    setJoined(true)
    sessionStorage.setItem('chatUser', JSON.stringify({ room, username }))
  }

  const leaveLobby = () => {
    if (!socketRef.current || !username) return
    socketRef.current.emit('leave', { room, username })
    setJoined(false)
    sessionStorage.removeItem('chatUser')
  }

  const startRoom = async () => {
    // Empieza la sala: POST a /api/rooms/{room_name}/sessions
    if (!socketRef.current) return
    setStarting(true)
    try {
      const prompt = sessionStorage.getItem('chatTopic') || ''
      const idioma = sessionStorage.getItem('chatIdioma') || 'español'
      const pipelineType = sessionStorage.getItem('pipelineType') || 'standard'

      const res = await fetch(`${backend}/api/rooms/${room}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room, prompt_inicial: prompt,idioma,pipeline_type: pipelineType }),
      })
      if (!res.ok) {
        const err = await res.json().catch(()=>({}))
        console.error('Error init-topic', err)
        alert('No se pudo iniciar la sala')
        setStarting(false)
        return
      }
      // El backend debería emitir 'start_session' a la sala. Redirigimos localmente también.
      router.push(`/chat/${room}`)
    } catch (e) {
      console.error('Error al iniciar sala', e)
      alert('Error al iniciar la sala')
      setStarting(false)
    }
  }

    return (
      <main className="flex justify-center items-center min-h-screen pt-12">
        <div className="bg-white rounded-2xl shadow-xl p-8 w-full max-w-2xl border border-gray-200 my-8 max-h-[calc(100vh-4rem)] overflow-auto">
          <h1 className="text-2xl font-bold mb-6 text-center text-blue-800">
            Lobby — Sala: {room}
          </h1>

          {!joined ? (
            <div className="flex flex-col gap-3">
              <label className="font-medium text-gray-700">
                Nombre de usuario (lobby):
              </label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Tu nombre"
                className="border border-gray-300 p-2 rounded-lg focus:ring-2 focus:ring-blue-400 outline-none"
              />
              <button
                onClick={joinLobby}
                disabled={!username.trim()}
                className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition disabled:opacity-50"
              >
                Unirse al lobby
              </button>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <strong className="block text-gray-700 mb-2">Participantes:</strong>
                <ul className="mt-2 list-disc list-inside bg-gray-50 border rounded-md p-3 max-h-40 overflow-y-auto text-gray-700">
                  {participants.length === 0 ? (
                    <li>Esperando participantes...</li>
                  ) : (
                    participants.map((p) => <li key={p}>{p}</li>)
                  )}
                </ul>

                <div className="mt-4 flex gap-3">
                  <button
                    onClick={startRoom}
                    className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
                    disabled={starting}
                  >
                    {starting ? 'Iniciando...' : 'Empezar sala'}
                  </button>
                  <button
                    onClick={leaveLobby}
                    className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 transition"
                  >
                    Salir del lobby
                  </button>
                </div>
              </div>

              <div>
                <strong className="block text-gray-700 mb-2">Mensajes de sistema:</strong>
                <div className="border rounded-md bg-gray-50 p-3 max-h-48 overflow-y-auto text-sm text-gray-700 shadow-inner">
                  {statusMessages.length === 0 ? (
                    <p className="text-gray-400 italic">Sin mensajes aún...</p>
                  ) : (
                    statusMessages.map((m, i) => (
                      <div key={i} className="mb-1">
                        • {m}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </main>


    
  )
}