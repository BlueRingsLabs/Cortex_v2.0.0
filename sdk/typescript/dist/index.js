/**
 * Receive Cortex webhooks: verify the signature, then read a typed event.
 *
 *     import { verify, WebhookVerificationError } from "@blueringslabs/cortex-webhooks";
 *
 *     const event = verify(secret, request.headers, rawBody);
 *     if (event.type === "invoicing.invoice_issued") {
 *       console.log(event.data.total_minor); // typed from the platform's own catalogue
 *     }
 */
export { EVENT_TYPES } from "./events.js";
export { TOLERANCE_SECONDS, verify, WebhookVerificationError } from "./verify.js";
