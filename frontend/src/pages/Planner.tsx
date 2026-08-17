import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, MealPlanCard } from '../api';
import { rangeLabel, upcomingSaturday } from '../lib/dates';

export default function Planner() {
  const [plans, setPlans] = useState<MealPlanCard[]>([]);
  const [start, setStart] = useState(upcomingSaturday());
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.listMealPlans().then(setPlans).catch(() => setPlans([]));
  }, []);

  const create = async () => {
    setBusy(true);
    try {
      const plan = await api.createMealPlan(start);
      navigate(`/plan/${plan.id}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl font-semibold">Meal planner</h1>
      <p className="text-sm text-muted">
        Pick a week, drop recipes onto days, and turn the whole thing into one grocery list.
      </p>

      <section className="card p-4">
        <h2 className="text-lg font-semibold">Start a new week</h2>
        <p className="mb-3 mt-1 text-sm text-muted">Defaults to this coming Saturday — change it to any start date.</p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="rounded-lg border-0 bg-white px-3 py-2.5 text-[15px] shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40"
          />
          <button onClick={create} disabled={busy} className="btn-primary">
            {busy ? 'Creating…' : 'Plan this week →'}
          </button>
        </div>
      </section>

      {plans.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Your plans</h2>
          {plans.map((p) => (
            <Link key={p.id} to={`/plan/${p.id}`} className="card flex items-center justify-between p-4">
              <div>
                <div className="font-semibold">{p.title || `Week of ${rangeLabel(p.start_date)}`}</div>
                <div className="text-sm text-muted">{rangeLabel(p.start_date)}</div>
              </div>
              <span className="chip bg-cream !text-[13px]">
                {p.entry_count} meal{p.entry_count === 1 ? '' : 's'}
              </span>
            </Link>
          ))}
        </section>
      )}
    </div>
  );
}
