import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import "./styles.css";
import "./desktop-experience.css";

const container = document.getElementById("root");

if (!container) {
  // Fail loudly and visibly instead of throwing inside the module graph, where
  // the only symptom would be an empty window with no explanation.
  document.body.innerHTML =
    '<main class="boot-screen"><section class="empty-panel">'
    + "<h1>RacerZLab could not start</h1>"
    + "<p>The application mount point is missing. Reinstall the desktop package "
    + "or reload the page.</p></section></main>";
} else {
  ReactDOM.createRoot(container).render(
    <React.StrictMode>
      <AppErrorBoundary>
        <App />
      </AppErrorBoundary>
    </React.StrictMode>,
  );
}
