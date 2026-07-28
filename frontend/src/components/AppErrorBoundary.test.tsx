import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppErrorBoundary } from './AppErrorBoundary'

function BrokenDashboardView() {
  throw new Error('render exploded')
  return null
}

describe('AppErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows a recovery view when a routed dashboard component crashes', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    render(
      <AppErrorBoundary>
        <BrokenDashboardView />
      </AppErrorBoundary>,
    )

    expect(screen.getByRole('heading', { name: 'Dashboard view crashed' })).toBeInTheDocument()
    expect(screen.getByText('This view could not be rendered. Refresh the view or return to another dashboard page.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
