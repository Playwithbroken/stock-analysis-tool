import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message || "Unknown error" };
  }

  componentDidCatch(error: Error) {
    if (import.meta.env.DEV) {
      console.error("[ErrorBoundary]", error);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="surface-panel rounded-[1.75rem] border border-red-200 bg-red-50/80 p-6 text-sm text-red-700">
            <div className="font-extrabold uppercase tracking-[0.18em]">
              Something went wrong
            </div>
            <div className="mt-2 text-red-600/80">{this.state.message}</div>
            <button
              className="mt-4 rounded-full border border-red-200 bg-white px-4 py-2 text-xs font-bold uppercase tracking-widest text-red-700 hover:bg-red-50"
              onClick={() => this.setState({ hasError: false, message: "" })}
            >
              Try again
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
