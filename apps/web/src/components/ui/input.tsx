import { Eye, EyeOff } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const controlClass =
  "w-full rounded-[var(--radius-control)] border border-border bg-surface px-3 text-body text-fg placeholder:text-fg-muted " +
  "transition-[border-color,box-shadow] duration-150 hover:border-border-strong focus-visible:border-brand " +
  "disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-fg-muted " +
  "aria-[invalid=true]:border-danger aria-[invalid=true]:focus-visible:shadow-[0_0_0_2px_var(--surface),0_0_0_4px_var(--danger)]";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input ref={ref} type={type} className={cn(controlClass, "h-9", className)} {...props} />
  ),
);
Input.displayName = "Input";

/** Password field with a show/hide toggle; all props (id, aria-*) go to the input itself. */
export const PasswordInput = React.forwardRef<HTMLInputElement, Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">>(
  ({ className, ...props }, ref) => {
    const [visible, setVisible] = React.useState(false);
    return (
      <div className="relative">
        <input ref={ref} type={visible ? "text" : "password"} className={cn(controlClass, "h-9 pr-10", className)} {...props} />
        <button type="button" onClick={() => setVisible((v) => !v)} aria-label={visible ? "Hide password" : "Show password"}
          className="absolute right-1 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded text-fg-muted transition-colors hover:text-fg">
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
    );
  },
);
PasswordInput.displayName = "PasswordInput";

export const Textarea =React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, rows = 4, ...props }, ref) => (
    <textarea ref={ref} rows={rows} className={cn(controlClass, "min-h-20 py-2 leading-5", className)} {...props} />
  ),
);
Textarea.displayName = "Textarea";
