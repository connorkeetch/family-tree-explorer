import { useEffect, useRef, RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Accessibility helper for dialogs: moves focus into the dialog on open, keeps
 * Tab/Shift+Tab cycling within it, fires `onEscape` on Escape, and restores
 * focus to the previously-focused element on close. The container should carry
 * tabIndex={-1} so it can receive initial focus when it has no focusable child.
 */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, onEscape?: () => void, active = true) {
  const escape = useRef(onEscape);
  escape.current = onEscape;
  useEffect(() => {
    if (!active) return;
    const node = ref.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    if (node && !node.contains(document.activeElement)) {
      const first = node.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? node).focus();
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        escape.current?.();
        return;
      }
      if (e.key !== "Tab" || !node) return;
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!items.length) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!node.contains(active)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (!document.activeElement || document.activeElement === document.body || node?.contains(document.activeElement)) {
        previouslyFocused?.focus?.();
      }
    };
  }, [ref, active]);
}
