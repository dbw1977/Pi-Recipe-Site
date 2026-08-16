import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const onHome = location.pathname === '/';

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-black/5 bg-cream/85 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            {!onHome && (
              <button
                onClick={() => navigate(-1)}
                aria-label="Back"
                className="btn-ghost !px-3 !py-2"
              >
                ‹
              </button>
            )}
            <Link to="/" className="font-display text-xl font-semibold text-ember">
              Our Recipes
            </Link>
          </div>
          <Link to="/new" className="btn-primary !py-2">
            + Add
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 pb-24 pt-4">
        <Outlet />
      </main>
    </div>
  );
}
