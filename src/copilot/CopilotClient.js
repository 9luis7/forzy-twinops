const CONTROL_CHARACTER = /[\x00-\x1f\x7f]/;

function validateBaseUrl(baseUrl) {
  if (typeof baseUrl !== "string" || CONTROL_CHARACTER.test(baseUrl)) {
    throw new TypeError("Copilot baseUrl must be a safe same-origin path");
  }
  if (
    baseUrl.includes("\\") ||
    baseUrl.startsWith("//") ||
    /^[a-z][a-z0-9+.-]*:/i.test(baseUrl) ||
    (baseUrl && !baseUrl.startsWith("/"))
  ) {
    throw new TypeError("Copilot baseUrl must be same-origin");
  }
  return baseUrl.replace(/\/$/, "");
}

export class CopilotHttpError extends Error {
  constructor(status) {
    super(`Copilot request failed with HTTP ${status}`);
    this.name = "CopilotHttpError";
    this.status = status;
  }
}

export function createCopilotClient({ fetchImpl = globalThis.fetch, baseUrl = "" } = {}) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetchImpl must be a function");
  const safeBaseUrl = validateBaseUrl(baseUrl);

  return Object.freeze({
    async explain(request, { signal } = {}) {
      const response = await fetchImpl(`${safeBaseUrl}/api/v1/copilot/explain`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
        signal,
      });
      if (!response.ok) throw new CopilotHttpError(response.status);
      const body = await response.json();
      if (
        typeof body?.answer !== "string" ||
        !Array.isArray(body?.evidenceRefs) ||
        body.evidenceRefs.some((item) => typeof item !== "string")
      ) {
        throw new TypeError("Invalid copilot response");
      }
      return body;
    },
  });
}
