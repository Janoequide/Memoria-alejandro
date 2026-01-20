'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthGuard } from '../hooks/useAuthGuard'

export default function PromptsPage() {
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL
  const router = useRouter()

  const [agents, setAgents] = useState<string[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [pipelineType, setPipelineType] = useState("standard")
  const [availablePipelines, setAvailablePipelines] = useState<string[]>([])

  // Obtener lista de pipelines disponibles del backend
  const fetchPipelines = async () => {
    try {
      const res = await fetch(`${backend}/api/pipelines`)
      if (!res.ok) throw new Error('Error al obtener pipelines')
      const data = await res.json()
      setAvailablePipelines(data)
      
      // Si la lista tiene elementos y el actual no está, ponemos el primero por defecto
      if (data.length > 0 && !data.includes(pipelineType)) {
        setPipelineType(data[0])
      }
    } catch (error) {
      console.error('Error al cargar pipelines:', error)
    }
  }

  // Obtener lista de agentes disponibles
  const fetchAgents = async () => {
    try {
      const res = await fetch(`${backend}/api/agents?pipeline=${pipelineType}`)
      if (!res.ok) throw new Error('Error al obtener agentes')
      const data = await res.json()
      setAgents(data.agents || [])
    } catch (error) {
      console.error('Error al cargar agentes:', error)
    }
  }

  // Obtener prompts del pipeline actual
  const fetchPrompts = async () => {
    try {
      setLoading(true)
      const res = await fetch(`${backend}/api/prompts?pipeline=${pipelineType}`)
      if (!res.ok) throw new Error('Error al obtener prompts')
      const data = await res.json()
      setPrompts(data)
    } catch (error) {
      console.error('Error al cargar prompts:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSavePrompt = async () => {
    if (agents.length === 0) return
    const currentAgent = agents[currentIndex]
    try {
      setSaving(true)
      const res = await fetch(`${backend}/api/prompts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Pipeline': pipelineType,
        },
        body: JSON.stringify({
          agent_name: currentAgent,
          prompt: prompts[currentAgent],
        }),
      })
      
      if (!res.ok) {
        const errorData = await res.json()
        throw new Error(errorData.error || 'Error al guardar el prompt')
      }
      
      // Solo recargar si el POST fue exitoso
      await fetchPrompts()
      alert('Prompt guardado correctamente')
    } catch (error) {
      console.error('Error al guardar prompt:', error)
      alert(`Error al guardar: ${error instanceof Error ? error.message : 'Error desconocido'}`)
    } finally {
      setSaving(false)
    }
  }

  // Cargar pipelines al montar el componente
  useEffect(() => {
    fetchPipelines()
  }, [backend])

  // Cargar prompts y agentes cuando se cargan los pipelines disponibles
  // o cuando cambia el pipeline seleccionado
  useEffect(() => {
    if (availablePipelines.length > 0) {
      fetchPrompts()
      fetchAgents()
      setCurrentIndex(0)
    }
  }, [pipelineType, availablePipelines])

  const currentAgent = agents[currentIndex] || null

  return (
    <div className="p-8 w-full max-w-6xl mx-auto">
      {/* Selector de pipelines - Dinámico */}
      <div className="mb-6 flex gap-3 flex-wrap">
        {availablePipelines.map((pipeline) => (
          <button
            key={pipeline}
            onClick={() => setPipelineType(pipeline)}
            className={`px-4 py-2 rounded-lg border transition ${
              pipelineType === pipeline
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-gray-200 hover:bg-gray-300 border-gray-300'
            }`}
          >
            {pipeline.charAt(0).toUpperCase() + pipeline.slice(1)}
          </button>
        ))}
      </div>

      {/* Editor de prompts */}
      <div className="border rounded-2xl p-6 shadow-lg bg-white min-h-[60vh] flex flex-col">
        <h2 className="text-xl font-semibold mb-4">
          {currentAgent ? `Prompt del agente: ${currentAgent}` : 'Cargando agente...'}
        </h2>
        {loading ? (
          <p>Cargando prompt...</p>
        ) : (
          <textarea
            className="w-full border p-4 rounded-lg min-h-[500px] h-[60vh] text-sm sm:text-base resize-vertical"
            rows={12}
            value={currentAgent ? prompts[currentAgent] || '' : ''}
            onChange={(e) =>
              currentAgent &&
              setPrompts((prev) => ({ ...prev, [currentAgent]: e.target.value }))
            }
          />
        )}
      </div>

      {/* Paginación de agentes */}
      <div className="mt-6 flex justify-center gap-2 flex-wrap">
        {agents.map((agent, index) => (
          <button
            key={agent}
            onClick={() => setCurrentIndex(index)}
            className={`px-4 py-2 rounded transition ${
              index === currentIndex
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 hover:bg-gray-300'
            }`}
          >
            {index + 1}
          </button>
        ))}
      </div>

      {/* Botones de acción */}
      <div className="mt-6 flex justify-between gap-3">
        <button
          onClick={() => router.back()}
          className="bg-gray-300 text-gray-800 px-4 py-2 rounded hover:bg-gray-400 transition"
        >
          ← Volver
        </button>

        <button
          onClick={handleSavePrompt}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition disabled:bg-gray-400"
          disabled={saving}
        >
          {saving ? 'Guardando...' : 'Guardar cambios'}
        </button>
      </div>
    </div>
  )
}
