// Runs before paint; storage failure must not prevent rendering.
try {
  document.documentElement.classList.toggle(
    'dark',
    localStorage.getItem('ai-radar-theme') !== 'light',
  );
} catch {
  document.documentElement.classList.add('dark');
}