import { describe, expect, it } from "vitest";
import { formatClock, formatDateTime, formatTimestampText } from "./displayTime.js";

describe("São Paulo display time", () => {
  it("renders the same instant from UTC and explicit offsets, including microseconds", () => {
    const instants = ["2026-05-19T14:50:01.633000+00:00", "2026-05-19T14:50:01.633Z", "2026-05-19T11:50:01.633-03:00"];
    for (const instant of instants) {
      expect(formatDateTime(instant)).toBe("19/05/2026, 11:50:01");
      expect(formatClock(instant)).toBe("11:50:01");
    }
  });

  it("preserves the date across midnight and applies historical São Paulo daylight saving", () => {
    expect(formatDateTime("2026-05-19T01:10:00Z")).toBe("18/05/2026, 22:10:00");
    expect(formatClock("2026-05-19T03:00:00Z")).toBe("00:00:00");
    expect(formatDateTime("2018-12-19T03:10:00Z")).toBe("19/12/2018, 01:10:00");
  });

  it.each([null, undefined, "", "invalid", "2026-05-19T14:50:01", "2026-02-30T14:50:01Z", "2026-05-19T24:00:00Z", "2026-05-19T14:50:60Z", "0000-05-19T14:50:01Z"])("handles missing, ambiguous or invalid dates without inventing an instant: %s", (value) => {
    expect(formatDateTime(value)).toBe("—");
    expect(formatClock(value, "Não informado")).toBe("Não informado");
  });

  it("normalizes every ISO instant in prose while preserving its other content and source string", () => {
    const original = "A janela vai de 2026-05-19T14:49:01.524000+00:00 a 2026-05-19T14:50:01.633000+00:00. S1: 1,664 mm/s.";
    const result = formatTimestampText(original);
    expect(result).toBe("A janela vai de 19/05/2026, 11:49:01 (São Paulo) a 19/05/2026, 11:50:01 (São Paulo). S1: 1,664 mm/s.");
    expect(original).toContain("2026-05-19T14:49:01.524000+00:00");
    expect(formatTimestampText(result)).toBe(result);
  });

  it("leaves ambiguous and malformed narrative dates untouched and handles absent prose", () => {
    const text = "Em 2026-02-30T14:50:01Z ou 2026-05-19T14:50:01; consulte o manual.";
    expect(formatTimestampText(text)).toBe(text);
    expect(formatTimestampText(null)).toBe("");
  });
});
