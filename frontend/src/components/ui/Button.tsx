/**
 * Button.
 *
 * Variants map to intent, not to colour, so a theme change or a brand accent
 * change does not require touching call sites. Sizes are fixed rather than
 * fluid so buttons stay aligned in dense toolbars.
 */

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "./icons";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  | "subtle";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
  iconRight?: LucideIcon;
  loading?: boolean;
  /** Renders the button as a router link while keeping button styling. */
  to?: string;
}

function classes(variant: ButtonVariant, size: ButtonSize, extra?: string) {
  return [
    "hs-btn",
    `hs-btn-${variant}`,
    size === "sm" ? "hs-btn-sm" : "",
    extra ?? "",
  ]
    .filter(Boolean)
    .join(" ");
}

function Inner({
  icon: Icon,
  iconRight: IconRight,
  loading,
  children,
}: Pick<ButtonProps, "icon" | "iconRight" | "loading" | "children">) {
  return (
    <>
      {loading ? (
        <span className="hs-spinner" aria-hidden="true" />
      ) : (
        Icon && <Icon size={14} aria-hidden="true" />
      )}
      {children != null && <span>{children}</span>}
      {IconRight && <IconRight size={14} aria-hidden="true" />}
    </>
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "secondary",
      size = "md",
      icon,
      iconRight,
      loading,
      to,
      className,
      children,
      disabled,
      type = "button",
      ...rest
    },
    ref,
  ) {
    const content = (
      <Inner icon={icon} iconRight={iconRight} loading={loading}>
        {children}
      </Inner>
    );

    if (to) {
      return (
        <Link to={to} className={classes(variant, size, className)}>
          {content}
        </Link>
      );
    }

    return (
      <button
        ref={ref}
        type={type}
        className={classes(variant, size, className)}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...rest}
      >
        {content}
      </button>
    );
  },
);

/**
 * Icon-only button.
 *
 * `label` is required and becomes the accessible name; an icon alone is not a
 * label a screen reader can announce.
 */
export function IconButton({
  label,
  icon: Icon,
  size = "md",
  variant = "ghost",
  className,
  ...rest
}: Omit<ButtonProps, "children" | "icon"> & {
  label: string;
  icon: LucideIcon;
}) {
  return (
    <button
      type="button"
      className={classes(variant, size, `hs-icon-btn ${className ?? ""}`)}
      aria-label={label}
      title={label}
      {...rest}
    >
      <Icon size={size === "sm" ? 14 : 16} aria-hidden="true" />
    </button>
  );
}

/** Groups buttons with consistent spacing. */
export function ButtonRow({ children }: { children: ReactNode }) {
  return <div className="hs-btn-row">{children}</div>;
}
