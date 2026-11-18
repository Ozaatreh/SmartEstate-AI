import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { router } from "@/app/router";
import { TooltipProvider } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api-client";
import "@/styles/globals.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
    },
    mutations: { retry: false },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <RouterProvider router={router} />
        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast: "!rounded-[var(--radius-panel)] !border !border-border !bg-surface !text-fg !shadow-[var(--shadow-overlay)] !font-sans",
              description: "!text-fg-secondary",
            },
          }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
);
