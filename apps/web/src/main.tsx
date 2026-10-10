import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { language, t } from "./i18n";
import "./styles.css";

document.documentElement.lang = language;
document.title = t("appName");
document
  .querySelector('meta[name="description"]')
  ?.setAttribute("content", t("description"));

const root = document.getElementById("root");
if (root) {
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
