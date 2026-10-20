import { useEffect, useState, useSyncExternalStore } from "react";

import { IS_STATIC_BUILD, loadManifest, type StaticManifest } from "../lib/static-backend";

/** localStorage key remembering that the visitor closed the demo notice. */
export const DEMO_NOTICE_DISMISSED_KEY = "testo.demoNotice.dismissed";

// The notice (above the router) and the header badge (inside AppShell) share
// one open/closed flag, kept here and mirrored to localStorage so a closed
// notice stays closed on reload. Storage can be unavailable (private mode,
// blocked site data); the notice then simply starts open again.
const listeners = new Set<() => void>();
let dismissed = readDismissed();

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(DEMO_NOTICE_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

function setDismissed(value: boolean) {
  dismissed = value;
  try {
    if (value) window.localStorage.setItem(DEMO_NOTICE_DISMISSED_KEY, "1");
    else window.localStorage.removeItem(DEMO_NOTICE_DISMISSED_KEY);
  } catch {
    // Remembered for this page view only.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function useDemoNoticeDismissed() {
  return useSyncExternalStore(subscribe, () => dismissed);
}

/**
 * Tells visitors of the published demo what they are looking at: a snapshot of
 * one pipeline run, what its two cycles are (and that fake-api's failures are
 * deliberate), with a link back to the pipeline that produced it. Like a
 * GitLab alert it has a close button; once closed, {@link DemoBadge} in the
 * header brings it back. Renders nothing in the normal build that talks to the API.
 */
export function StaticBuildBanner() {
  const [manifest, setManifest] = useState<StaticManifest | null>(null);
  const isDismissed = useDemoNoticeDismissed();

  useEffect(() => {
    if (!IS_STATIC_BUILD) return;
    let active = true;
    loadManifest().then((m) => {
      if (active) setManifest(m);
    });
    return () => {
      active = false;
    };
  }, []);

  if (!IS_STATIC_BUILD || isDismissed) return null;

  const generated = manifest ? new Date(manifest.generated_at * 1000).toUTCString() : null;
  const commit = manifest?.commit ? manifest.commit.slice(0, 8) : null;

  return (
    <div className="px-4 pt-3 sm:px-6 lg:pl-[19.5rem] lg:pt-5">
      <div
        id="demo-notice"
        role="region"
        aria-label="Read-only demo"
        className="relative mx-auto flex max-w-6xl gap-3 rounded-2xl border border-warn-400/40 border-l-4 border-l-warn-400 bg-ink-950/70 py-3 pl-3 pr-10 text-xs text-ink-200 shadow-lg backdrop-blur-xl"
      >
        <svg
          className="mt-0.5 h-4 w-4 shrink-0 text-warn-400"
          viewBox="0 0 16 16"
          fill="currentColor"
          aria-hidden
        >
          <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm0 3.25a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8ZM9 12H7V7.5h2V12Z" />
        </svg>
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-semibold text-warn-400">Read-only demo</p>
          <p>
            Real results from <code className="font-mono">testo run</code> in CI: Testosterone testing itself (
            <code className="font-mono">self-test</code>) and{" "}
            <a
              href="https://github.com/taltal-beep/fake-api"
              target="_blank"
              rel="noreferrer"
              className="text-brand-300 hover:text-brand-400 hover:underline"
            >
              fake-api
            </a>
            , an app whose flaky, broken and slow routes fail on purpose, so red there is expected. Starting runs and
            saving settings are disabled.
          </p>
          <p className="flex flex-wrap gap-x-3 gap-y-1 text-ink-400">
            {generated ? <span>Exported {generated}</span> : null}
            {commit ? (
              <span>
                Commit <code className="font-mono">{commit}</code>
                {manifest?.commit_ref ? ` (${manifest.commit_ref})` : ""}
              </span>
            ) : null}
            {manifest?.pipeline_url ? (
              <a
                href={manifest.pipeline_url}
                target="_blank"
                rel="noreferrer"
                className="text-brand-300 hover:text-brand-400 hover:underline"
              >
                View the pipeline
              </a>
            ) : null}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="absolute right-2 top-2 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-ink-800 hover:text-white"
          aria-label="Dismiss read-only demo notice"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
            <path d="M3 3l8 8M11 3l-8 8" />
          </svg>
        </button>
      </div>
    </div>
  );
}

/**
 * Header badge for the static build, so a visitor who closed the notice still
 * sees this is a read-only snapshot. Clicking it toggles the notice.
 */
export function DemoBadge() {
  const isDismissed = useDemoNoticeDismissed();
  if (!IS_STATIC_BUILD) return null;

  return (
    <button
      type="button"
      onClick={() => {
        setDismissed(!isDismissed);
        if (isDismissed) window.scrollTo({ top: 0 });
      }}
      className="whitespace-nowrap rounded-full border border-warn-400/40 bg-warn-400/10 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-warn-400 transition-colors hover:bg-warn-400/20"
      aria-controls="demo-notice"
      aria-expanded={!isDismissed}
      title={isDismissed ? "Show the read-only demo notice" : "Hide the read-only demo notice"}
    >
      Read-only demo
    </button>
  );
}
