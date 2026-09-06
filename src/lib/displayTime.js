export const DISPLAY_TIME_ZONE = "America/Sao_Paulo";
export const DISPLAY_TIME_ZONE_LABEL = "São Paulo";

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: DISPLAY_TIME_ZONE,
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});
const clockFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: DISPLAY_TIME_ZONE,
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});
const timestampPattern = /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$/;
const narrativeTimestampPattern = /\b\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})\b/g;

function displayDate(value) {
  if (typeof value !== "string") return null;
  const match = value.match(timestampPattern);
  if (!match) return null; // Never infer the computer's timezone for unzoned text.
  const [, year, month, day, hour, minute, second] = match.map(Number);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1]
    || hour > 23 || minute > 59 || second > 59) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

// Presentation only: callers keep canonical timestamps in requests and dateTime attributes.
export function formatDateTime(value, fallback = "—") {
  const date = displayDate(value);
  return date ? dateTimeFormatter.format(date) : fallback;
}

export function formatClock(value, fallback = "—") {
  const date = displayDate(value);
  return date ? clockFormatter.format(date) : fallback;
}

// Python ISO timestamps may contain microseconds; human-facing prose uses seconds.
export function formatTimestampText(text) {
  if (typeof text !== "string") return "";
  return text.replace(narrativeTimestampPattern, (timestamp) => {
    const formatted = formatDateTime(timestamp, null);
    return formatted ? `${formatted} (${DISPLAY_TIME_ZONE_LABEL})` : timestamp;
  });
}
