import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "styled-components";
import App from "./App";
import { theme } from "./styles/theme";
import { GlobalStyle } from "./styles/GlobalStyles";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <GlobalStyle theme={theme} />
      <BrowserRouter basename="/ui">
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>,
);
