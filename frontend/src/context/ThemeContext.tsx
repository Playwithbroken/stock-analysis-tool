import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";

type Theme = "premium-light" | "dark";

interface ThemeContextType {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem("preferred_theme") as Theme | null;
    if (saved) return saved;
    // Respect system preference
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "premium-light";
  });

  const setTheme = (t: Theme) => {
    setThemeState(t);
    localStorage.setItem("preferred_theme", t);
    // Sync to backend profile (best-effort, no await needed)
    fetch("/api/settings/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: t }),
    }).catch(() => {});
  };

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.setAttribute("data-theme", "dark");
    } else {
      root.removeAttribute("data-theme");
    }
  }, [theme]);

  // Sync from backend after auth is confirmed to avoid 401 noise on login screen.
  useEffect(() => {
    const onAuthState = (event: Event) => {
      const custom = event as CustomEvent<{ authenticated?: boolean }>;
      if (!custom.detail?.authenticated) return;
      fetch("/api/settings/profile")
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data?.theme === "dark") {
            setThemeState("dark");
            localStorage.setItem("preferred_theme", "dark");
          }
        })
        .catch(() => {});
    };

    window.addEventListener("app:auth-state", onAuthState);
    return () => {
      window.removeEventListener("app:auth-state", onAuthState);
    };
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
};
