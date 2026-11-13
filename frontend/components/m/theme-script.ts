// Plain module (no "use client") so the server layout can inline the script.
export const THEME_KEY = "meridian-v2-theme"

/** Runs in <head> before first paint so the right class is on <html> before
 *  anything renders — no dark→light flash. Saved choice wins, else the OS. */
export const THEME_INIT_SCRIPT = `(function(){try{
var s=localStorage.getItem('${THEME_KEY}');
var l=s?s==='light':window.matchMedia('(prefers-color-scheme: light)').matches;
document.documentElement.classList.toggle('light',l);
document.documentElement.classList.toggle('dark',!l);
}catch(_){}})()`

