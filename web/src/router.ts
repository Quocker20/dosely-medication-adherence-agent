type Listener = (pathname: string) => void;

const listeners = new Set<Listener>();
let current = window.location.pathname;

window.addEventListener("popstate", () => {
  current = window.location.pathname;
  listeners.forEach((listener) => listener(current));
});

export function getPathname(): string {
  return current;
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function navigate(path: string, { replace = false }: { replace?: boolean } = {}): void {
  if (path === current && !replace) return;

  current = path;
  if (replace) window.history.replaceState({}, "", path);
  else window.history.pushState({}, "", path);
  listeners.forEach((listener) => listener(path));
}
