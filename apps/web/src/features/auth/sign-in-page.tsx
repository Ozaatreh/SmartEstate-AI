import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Wordmark } from "@/components/system/brand";
import { FormAlert, FormField, applyServerErrors } from "@/components/system/forms";
import { Button } from "@/components/ui/button";
import { Input, PasswordInput } from "@/components/ui/input";
import { useLogin } from "./api";
import { useAuth } from "./auth-context";
import { signInSchema, type SignInValues } from "./schemas";

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export default function SignInPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const login = useLogin();
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<SignInValues>({ resolver: zodResolver(signInSchema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;

  if (user) return <Navigate to={safeNext(params.get("next"))} replace />;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      await login.mutateAsync(values);
      navigate(safeNext(params.get("next")), { replace: true });
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, ["email", "password"]));
    }
  });

  return (
    <div className="grid min-h-dvh bg-canvas lg:grid-cols-[minmax(0,1fr)_minmax(0,560px)]">
      {/* Brand panel */}
      <aside className="relative hidden overflow-hidden bg-primary text-primary-foreground lg:flex lg:flex-col lg:justify-between lg:p-12">
        <SkylinePattern />
        <div className="relative flex items-center gap-2.5">
          <Wordmark className="[&_span]:text-primary-foreground [&_span_span]:text-white/60" />
        </div>
        <div className="relative max-w-md">
          <p className="mb-4 text-small font-medium uppercase tracking-[0.12em] text-[#e2b89f]">Real estate operations platform</p>
          <h1 className="font-display text-[40px] font-medium leading-[48px] tracking-[-0.01em]">
            Run the business behind every development.
          </h1>
          <p className="mt-4 text-lead text-white/70">
            Budgets, approvals, procurement, sales and marketing in one workspace, with AI that answers from your own data.
          </p>
        </div>
        <p className="relative text-small text-white/50">Prototype · NOVA Residences, Riyadh is a fictional demonstration project.</p>
      </aside>

      {/* Form */}
      <main className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-[380px]">
          <div className="mb-10 lg:hidden"><Wordmark /></div>
          <h2 className="text-h2 font-semibold tracking-[-0.015em]">Sign in</h2>
          <p className="mt-1 text-body text-fg-secondary">Use your SmartEstate work account.</p>

          <form onSubmit={onSubmit} noValidate className="mt-8 space-y-5">
            <FormAlert message={formError} />
            <FormField label="Work email" htmlFor="email" error={errors.email?.message} required>
              <Input type="email" autoComplete="username" autoFocus placeholder="name@company.com" {...form.register("email")} />
            </FormField>
            <FormField label="Password" htmlFor="password" error={errors.password?.message} required>
              <PasswordInput autoComplete="current-password" {...form.register("password")} />
            </FormField>
            <Button type="submit" variant="primary" size="lg" className="w-full" loading={isSubmitting}>Sign in</Button>
          </form>

          <p className="mt-8 flex items-center gap-2 text-small text-fg-muted">
            <ShieldCheck className="size-4 shrink-0" />
            Sessions are protected with secure, HttpOnly cookies. Five failed attempts lock the account for 15 minutes.
          </p>
        </div>
      </main>
    </div>
  );
}

/** Quiet line-drawn skyline (no gradients): rooftops and setbacks typical of Riyadh towers. */
function SkylinePattern() {
  return (
    <svg className="pointer-events-none absolute inset-x-0 bottom-0 h-[55%] w-full text-white/[0.07]" viewBox="0 0 800 400" preserveAspectRatio="xMidYMax slice" aria-hidden>
      <g fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M0 400V300h60v-40h50v140" />
        <path d="M120 400V180l40-30 40 30v220" />
        <path d="M215 400V240h70v160M235 240v-50h30v50" />
        <path d="M300 400V120h24V80h32v40h24v280" />
        <path d="M395 400V210l55-55 55 55v190" />
        <path d="M520 400V260h45v-60h45v200" />
        <path d="M625 400V150h70v250M645 150V110h30v40" />
        <path d="M710 400V280h90" />
        <path d="M0 400h800" />
      </g>
      <g fill="currentColor">
        {Array.from({ length: 18 }, (_, i) => <rect key={i} x={312 + (i % 3) * 18} y={140 + Math.floor(i / 3) * 34} width="8" height="12" />)}
      </g>
    </svg>
  );
}
