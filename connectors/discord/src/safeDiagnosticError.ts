export type SafeDiagnosticError = Readonly<{
  error_kind: string;
  error_code?: string | number;
  http_status?: number;
}>;

const SAFE_ERROR_KINDS = new Set([
  "AbortError",
  "AggregateError",
  "DiscordAPIError",
  "Error",
  "FetchError",
  "HTTPError",
  "RangeError",
  "ReferenceError",
  "SyntaxError",
  "TypeError",
  "URIError"
]);
const SAFE_ERROR_CODES = new Set([
  "EAI_AGAIN",
  "ECONNABORTED",
  "ECONNREFUSED",
  "ECONNRESET",
  "EHOSTUNREACH",
  "ENETUNREACH",
  "ENOTFOUND",
  "EPIPE",
  "ERR_CANCELED",
  "ETIMEDOUT",
  "UND_ERR_BODY_TIMEOUT",
  "UND_ERR_CONNECT_TIMEOUT",
  "UND_ERR_HEADERS_TIMEOUT"
]);

function readProperty(value: object, key: string): unknown {
  try {
    return Reflect.get(value, key);
  } catch {
    return undefined;
  }
}

function safeErrorKind(error: unknown): string {
  if (!error || (typeof error !== "object" && typeof error !== "function")) {
    return "unknown_error";
  }
  const constructor = readProperty(error, "constructor");
  const constructorName =
    constructor && (typeof constructor === "object" || typeof constructor === "function")
      ? readProperty(constructor, "name")
      : undefined;
  if (typeof constructorName === "string" && SAFE_ERROR_KINDS.has(constructorName)) {
    return constructorName;
  }
  return "unknown_error";
}

function safeErrorCode(error: unknown): string | number | undefined {
  if (!error || (typeof error !== "object" && typeof error !== "function")) {
    return undefined;
  }
  const code = readProperty(error, "code");
  if (typeof code === "number" && Number.isSafeInteger(code) && code >= 0) return code;
  if (typeof code === "string" && SAFE_ERROR_CODES.has(code)) return code;
  return undefined;
}

function safeHttpStatus(error: unknown): number | undefined {
  if (!error || (typeof error !== "object" && typeof error !== "function")) {
    return undefined;
  }
  for (const key of ["status", "statusCode"]) {
    const status = readProperty(error, key);
    if (typeof status === "number" && Number.isSafeInteger(status) && status >= 100 && status <= 599) {
      return status;
    }
  }
  return undefined;
}

/**
 * Creates a diagnostics-only error summary. It deliberately never reads or
 * returns Error.message, cause, stack, request/response objects, or arbitrary
 * string-valued error metadata because those values may contain Discord text,
 * credentials, or provider payloads.
 */
export function safeDiagnosticError(error: unknown): SafeDiagnosticError {
  const errorCode = safeErrorCode(error);
  const httpStatus = safeHttpStatus(error);
  return {
    error_kind: safeErrorKind(error),
    ...(errorCode === undefined ? {} : { error_code: errorCode }),
    ...(httpStatus === undefined ? {} : { http_status: httpStatus })
  };
}

/**
 * Compatibility representation for API fields that currently accept a string.
 * The string is composed only from the safe structured fields above.
 */
export function formatSafeDiagnosticError(error: unknown): string {
  const diagnostic = safeDiagnosticError(error);
  return [
    `kind=${diagnostic.error_kind}`,
    ...(diagnostic.error_code === undefined ? [] : [`code=${diagnostic.error_code}`]),
    ...(diagnostic.http_status === undefined ? [] : [`status=${diagnostic.http_status}`])
  ].join(" ");
}
