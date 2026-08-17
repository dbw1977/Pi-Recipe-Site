import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api } from './api';

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const onHome = location.pathname === '/';
  const [draftCount, setDraftCount] = useState(0);

  // Keep the drafts badge current as you navigate (cheap; two-user LAN app).
  useEffect(() => {
    api
      .listDrafts()
      .then((d) => setDraftCount(d.length))
      .catch(() => setDraftCount(0));
  }, [location.pathname]);

  return (
    <div className="min-h-screen">
      <header className="no-print sticky top-0 z-10 border-b border-black/5 bg-cream/85 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            {!onHome && (
              <button onClick={() => navigate(-1)} aria-label="Back" className="btn-ghost !px-3 !py-2">
                ‹
              </button>
            )}
            <Link to="/" className="font-display text-xl font-semibold text-ember">
              Our Recipes
            </Link>
          </div>
          <div className="flex items-center gap-1.5">
            <Link to="/settings" className="btn-ghost !px-2.5 !py-2" aria-label="Settings" title="Settings">
              ⚙
            </Link>
            {draftCount > 0 && (
              <Link to="/drafts" className="btn-ghost relative !px-3 !py-2" aria-label="Drafts">
                Drafts
                <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-ember px-1 text-xs font-bold text-white">
                  {draftCount}
                </span>
              </Link>
            )}
            <Link to="/import" className="btn-ghost !px-3 !py-2">
              Import
            </Link>
            <Link to="/new" className="btn-primary !px-3 !py-2">
              + New
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 pb-24 pt-4">
        <Outlet />
      </main>
    </div>
  );
}
