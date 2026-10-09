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
import type { CortexEvent } from "./events.ts";
/** Seconds a delivery's timestamp may differ from this machine's clock. */
export declare const TOLERANCE_SECONDS = 300;
export type VerificationFailure = "missing_header" | "malformed_timestamp" | "timestamp_too_old" | "timestamp_too_new" | "malformed_secret" | "no_matching_signature" | "malformed_body";
/**
 * A delivery that must not be believed. Answer it with a 4xx other than 410 -- a 410 tells
 * Cortex to stop sending to the endpoint altogether.
 */
export declare class WebhookVerificationError extends Error {
    readonly reason: VerificationFailure;
    constructor(reason: VerificationFailure);
}
export type Headers = Readonly<Record<string, string | readonly string[] | undefined>> | {
    get(name: string): string | null;
};
export interface VerifyOptions {
    readonly toleranceSeconds?: number;
    /** Seconds since the epoch; defaults to now. */
    readonly now?: number;
}
/** The delivery's event if it is genuine and fresh; throws `WebhookVerificationError` if not. */
export declare function verify(secret: string, headers: Headers, body: Uint8Array | string, options?: VerifyOptions): CortexEvent;
