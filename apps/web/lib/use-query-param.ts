"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => undefined;

export function useQueryParam(name: string): string | null {
  return useSyncExternalStore(
    subscribe,
    () => new URLSearchParams(window.location.search).get(name),
    () => null,
  );
}
