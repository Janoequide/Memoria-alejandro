'use client'

import { useEffect, useState } from 'react'

interface Tema {
  id: number
  titulo: string
  tema_text: string
  created_at: string
}

interface TemaForm {
  titulo: string
  tema_text: string
}

interface TemasManagerProps {
  backend: string
}

export default function TemasManager({ backend }: TemasManagerProps) {
  const [temas, setTemas] = useState<Tema[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const [form, setForm] = useState<TemaForm>({ titulo: '', tema_text: '' })
  const [editingId, setEditingId] = useState<number | null>(null)

  // FETCH TEMAS
  const fetchTemas = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${backend}/api/topics`)
      if (!res.ok) throw new Error('Error al obtener los temas')
      const data = await res.json()
      setTemas(data)
      setError(null)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTemas()
  }, [backend])

  // HANDLE FORM CHANGE
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }))
  }

  // HANDLE SUBMIT (POST o PUT)
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const method = editingId ? 'PUT' : 'POST'
      const endpoint = editingId ? `/${editingId}` : ''
      // Sanitización del texto
      const sanitizedTemaText = form.tema_text
        .replace(/\\/g, '\\\\')
        .replace(/"/g, '\\"')
        .replace(/\r?\n/g, '\\n');
  
      const body = editingId
        ? { id: editingId, titulo: form.titulo, tema_text: sanitizedTemaText }
        : { titulo: form.titulo, tema_text: sanitizedTemaText }
  
      const res = await fetch(`${backend}/api/topics${endpoint}`, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
  
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || 'Error al guardar el tema')
      }
  
      // Reset form
      setForm({ titulo: '', tema_text: '' })
      setEditingId(null)
      // Refrescar lista
      fetchTemas()
    } catch (err: any) {
      setError(err.message)
    }
  }
  

  // EDITAR TEMA
  const handleEdit = (tema: Tema) => {
    setForm({ titulo: tema.titulo, tema_text: tema.tema_text })
    setEditingId(tema.id)
  }

  return (
    <div className="p-4">
      <h2 className="text-2xl font-bold mb-4">Gestión de Temas</h2>

      {error && <p className="text-red-500 mb-2">{error}</p>}
      {loading && <p>Cargando temas...</p>}

      <div className="grid md:grid-cols-2 gap-6 items-start">
        {/* Lista de temas */}
        <div className="self-start bg-white p-4 rounded shadow-sm">
            <h3 className="font-semibold mb-2">Temas existentes</h3>
            <ul className="space-y-2 overflow-y-auto max-h-[70vh] pr-2">
                {temas.map(t => (
                <li
                    key={t.id}
                    className="border p-3 rounded flex justify-between items-start hover:shadow-md transition"
                >
                    <div className="overflow-hidden">
                    <p className="font-bold text-blue-900">{t.titulo}</p>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap break-words max-h-60 overflow-y-auto">
                        {t.tema_text}
                    </p>
                    </div>
                    <button
                    className="bg-yellow-500 text-white px-3 py-1 rounded hover:bg-yellow-600 text-sm ml-2"
                    onClick={() => handleEdit(t)}
                    >
                    Editar
                    </button>
                </li>
                ))}
            </ul>
        </div>
        <div className="self-start">
            <h3 className="font-semibold mb-2">
                {editingId ? 'Editar Tema' : 'Agregar Nuevo Tema'}
            </h3>
            <form onSubmit={handleSubmit} className="flex flex-col space-y-2 bg-white p-4 rounded shadow-sm">
                <input
                    type="text"
                    name="titulo"
                    placeholder="Título del tema"
                    value={form.titulo}
                    onChange={handleChange}
                    className="border p-2 rounded w-full"
                    required
                />
                <textarea
                    name="tema_text"
                    placeholder="Texto del tema"
                    value={form.tema_text}
                    onChange={handleChange}
                    rows={4}
                    className="border p-2 rounded w-full"
                    required
                />
                <button
                    type="submit"
                    className={`px-4 py-2 rounded text-white ${
                        editingId ? 'bg-blue-600 hover:bg-blue-700' : 'bg-green-600 hover:bg-green-700'
                    }`}
                    >
                    {editingId ? 'Actualizar Tema' : 'Agregar Tema'}
                </button>
                {editingId && (
                <button
                    type="button"
                    className="px-4 py-2 rounded bg-gray-400 text-white hover:bg-gray-500"
                    onClick={() => {
                    setEditingId(null)
                    setForm({ titulo: '', tema_text: '' })
                    }}
                >
                    Cancelar
                </button>
                )}
            </form>
        </div>
      </div>
    </div>
  )
}
