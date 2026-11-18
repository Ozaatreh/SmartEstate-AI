import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  // Primitives and system components export variants/helpers alongside components by design.
  {
    files: ["src/components/ui/**", "src/components/system/**", "src/app/**", "src/features/**/api.ts", "src/features/auth/auth-context.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
  // TanStack Table returns non-memoizable functions; the compiler skips this component by design.
  { files: ["src/components/system/data-table.tsx"], rules: { "react-hooks/incompatible-library": "off" } },
);
