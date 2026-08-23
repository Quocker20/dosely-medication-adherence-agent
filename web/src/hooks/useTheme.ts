import { useCallback, useEffect, useState } from "react";

/**
 * Chế độ giao diện. "system" = bỏ hẳn attribute data-theme để CSS rơi về
 * @media (prefers-color-scheme) trong styles/tokens.css.
 */
export type ThemeMode = "system" | "light" | "dark";

const NEXT_THEME: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };

export const THEME_LABEL: Record<ThemeMode, string> = {
  system: "theo hệ thống",
  light: "sáng",
  dark: "tối",
};

/** Dùng chung cho Doctor và Admin portal — Patient portal không có nút đổi giao diện. */
export function useTheme() {
  const [theme, setTheme] = useState<ThemeMode>("system");

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);

  const cycleTheme = useCallback(() => setTheme((current) => NEXT_THEME[current]), []);

  return { theme, cycleTheme };
}
