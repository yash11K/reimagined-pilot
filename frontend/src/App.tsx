import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/contexts/AuthContext";
import { BrandProvider } from "@/contexts/BrandContext";
import { ToastProvider } from "@/contexts/ToastContext";
import { AppLayout } from "@/components/layout/AppLayout";
import ExecutiveDashboard from "@/pages/ExecutiveDashboard";
import SearchOperations from "@/pages/SearchOperations";
import DiscoveryTools from "@/pages/DiscoveryTools";
import KnowledgeLibrary from "@/pages/KnowledgeLibrary";
import FileDetail from "@/pages/FileDetail";
import ReviewGovernance from "@/pages/ReviewGovernance";
import AuthoringMode from "@/pages/AuthoringMode";
import Operations from "@/pages/Operations";
import "./App.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrandProvider>
          <ToastProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<AppLayout />}>
                <Route index element={<ExecutiveDashboard />} />
                <Route path="search-operations" element={<SearchOperations />} />
                <Route path="discovery-tools" element={<DiscoveryTools />} />
                <Route path="knowledge-library" element={<KnowledgeLibrary />} />
                <Route path="knowledge-library/:id" element={<FileDetail />} />
                <Route path="review-governance" element={<ReviewGovernance />} />
                <Route path="review-governance/:id" element={<FileDetail reviewMode />} />
                <Route path="authoring-mode" element={<AuthoringMode />} />
                <Route path="operations" element={<Operations />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
          </ToastProvider>
        </BrandProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
