import * as React from "react";

/** Set by FormField so controls that aren't direct children (e.g. a Select inside a Controller) still get the label's id. */
export interface FieldContextValue {
  id: string;
  describedBy?: string;
  invalid?: boolean;
  required?: boolean;
}

export const FieldContext = React.createContext<FieldContextValue | null>(null);
