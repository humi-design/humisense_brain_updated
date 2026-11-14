/**
 * Form primitives.
 *
 * Labels are always rendered and always associated with their control, either
 * implicitly (wrapping) or via a generated id. Help and error text are wired
 * through aria-describedby so they are announced with the field rather than
 * being visually adjacent only.
 *
 * Errors carry an icon as well as a colour, and use aria-invalid so the state
 * is available to assistive technology.
 */

import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { AlertTriangle } from "./icons";

interface FieldShellProps {
  id: string;
  label: string;
  help?: ReactNode;
  error?: string | null;
  required?: boolean;
  children: (ids: { id: string; describedBy?: string }) => ReactNode;
}

function FieldShell({
  id,
  label,
  help,
  error,
  required,
  children,
}: FieldShellProps) {
  const helpId = help ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, helpId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="hs-field">
      <label className="hs-field-label" htmlFor={id}>
        {label}
        {required && (
          <span className="hs-field-required" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children({ id, describedBy })}
      {error && (
        <p className="hs-field-error" id={errorId}>
          <AlertTriangle size={12} aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
      {help && (
        <p className="hs-field-help" id={helpId}>
          {help}
        </p>
      )}
    </div>
  );
}

export interface FieldProps {
  label: string;
  help?: ReactNode;
  error?: string | null;
  required?: boolean;
  /** Use an existing id instead of generating one. */
  id?: string;
}

export const Input = forwardRef<
  HTMLInputElement,
  FieldProps & InputHTMLAttributes<HTMLInputElement>
>(function Input({ label, help, error, required, id, ...rest }, ref) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <FieldShell
      id={fieldId}
      label={label}
      help={help}
      error={error}
      required={required}
    >
      {({ id: controlId, describedBy }) => (
        <input
          ref={ref}
          id={controlId}
          className={`hs-input${error ? " has-error" : ""}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          aria-required={required || undefined}
          {...rest}
        />
      )}
    </FieldShell>
  );
});

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ label, help, error, required, id, ...rest }, ref) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <FieldShell
      id={fieldId}
      label={label}
      help={help}
      error={error}
      required={required}
    >
      {({ id: controlId, describedBy }) => (
        <textarea
          ref={ref}
          id={controlId}
          className={`hs-input hs-textarea${error ? " has-error" : ""}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          aria-required={required || undefined}
          {...rest}
        />
      )}
    </FieldShell>
  );
});

export const Select = forwardRef<
  HTMLSelectElement,
  FieldProps & SelectHTMLAttributes<HTMLSelectElement>
>(function Select({ label, help, error, required, id, children, ...rest }, ref) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <FieldShell
      id={fieldId}
      label={label}
      help={help}
      error={error}
      required={required}
    >
      {({ id: controlId, describedBy }) => (
        <select
          ref={ref}
          id={controlId}
          className={`hs-input hs-select${error ? " has-error" : ""}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          aria-required={required || undefined}
          {...rest}
        >
          {children}
        </select>
      )}
    </FieldShell>
  );
});

/** Bare field wrapper, for controls that manage their own input element. */
export function Field({
  label,
  help,
  error,
  required,
  htmlFor,
  children,
}: FieldProps & { htmlFor: string; children: ReactNode }) {
  return (
    <FieldShell
      id={htmlFor}
      label={label}
      help={help}
      error={error}
      required={required}
    >
      {() => children}
    </FieldShell>
  );
}
