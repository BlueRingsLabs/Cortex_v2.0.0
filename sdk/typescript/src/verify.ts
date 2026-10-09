/**
 * Verify a Cortex webhook before believing a word of it.
 *
 * A delivery carries `webhook-id`, `webhook-timestamp` and `webhook-signature`; the signature
 * is HMAC-SHA256, under the endpoint's secret, over `"{id}.{timestamp}.{body}"`, base64,
 * prefixed `v1,` (Standard Webhooks). During a rotation the header carries two signatures,
 * space-separated, and either verifying is enough.
 *
 * The body is verified as the bytes received -- pass the raw body, never `JSON.stringify` of a
 * parsed one -- the comparison is constant-time, and the timestamp must be within the
 * tolerance (five minutes by default). Node's own `crypto`, nothing else.
 */

import { createHmac, timingSafeEqual } from "node:crypto";

import type { CortexEvent } from "./events.ts";

/** Seconds a delivery's timestamp may differ from this machine's clock. */
export const TOLERANCE_SECONDS = 300;

export type VerificationFailure =
  | "missing_header"
  | "malformed_timestamp"
  | "timestamp_too_old"
  | "timestamp_too_new"
  | "malformed_secret"
  | "no_matching_signature"
  | "malformed_body";

/**
 * A delivery that must not be believed. Answer it with a 4xx other than 410 -- a 410 tells
 * Cortex to stop sending to the endpoint altogether.
 */
export class WebhookVerificationError extends Error {
  readonly reason: VerificationFailure;

  constructor(reason: VerificationFailure) {
    super(reason);
    this.name = "WebhookVerificationError";
    this.reason = reason;
  }
}

export type Headers =
  | Readonly<Record<string, string | readonly string[] | undefined>>
  | { get(name: string): string | null };

function header(headers: Headers, name: string): string | undefined {
  if (typeof (headers as { get?: unknown }).get === "function") {
    return (headers as { get(name: string): string | null }).get(name) ?? undefined;
  }
  const record = headers as Readonly<Record<string, string | readonly string[] | undefined>>;
  for (const [key, value] of Object.entries(record)) {
    if (key.toLowerCase() === name) return Array.isArray(value) ? value[0] : (value as string);
  }
  return undefined;
}

export interface VerifyOptions {
  readonly toleranceSeconds?: number;
  /** Seconds since the epoch; defaults to now. */
  readonly now?: number;
}

/** The delivery's event if it is genuine and fresh; throws `WebhookVerificationError` if not. */
export function verify(
  secret: string,
  headers: Headers,
  body: Uint8Array | string,
  options: VerifyOptions = {},
): CortexEvent {
  const id = header(headers, "webhook-id");
  const timestamp = header(headers, "webhook-timestamp");
  const signatures = header(headers, "webhook-signature");
  if (id === undefined || timestamp === undefined || signatures === undefined) {
    throw new WebhookVerificationError("missing_header");
  }
  if (!/^\d+$/.test(timestamp)) throw new WebhookVerificationError("malformed_timestamp");
  const sent = Number(timestamp);
  const now = options.now ?? Date.now() / 1000;
  const tolerance = options.toleranceSeconds ?? TOLERANCE_SECONDS;
  if (sent < now - tolerance) throw new WebhookVerificationError("timestamp_too_old");
  if (sent > now + tolerance) throw new WebhookVerificationError("timestamp_too_new");

  if (!secret.startsWith("whsec_")) throw new WebhookVerificationError("malformed_secret");
  const encoded = secret.slice("whsec_".length);
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(encoded)) {
    throw new WebhookVerificationError("malformed_secret");
  }
  const key = Buffer.from(encoded, "base64");
  const raw = typeof body === "string" ? Buffer.from(body, "utf8") : Buffer.from(body);
  const expected = createHmac("sha256", key).update(`${id}.${timestamp}.`).update(raw).digest();

  let matched = false;
  for (const candidate of signatures.split(" ")) {
    const comma = candidate.indexOf(",");
    if (comma < 0 || candidate.slice(0, comma) !== "v1") continue;
    const given = Buffer.from(candidate.slice(comma + 1), "base64");
    // Every candidate is compared, so the time taken does not say which one matched.
    if (given.length === expected.length && timingSafeEqual(given, expected)) matched = true;
  }
  if (!matched) throw new WebhookVerificationError("no_matching_signature");

  let event: unknown;
  try {
    event = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new WebhookVerificationError("malformed_body");
  }
  if (
    typeof event !== "object" ||
    event === null ||
    typeof (event as { type?: unknown }).type !== "string"
  ) {
    throw new WebhookVerificationError("malformed_body");
  }
  return event as CortexEvent;
}
