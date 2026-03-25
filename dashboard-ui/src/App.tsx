import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import SuiteDetail from "./pages/SuiteDetail";
import RunDetail from "./pages/RunDetail";
import Prompts from "./pages/Prompts";
import PromptDetail from "./pages/PromptDetail";
import Models from "./pages/Models";
import Cost from "./pages/Cost";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/suite/:name" element={<SuiteDetail />} />
        <Route path="/suite/:name/run/:runId" element={<RunDetail />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/prompts/:name" element={<PromptDetail />} />
        <Route path="/models" element={<Models />} />
        <Route path="/cost" element={<Cost />} />
      </Route>
    </Routes>
  );
}
