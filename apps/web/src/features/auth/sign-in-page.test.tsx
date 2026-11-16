import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth-context";
import SignInPage from "./sign-in-page";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderSignIn() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [{ path: "/sign-in", element: <AuthProvider><SignInPage /></AuthProvider> }, { path: "/", element: <p>Home page</p> }],
    { initialEntries: ["/sign-in"] },
  );
  render(<QueryClientProvider client={qc}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

afterEach(() => vi.unstubAllGlobals());

describe("SignInPage", () => {
  it("validates fields before calling the API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, { error: { code: "not_authenticated", message: "Sign in" } }));
    vi.stubGlobal("fetch", fetchMock);
    renderSignIn();
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your work email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1); // only the initial /auth/me probe
  });

  it("shows the server's error and sends the CSRF header", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "not_authenticated", message: "Sign in" } }))
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "invalid_credentials", message: "The email or password is incorrect." } }));
    vi.stubGlobal("fetch", fetchMock);
    renderSignIn();
    await userEvent.type(await screen.findByLabelText(/Work email/), "ceo@smartestate.demo");
    await userEvent.type(screen.getByLabelText(/^Password/), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The email or password is incorrect.");
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-Requested-With"]).toBe("XMLHttpRequest");
    expect(init.credentials).toBe("same-origin");
  });

  it("navigates home after a successful sign-in", async () => {
    const me = { id: "1", email: "ceo@smartestate.demo", full_name: "Faisal Al-Rashid", job_title: null, initials: "FA", roles: [], permissions: [], is_super_admin: false, last_login_at: null, session_expires_at: null };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "not_authenticated", message: "Sign in" } }))
      .mockResolvedValueOnce(jsonResponse(200, me)));
    const router = renderSignIn();
    await userEvent.type(await screen.findByLabelText(/Work email/), "ceo@smartestate.demo");
    await userEvent.type(screen.getByLabelText(/^Password/), "a-correct-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});
