/**
 * Typed errors for the two failures the UI must react to rather than merely
 * display: the token was rejected (401) and the token was accepted but is not
 * permitted (403).
 *
 * Everything else stays a generic ApiError and is rendered as an error note.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail?: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

/** The credential is missing, expired, or rejected. Re-authentication may help. */
export class UnauthorizedError extends ApiError {
  constructor(message: string, detail?: unknown) {
    super(401, "unauthorized", message, detail);
    this.name = "UnauthorizedError";
  }
}

/**
 * The credential is valid but this principal may not do this.
 *
 * Re-authenticating will not help, so the UI must not send the user to the
 * login page — that is the difference that matters between these two.
 */
export class ForbiddenError extends ApiError {
  constructor(message: string, detail?: unknown) {
    super(403, "forbidden", message, detail);
    this.name = "ForbiddenError";
  }
}

export function isUnauthorized(error: unknown): error is UnauthorizedError {
  return error instanceof UnauthorizedError;
}

export function isForbidden(error: unknown): error is ForbiddenError {
  return error instanceof ForbiddenError;
}

/** Human-readable message for any thrown value. */
export function describeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
