/**
 * Builds Server-Sent Events Responses that stream a run job's or a scenario
 * batch's progress: replays buffered events on connect (so a reconnect/late
 * subscribe catches up), then forwards live events until it ends. Server-only.
 */
import { EventEmitter } from "node:events";
import { getJob, getBatch, type ProgressEvent } from "./runManager";

interface Streamable {
  buffer: ProgressEvent[];
  done: boolean;
  emitter: EventEmitter;
}

function streamFrom(src: Streamable | undefined): Response {
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const send = (ev: ProgressEvent) => {
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(ev)}\n\n`));
        } catch {
          /* controller closed */
        }
      };

      if (!src) {
        send({ event: "error", message: "Unknown or expired job." });
        controller.close();
        return;
      }

      // Replay everything seen so far (safe: no events interleave here).
      for (const ev of src.buffer) send(ev);
      if (src.done) {
        controller.close();
        return;
      }

      const onEvent = (ev: ProgressEvent) => send(ev);
      const heartbeat = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(`: ping\n\n`));
        } catch {
          clearInterval(heartbeat);
        }
      }, 15000);

      const onEnd = () => {
        clearInterval(heartbeat);
        src.emitter.off("event", onEvent);
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };

      src.emitter.on("event", onEvent);
      src.emitter.once("end", onEnd);
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}

export function sseResponse(jobId: string): Response {
  return streamFrom(getJob(jobId));
}

export function sseBatchResponse(batchId: string): Response {
  return streamFrom(getBatch(batchId));
}
