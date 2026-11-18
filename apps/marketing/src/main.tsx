import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "@/app/router";
import { I18nProvider } from "@/lib/i18n";
import "@/styles/globals.css";

// Refetch when a visitor comes back to the tab, so dashboard edits (cover image, prices, availability) show without a reload.
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: true, retry: 1 } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <RouterProvider router={router} />
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
);
