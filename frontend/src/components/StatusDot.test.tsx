import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StatusDot } from './StatusDot'

describe('StatusDot', () => {
  it('renderiza sem lancar, marcado aria-hidden (decorativo — status ja tem texto ao lado)', () => {
    const { container } = render(<StatusDot state="warn" />)
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
  })
})
