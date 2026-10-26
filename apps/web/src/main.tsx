import React from "react";
import ReactDOM from "react-dom/client";
import AdminApp from "./AdminApp";
import App from "./App";
import { language, t } from "./i18n";
import "./styles.css";
import "./admin.css";

document.documentElement.lang = language;
document.title = t("appName");
const description = t("description");
document
  .querySelector('meta[name="description"]')
  ?.setAttribute("content", description);
document
  .querySelector('meta[property="og:description"]')
  ?.setAttribute("content", description);

const root = document.getElementById("root");
if (root) {
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      {location.pathname.startsWith("/admin") ? <AdminApp /> : <App />}
    </React.StrictMode>,
  );
}
