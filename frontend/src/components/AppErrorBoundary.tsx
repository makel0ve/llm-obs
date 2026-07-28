import { Component, type ErrorInfo, type ReactNode } from 'react'

type AppErrorBoundaryProps = {
  children: ReactNode
}

type AppErrorBoundaryState = {
  hasError: boolean
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = {
    hasError: false,
  }

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Dashboard route crashed', { error, componentStack: errorInfo.componentStack })
  }

  render() {
    if (this.state.hasError) {
      return (
        <RouteCrashFallback onReset={() => this.setState({ hasError: false })} />
      )
    }

    return this.props.children
  }
}

export function RouteCrashFallback({ onReset }: { onReset: () => void }) {
  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800">
        <h1 className="text-lg font-semibold text-red-950">Dashboard view crashed</h1>
        <p className="mt-2 leading-6">
          This view could not be rendered. Refresh the view or return to another dashboard page.
        </p>
        <button
          type="button"
          onClick={onReset}
          className="mt-4 rounded-md bg-red-700 px-3 py-2 text-sm font-medium text-white hover:bg-red-800"
        >
          Try again
        </button>
      </div>
    </div>
  )
}
