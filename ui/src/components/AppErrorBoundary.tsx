import { AlertTriangle, RefreshCw, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Last-resort render boundary for the whole application shell.
 *
 * The workspace boundary inside the cockpit catches a single workspace failing
 * to render. This boundary exists for failures above that scope: a crashed
 * provider, a broken context value, or any throw in the shell itself. Without
 * it React unmounts the entire tree and the desktop window shows a blank page
 * with no message, no recovery, and no way to report what happened.
 *
 * Fail-closed contract: this boundary only renders text and offers reload and
 * retry. It never writes telemetry, setup, workflow, or authority state, and it
 * never fabricates a decision. Reloading rebuilds the same exact session scope
 * from persisted truth.
 */

type Props = { children: ReactNode };

type State = {
  error: Error | null;
  errorInfo: string | null;
  retryGeneration: number;
  detailsOpen: boolean;
};

const RELOAD_HINT = "Reloading rebuilds the exact current session from persisted telemetry. Nothing is deleted and no setup decision is changed.";

export class AppErrorBoundary extends Component<Props, State> {
  state: State = {
    error: null,
    errorInfo: null,
    retryGeneration: 0,
    detailsOpen: false,
  };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Diagnostics stay local and redacted. Product behavior is unchanged.
    // The stack is kept in memory only so the driver can copy it on request.
    const componentStack = typeof errorInfo.componentStack === "string"
      ? errorInfo.componentStack
      : null;
    this.setState({ errorInfo: componentStack });
    console.error("[RacerZLab] Unhandled shell render error", error, componentStack);
  }

  private readonly handleRetry = (): void => {
    this.setState((state) => ({
      error: null,
      errorInfo: null,
      detailsOpen: false,
      retryGeneration: state.retryGeneration + 1,
    }));
  };

  private readonly handleReload = (): void => {
    window.location.reload();
  };

  private readonly handleToggleDetails = (): void => {
    this.setState((state) => ({ detailsOpen: !state.detailsOpen }));
  };

  private buildDiagnosticText(): string {
    const { error, errorInfo } = this.state;
    const parts = [
      "RacerZLab shell error report",
      `Version: 0.1.0`,
      `User agent: ${typeof navigator === "undefined" ? "unavailable" : navigator.userAgent}`,
      `Location: ${typeof window === "undefined" ? "unavailable" : window.location.href}`,
      "",
      `Message: ${error?.message ?? "unknown"}`,
      "",
      "Stack:",
      error?.stack ?? "unavailable",
    ];
    if (errorInfo) {
      parts.push("", "Component stack:", errorInfo);
    }
    return parts.join("\n");
  }

  private readonly handleCopy = (): void => {
    const text = this.buildDiagnosticText();
    try {
      void navigator.clipboard?.writeText(text);
    } catch {
      // Clipboard access is optional; the details panel still shows the text.
    }
  };

  render(): ReactNode {
    const { error, errorInfo, detailsOpen } = this.state;
    if (!error) {
      return <div key={this.state.retryGeneration}>{this.props.children}</div>;
    }

    return (
      <main className="shell-loading-screen" role="alert" aria-live="assertive">
        <section className="shell-loading-panel app-crash-panel">
          <div className="shell-loading-mark app-crash-mark" aria-hidden="true">
            <AlertTriangle size={22} />
          </div>
          <div className="app-crash-copy">
            <span className="eyebrow">Shell recovery</span>
            <h1>RacerZLab could not render this screen.</h1>
            <p>
              The app stopped before drawing the workspace. Your telemetry, setups, and engineering
              history were not modified.
            </p>
            <p className="app-crash-hint">{RELOAD_HINT}</p>

            <div className="app-crash-message" role="note">
              <strong>Reported error</strong>
              <span>{error.message || "No message was provided."}</span>
            </div>

            <div className="app-crash-actions">
              <button type="button" className="start-primary-btn" onClick={this.handleReload}>
                <RefreshCw size={16} aria-hidden="true" /> Reload RacerZLab
              </button>
              <button type="button" className="secondary-button" onClick={this.handleRetry}>
                <RotateCcw size={16} aria-hidden="true" /> Try rendering again
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={this.handleToggleDetails}
                aria-expanded={detailsOpen}
              >
                {detailsOpen ? "Hide technical detail" : "Show technical detail"}
              </button>
              <button type="button" className="secondary-button" onClick={this.handleCopy}>
                Copy error report
              </button>
            </div>

            {detailsOpen && (
              <pre className="app-crash-details" tabIndex={0}>
                {this.buildDiagnosticText()}
                {errorInfo ? "" : "\n\nComponent stack: unavailable"}
              </pre>
            )}
          </div>
        </section>
      </main>
    );
  }
}
