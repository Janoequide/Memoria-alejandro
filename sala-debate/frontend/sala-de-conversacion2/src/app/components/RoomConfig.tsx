'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

interface DebateTopic {
  id: number
  titulo: string
  tema_text: string
  created_at?: string
}

interface Room {
  id: number
  name: string
}

interface RoomStatus {
  room_name: string
  status: string
}

interface RoomConfigProps {
  backend: string
}

export default function RoomConfig({ backend }: RoomConfigProps) {
  const router = useRouter()

  const [availableRooms, setAvailableRooms] = useState<Room[]>([])
  const [roomStatuses, setRoomStatuses] = useState<RoomStatus[]>([])
  const [debateTopics, setDebateTopics] = useState<DebateTopic[]>([])
  const [room, setRoom] = useState('')
  const [topic, setTopic] = useState('')
  const [selectedCaseKey, setSelectedCaseKey] = useState('')
  const [idioma, setIdioma] = useState('español')
  const [pipeline, setPipeline] = useState("standard")
 

  // Fetch de salas
  const fetchRooms = async () => {
    try {
      const res = await fetch(`${backend}/api/rooms`)
      if (!res.ok) throw new Error('Error al obtener salas')
      const data = await res.json()
      setAvailableRooms(data)
    } catch (error) {
      console.error('Error al cargar salas:', error)
    }
  }

  // Fetch de estado de salas
  const fetchStatuses = async () => {
    try {
      const res = await fetch(`${backend}/api/rooms/status`)
      if (!res.ok) throw new Error('Error al obtener estado de salas')
      const data = await res.json()
      setRoomStatuses(data)
    } catch (error) {
      console.error('Error al cargar estado de salas:', error)
    }
  }

  // Fetch de temas de debate
  const fetchDebateTopics = async () => {
    try {
      const res = await fetch(`${backend}/api/topics`)
      if (!res.ok) throw new Error('Error al obtener los temas de debate')
      const data = await res.json()
      setDebateTopics(data)
    } catch (error) {
      console.error(error)
    }
  }

  useEffect(() => {
    fetchRooms()
    fetchStatuses()
    fetchDebateTopics()
  }, [backend])

  // Selección de tema
  const handleCaseChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = parseInt(e.target.value)
    const selected = debateTopics.find((t) => t.id === id)
    if (selected) {
      setSelectedCaseKey(id.toString())
      setTopic(selected.tema_text)
    } else {
      setSelectedCaseKey('')
      setTopic('')
    }
  }

  const handleEnter = () => {
    if (!room || !topic) return
    sessionStorage.setItem('chatIdioma', idioma)
    sessionStorage.setItem('chatTopic', topic)
    sessionStorage.setItem('chatRoom', room)
    sessionStorage.setItem("pipelineType", pipeline)

    router.push(`/chat/${room}/lobby`)
  }

  const handleCloseRoom = async (roomName: string) => {
    if (!confirm(`¿Deseas cerrar la sala "${roomName}"?`)) return

    try {
      const res = await fetch(`${backend}/api/rooms/${roomName}/sessions/active`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room: roomName }),
      })

      if (!res.ok) {
        const errorData = await res.json()
        alert(`Error: ${errorData.error || 'No se pudo cerrar la sala'}`)
        return
      }

      alert(`Sala "${roomName}" cerrada exitosamente`)
      fetchStatuses()
    } catch (error) {
      console.error('Error al cerrar la sala:', error)
      alert('Error al cerrar la sala')
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Panel izquierdo - Estado de salas */}
      <div className="border rounded-lg p-4 shadow bg-gray-50">
        <h2 className="text-lg font-semibold mb-2">Estado de salas</h2>
        {roomStatuses.length === 0 ? (
          <p className="text-sm text-gray-500">No hay información de salas.</p>
        ) : (
          <ul className="space-y-2">
            {roomStatuses.map((r, idx) => (
              <li key={idx} className="flex justify-between items-center border-b pb-1">
                <span>{r.room_name}</span>
                <span
                  className={`px-2 py-1 rounded text-xs font-semibold ${
                    r.status === 'active'
                      ? 'bg-green-200 text-green-800'
                      : 'bg-red-200 text-red-800'
                  }`}
                >
                  {r.status || 'sin sesión'}
                </span>
                {r.status === 'active' && (
                  <button
                    className="bg-red-500 text-white text-[10px] px-1.5 py-0.5 rounded hover:bg-red-600 transition"
                    onClick={() => handleCloseRoom(r.room_name)}
                  >
                    Cerrar
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Panel central - Configuración */}
      <div>
        <h1 className="text-2xl font-bold mb-6">Configuración de la Sala</h1>

        <div className="mb-4">
          <label className="block mb-2 text-sm font-medium">Elige la sala:</label>
          <select
            className="border p-2 w-full rounded cursor-pointer"
            value={room}
            onChange={(e) => setRoom(e.target.value)}
          >
            <option value="">-- Selecciona una sala --</option>
            {availableRooms.map((r) => (
              <option key={r.id} value={r.name}>
                {r.name}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-6">
          <label className="block mb-2 text-sm font-medium">Elige un tema:</label>
          <select
            className="border p-2 w-full rounded"
            value={selectedCaseKey}
            onChange={handleCaseChange}
          >
            <option value="">-- Selecciona un tema --</option>
            {debateTopics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.titulo}
              </option>
            ))}
          </select>
        </div>

        <div>
          <button
            onClick={handleEnter}
            className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700 transition w-full"
          >
            Entrar a la Sala
          </button>
        </div>
        
        <div className="mb-4">
          <label className="block mb-2 text-sm font-medium">Seleccionar idioma:</label>
          <select
            className="border p-2 w-full rounded cursor-pointer"
            value={idioma}
            onChange={(e) => setIdioma(e.target.value)}
          >
            <option value="español">Español</option>
            <option value="inglés">Inglés</option>
          </select>
        </div>
        <div className="mb-4">
          <label className="block mb-2 text-sm font-medium">Seleccionar tipo de sistema:</label>
          <select
            className="border p-2 w-full rounded cursor-pointer"
            value={pipeline}
            onChange={(e) => setPipeline(e.target.value)}
          >
            <option value="standard">Pipeline estándar</option>
            <option value="toulmin">Pipeline Toulmin</option>
          </select>
        </div>

      </div>

      {/* Panel derecho - Texto del tema */}
      <div className="border rounded-lg p-5 shadow-lg bg-white h-[500px] flex flex-col">
        <h2 className="text-xl font-semibold mb-3 text-blue-800">Tema seleccionado</h2>

        <div className="border rounded-md bg-gray-50 p-4 flex-grow overflow-y-auto text-gray-800 whitespace-pre-wrap leading-relaxed shadow-inner">
          {topic ? (
            <p>{topic}</p>
          ) : (
            <p className="text-gray-400 italic">Selecciona un tema para visualizarlo aquí.</p>
          )}
        </div>
      </div>
    </div>
  )
}
