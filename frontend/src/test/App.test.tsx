import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import App from '../App'

describe('App', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('renders the sign-in screen when no token is stored', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'LLM Obs' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Email')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Password')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Sign in' })).toHaveLength(2)
  })
})
