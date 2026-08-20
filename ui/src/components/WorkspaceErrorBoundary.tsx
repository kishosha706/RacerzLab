import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { workspaceKey: string; children: ReactNode; onReturnToOverview: () => void };
type State = { error: Error | null; retryGeneration: number; workspaceKey: string };

export class WorkspaceErrorBoundary extends Component<Props, State> {
  state: State = { error: null, retryGeneration: 0, workspaceKey: this.props.workspaceKey };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.workspaceKey === state.workspaceKey
      ? null
      : { error: null, workspaceKey: props.workspaceKey };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Rendering stays local and fail-closed. Product diagnostics may collect a
    // redacted error receipt later; no telemetry or authority state is changed.
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <section className="workspace-placeholder workspace-error-boundary" role="alert">
          <h3>Workspace could not be rendered</h3>
          <p>{this.state.error.message}</p>
          <div className="tab-handoff-actions">
            <button type="button" onClick={() => this.setState((state) => ({ error: null, retryGeneration: state.retryGeneration + 1 }))}>Retry workspace</button>
            <button type="button" onClick={this.props.onReturnToOverview}>Return to Overview</button>
          </div>
        </section>
      );
    }
    return <div key={this.state.retryGeneration}>{this.props.children}</div>;
  }
}
