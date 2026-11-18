import * as React from "react";
import { createBrowserRouter } from "react-router-dom";
import { SiteLayout } from "@/components/layout";
import { Skeleton } from "@/components/ui";
import HomePage from "@/pages/home";
import NotFoundPage from "@/pages/not-found";

const AboutPage = React.lazy(() => import("@/pages/about"));
const AssistantPage = React.lazy(() => import("@/features/assistant/assistant-page"));
const ProjectsPage = React.lazy(() => import("@/pages/projects").then((m) => ({ default: m.ProjectsPage })));
const ProjectPage = React.lazy(() => import("@/pages/projects").then((m) => ({ default: m.ProjectPage })));
const UnitPage = React.lazy(() => import("@/pages/projects").then((m) => ({ default: m.UnitPage })));
const ContactPage = React.lazy(() => import("@/pages/contact").then((m) => ({ default: m.ContactPage })));
const ViewingPage = React.lazy(() => import("@/pages/contact").then((m) => ({ default: m.ViewingPage })));

const page = (el: React.ReactNode) => (
  <React.Suspense fallback={<div className="mx-auto max-w-6xl px-4 py-12" aria-busy="true"><Skeleton className="h-10 w-72" /></div>}>{el}</React.Suspense>
);

/** Public routes only. The internal dashboard is a separate application (apps/dashboard). */
export const router = createBrowserRouter([
  {
    element: <SiteLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "about", element: page(<AboutPage />) },
      { path: "projects", element: page(<ProjectsPage />) },
      { path: "projects/:code", element: page(<ProjectPage />) },
      { path: "projects/:code/units/:unit", element: page(<UnitPage />) },
      { path: "assistant", element: page(<AssistantPage />) },
      { path: "contact", element: page(<ContactPage />) },
      { path: "request-viewing", element: page(<ViewingPage />) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
