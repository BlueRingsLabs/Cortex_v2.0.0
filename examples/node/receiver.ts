/**
 * A Cortex webhook receiver in TypeScript, Node's standard library only (Node 22.18+ runs it
 * as it is, stripping the types).
 *
 *     CORTEX_WEBHOOK_SECRET=whsec_... node examples/node/receiver.ts 8082
 *
 * Verify the raw body before parsing it, answer quickly, ignore a delivery already handled
 * (delivery is at least once: a retry or a replay carries the same `webhook-id`), and refuse
 * what does not verify with a 400.
 */

import { createServer } from "node:http";

import { verify, WebhookVerificationError } from "../../sdk/typescript/src/index.ts";

const secret = process.env["CORTEX_WEBHOOK_SECRET"];
if (secret === undefined) throw new Error("CORTEX_WEBHOOK_SECRET is not set");
const port = Number(process.argv[2] ?? "8082");
const maxBody = 1 << 20;

/** Message ids already handled. In production: a table with a unique constraint. */
const handled = new Set<string>();

createServer((request, response) => {
  const chunks: Buffer[] = [];
  let size = 0;
  request.on("data", (chunk: Buffer) => {
    size += chunk.length;
    if (size > maxBody) request.destroy();
    else chunks.push(chunk);
  });
  request.on("end", () => {
    const body = Buffer.concat(chunks);
    const headers: Record<string, string> = {};
    for (const [name, value] of Object.entries(request.headers)) {
      if (typeof value === "string") headers[name] = value;
    }
    try {
      const event = verify(secret, headers, body);
      const id = headers["webhook-id"] ?? "";
      if (handled.has(id)) {
        console.log(`duplicate ${id}`);
      } else {
        handled.add(id);
        console.log(`received ${event.type} ${id}`);
      }
      response.writeHead(204).end();
    } catch (error) {
      const reason = error instanceof WebhookVerificationError ? error.reason : "invalid";
      response.writeHead(400).end(reason);
    }
  });
}).listen(port, "127.0.0.1");
