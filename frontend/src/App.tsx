import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api } from './api';

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;
  const eat = path === '/eat' || path.startsWith('/eat/');
  const collectionRoot = eat ? '/eat' : '/';
  const atRoot = path === '/' || path === '/eat';
  const [draftCount, setDraftCount] = useState(0);

  // Keep the drafts badge current for the active collection.
  useEffect(() => {
    const load = eat ? api.listPlaceDrafts() : api.listDrafts();
    load.then((d) => setDraftCount(d.length)).catch(() => setDraftCount(0));
  }, [path, eat]);

  const base = eat ? '/eat/' : '/';

  return (
    <div className="min-h-screen">
      <header className="no-print sticky top-0 z-10 border-b border-black/5 bg-cream/85 backdrop-blur">
        <div className="mx-auto max-w-3xl px-4 py-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {!atRoot && (
                <button onClick={() => navigate(-1)} aria-label="Back" className="btn-ghost !px-3 !py-2">
                  ‹
                </button>
              )}
              {/* Collection toggle — the app's identity + the Cook/Eat Out switch */}
              <div className="flex rounded-xl bg-white/70 p-0.5 ring-1 ring-black/5">
                <Link
                  to="/"
                  className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
                    !eat ? 'bg-ember text-white shadow-sm' : 'text-bark'
                  }`}
                >
                  🍳 Cook
                </Link>
                <Link
                  to="/eat"
                  className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
                    eat ? 'bg-ember text-white shadow-sm' : 'text-bark'
                  }`}
                >
                  🍴 Eat Out
                </Link>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <Link to="/plan" className="btn-ghost !px-2.5 !py-2" aria-label="Meal planner" title="Meal planner">
                📅
              </Link>
              <Link to="/settings" className="btn-ghost !px-2.5 !py-2" aria-label="Settings" title="Settings">
                ⚙
              </Link>
              {draftCount > 0 && (
                <Link to={`${collectionRoot === '/' ? '' : collectionRoot}/drafts`} className="btn-ghost relative !px-3 !py-2" aria-label="Drafts">
                  Drafts
                  <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-ember px-1 text-xs font-bold text-white">
                    {draftCount}
                  </span>
                </Link>
              )}
              <Link to={`${base}import`} className="btn-ghost !px-3 !py-2">
                Import
              </Link>
              <Link to={`${base}new`} className="btn-primary !px-3 !py-2">
                + New
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 pb-24 pt-4">
        <Outlet />
      </main>
    </div>
  );
}
