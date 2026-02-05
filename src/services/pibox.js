import { getFingerprint } from "./fingerprint";

async function get(path) {
  return makePiboxRequest(path, "GET");
}

async function post(path, data) {
  return makePiboxRequest(path, "POST", data);
}

async function del(path, data = null) {
  return makePiboxRequest(path, "DELETE", data);
}

export const pibox = {
  get,
  post,
  delete: del,
};

async function makePiboxRequest(path, method = "GET", data = null) {
  const result = await fetch(`/pibox${path}`, {
    method,
    headers: getDefaultHeaders(),
    body: data ? JSON.stringify(data) : undefined,
  });

  const contentLength = result.headers.get("Content-Length");
  const hasBody = contentLength && parseInt(contentLength, 10) > 0;

  let responseData = null;
  if (hasBody) {
    try {
      responseData = await result.json();
    } catch (e) {
      // Not JSON (e.g., HTML error page). Fall back to raw text.
      try {
        const text = await result.text();
        responseData = { _text: text };
      } catch (e2) {
        responseData = null;
      }
    }
  }

  const retryAfter = result.headers.get("Retry-After") || null;

  return {
    status: result.status,
    data: responseData,
    headers: {
      retryAfter,
    },
  };
}

function getDefaultHeaders() {
  return {
    "X-Pibox-Fingerprint": getFingerprint(),
    "Content-Type": "application/json",
  };
}
