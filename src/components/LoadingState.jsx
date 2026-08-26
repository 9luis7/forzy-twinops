import React, { useEffect, useState } from "react";

const MESSAGE_ROTATION_MS = 2_500;
const VISUAL_VARIANTS = new Set(["panel", "twin", "canvas"]);

function prefersReducedMotion() {
  return (
    typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function useReducedMotionPreference() {
  const [reduceMotion, setReduceMotion] = useState(prefersReducedMotion);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }

    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setReduceMotion(preference.matches);
    updatePreference();

    if (typeof preference.addEventListener === "function") {
      preference.addEventListener("change", updatePreference);
      return () => preference.removeEventListener("change", updatePreference);
    }

    preference.addListener?.(updatePreference);
    return () => preference.removeListener?.(updatePreference);
  }, []);

  return reduceMotion;
}

export default function LoadingState({ label, messages = [], variant = "panel" }) {
  const visualMessages = Array.isArray(messages)
    ? Array.from(new Set(messages.filter(Boolean)))
    : [];
  const messageCount = visualMessages.length;
  const [messageIndex, setMessageIndex] = useState(() => (
    messageCount > 0 ? Math.floor(Math.random() * messageCount) : 0
  ));
  const reduceMotion = useReducedMotionPreference();
  const visualVariant = VISUAL_VARIANTS.has(variant) ? variant : "panel";

  useEffect(() => {
    if (reduceMotion || messageCount < 2) return undefined;

    const rotation = window.setInterval(() => {
      setMessageIndex((currentIndex) => (currentIndex + 1) % messageCount);
    }, MESSAGE_ROTATION_MS);

    return () => window.clearInterval(rotation);
  }, [messageCount, reduceMotion]);

  const message = messageCount > 0 ? visualMessages[messageIndex % messageCount] : null;

  return (
    <div
      aria-busy="true"
      aria-label={label}
      aria-live="polite"
      className={`loading-state loading-state--${visualVariant}`}
      role="status"
    >
      <div aria-hidden="true" className="loading-state__indicator" data-testid="loading-indicator">
        <span className="loading-state__ring" />
        <span className="loading-state__pulse" />
      </div>
      <p aria-hidden="true" className="loading-state__label">{label}</p>
      {message && (
        <p aria-hidden="true" className="loading-state__message">{message}</p>
      )}
    </div>
  );
}
