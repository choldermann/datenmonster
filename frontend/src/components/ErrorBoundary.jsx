import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, errorInfo: null };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ error, errorInfo });
    // Fehler in Konsole loggen (in Produktion könnte man hier Sentry etc. nutzen)
    console.error("ErrorBoundary:", error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: "100vh", display: "flex", alignItems: "center",
          justifyContent: "center", backgroundColor: "#111", color: "#f0f0f0",
          fontFamily: "system-ui, sans-serif", padding: 32,
        }}>
          <div style={{
            maxWidth: 560, backgroundColor: "#1a1a1a",
            border: "1px solid rgba(224,112,112,0.3)", borderRadius: 10,
            padding: 32, boxShadow: "0 16px 48px rgba(0,0,0,0.6)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <span style={{ fontSize: 24 }}>⚠</span>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#e07070" }}>
                Unerwarteter Fehler
              </h2>
            </div>
            <p style={{ fontSize: 13, color: "#aaa", margin: "0 0 16px", lineHeight: 1.6 }}>
              Ein unerwarteter Fehler ist aufgetreten. Bitte lade die Seite neu.
              Wenn das Problem bestehen bleibt, überprüfe die Browser-Konsole.
            </p>
            <div style={{
              backgroundColor: "#111", border: "1px solid #333", borderRadius: 6,
              padding: "10px 14px", marginBottom: 20, maxHeight: 160, overflow: "auto",
            }}>
              <code style={{ fontSize: 11, color: "#e07070", fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
                {this.state.error?.toString()}
              </code>
              {this.state.errorInfo?.componentStack && (
                <pre style={{ fontSize: 10, color: "#666", margin: "8px 0 0", whiteSpace: "pre-wrap" }}>
                  {this.state.errorInfo.componentStack.trim().split("\n").slice(0, 8).join("\n")}
                </pre>
              )}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={() => window.location.reload()}
                style={{
                  padding: "8px 20px", borderRadius: 5, border: "none",
                  backgroundColor: "#fce499", color: "#111", fontSize: 12,
                  fontWeight: 700, cursor: "pointer",
                }}>
                Seite neu laden
              </button>
              <button
                onClick={() => this.setState({ error: null, errorInfo: null })}
                style={{
                  padding: "8px 16px", borderRadius: 5,
                  border: "1px solid #444", background: "none",
                  color: "#aaa", fontSize: 12, cursor: "pointer",
                }}>
                Fehler verwerfen
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
