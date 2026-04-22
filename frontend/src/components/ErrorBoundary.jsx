import { Component } from "react";

/**
 * ErrorBoundary — catches render errors in any child component tree.
 *
 * Usage:
 *   <ErrorBoundary fallbackLabel="POS Terminal">
 *     <POSTerminal />
 *   </ErrorBoundary>
 *
 * Accepts a `fallbackLabel` prop so each boundary can surface context-aware
 * messaging ("Back Office crashed" vs "POS Terminal crashed").
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error(
      `[ErrorBoundary] ${this.props.fallbackLabel ?? "Component"} crashed:`,
      error,
      info.componentStack
    );
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const label = this.props.fallbackLabel ?? "Application";
    const errorName = this.state.error?.name ?? "Unknown Error";

    return (
      <div style={styles.overlay}>
        <div style={styles.panel}>
          <div style={styles.titleBar}>
            <span style={styles.titleText}>⚠ {label} Error</span>
          </div>
          <div style={styles.body}>
            <p style={styles.heading}>{label} has crashed</p>
            <p style={styles.errorName}>{errorName}</p>
            <p style={styles.hint}>
              This section encountered an unexpected error. Your other tabs are
              unaffected.
            </p>
            <button style={styles.reloadBtn} onClick={() => window.location.reload()}>
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}

const styles = {
  overlay: {
    position: "fixed",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#0f172a",
    fontFamily: "Tahoma, 'Segoe UI', Arial, sans-serif",
    zIndex: 9999,
  },
  panel: {
    width: 440,
    borderRadius: 6,
    overflow: "hidden",
    boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
  },
  titleBar: {
    backgroundColor: "#1e3a5f",
    padding: "12px 20px",
  },
  titleText: {
    color: "#ffffff",
    fontWeight: "bold",
    fontSize: 14,
    letterSpacing: "0.02em",
  },
  body: {
    backgroundColor: "#ffffff",
    padding: "28px 28px 24px",
    textAlign: "center",
  },
  heading: {
    margin: "0 0 8px",
    fontSize: 17,
    fontWeight: "bold",
    color: "#1e293b",
  },
  errorName: {
    margin: "0 0 16px",
    fontSize: 13,
    color: "#dc2626",
    fontFamily: "monospace",
  },
  hint: {
    margin: "0 0 24px",
    fontSize: 13,
    color: "#64748b",
    lineHeight: 1.5,
  },
  reloadBtn: {
    padding: "10px 32px",
    backgroundColor: "#1e3a5f",
    color: "#ffffff",
    border: "none",
    borderRadius: 4,
    fontSize: 14,
    fontFamily: "Tahoma, 'Segoe UI', Arial, sans-serif",
    cursor: "pointer",
    fontWeight: "bold",
  },
};
