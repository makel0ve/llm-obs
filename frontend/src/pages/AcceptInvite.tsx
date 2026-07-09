import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { acceptOrganizationInvite, type UserRole } from '../api/dashboard'

function validatePassword(password: string, confirmation: string) {
  if (password.length < 8) return 'Password must be at least 8 characters.'
  if (password !== confirmation) return 'Passwords do not match.'
  return ''
}

export function AcceptInvite({
  onLogin,
}: {
  onLogin: (token: string, pid: string, role: UserRole) => void
}) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submitInvite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')

    const validationError = validatePassword(password, confirmation)
    if (validationError) {
      setError(validationError)
      return
    }

    setLoading(true)
    try {
      const result = await acceptOrganizationInvite({ token, password })
      onLogin(result.access_token, result.project_id ?? '', result.role)
      navigate('/', { replace: true })
    } catch {
      setError('Invite is invalid, expired or already accepted.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8">
        <h1 className="text-xl font-semibold text-gray-950">Accept invite</h1>
        <p className="mt-2 text-sm leading-6 text-gray-500">Set your password to join the organization.</p>
        {!token && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            Invite token is missing.
          </div>
        )}
        <form onSubmit={submitInvite} className="mt-5 space-y-3">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Password</span>
            <input
              type="password"
              value={password}
              onChange={event => {
                setError('')
                setPassword(event.target.value)
              }}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              minLength={8}
              maxLength={128}
              required
              disabled={!token}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Confirm password</span>
            <input
              type="password"
              value={confirmation}
              onChange={event => {
                setError('')
                setConfirmation(event.target.value)
              }}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              minLength={8}
              maxLength={128}
              required
              disabled={!token}
            />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={!token || loading}
            className="min-h-10 w-full rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? 'Joining...' : 'Join organization'}
          </button>
        </form>
      </div>
    </div>
  )
}
