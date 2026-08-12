import { describe, expect, it, vi } from "vitest";

import { CopilotHttpError, createCopilotClient } from "./CopilotClient.js";

describe("createCopilotClient", () => {
  it("uses the same-origin endpoint and forwards AbortSignal", async () => {
    const signal = new AbortController().signal;
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ answer: "ok", evidenceRefs: [] }),
    });

    await createCopilotClient({ fetchImpl }).explain(
      { question: "Q", assetTag: "MOTOR-01", assessment: {} },
      { signal }
    );

    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/v1/copilot/explain",
      expect.objectContaining({ method: "POST", signal })
    );
  });

  it("throws a typed error without leaking the response body", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 503 });
    const client = createCopilotClient({ fetchImpl });

    await expect(
      client.explain({ question: "Q", assetTag: "MOTOR-01", assessment: {} })
    ).rejects.toEqual(expect.objectContaining({ name: "CopilotHttpError", status: 503 }));
    await expect(
      client.explain({ question: "Q", assetTag: "MOTOR-01", assessment: {} })
    ).rejects.toBeInstanceOf(CopilotHttpError);
  });

  it("rejects external and protocol-relative base URLs", () => {
    expect(() => createCopilotClient({ fetchImpl: vi.fn(), baseUrl: "https://llm.test" })).toThrow();
    expect(() => createCopilotClient({ fetchImpl: vi.fn(), baseUrl: "//llm.test" })).toThrow();
  });
});
