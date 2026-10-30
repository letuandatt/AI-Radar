import { create } from 'zustand';

type Theme = 'dark' | 'light';

const initial = (): Theme =>
  document.documentElement.classList.contains('dark') ? 'dark' : 'light';

export const useTheme = create<{
  theme: Theme;
  toggle: () => void;
}>((set) => ({
  theme: initial(),
  toggle: () => set((state) => {
    const theme = state.theme === 'dark' ? 'light' : 'dark';

    document.documentElement.classList.toggle('dark', theme === 'dark');

    try {
      localStorage.setItem('ai-radar-theme', theme);
    } catch {
      // Session-only theme.
    }

    return { theme };
  }),
}));