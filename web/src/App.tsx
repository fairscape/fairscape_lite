import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import EntityPage from "./pages/EntityPage";
import SearchPage from "./pages/SearchPage";

const App = () => (
  <Routes>
    <Route element={<Layout />}>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/search" element={<SearchPage />} />
      {/* ARKs contain slashes, so the entity route is a wildcard. */}
      <Route path="/view/*" element={<EntityPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
  </Routes>
);

export default App;
