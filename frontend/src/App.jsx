import { useMemo, useState } from "react";

const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// Money arrives in paise (integers). Format as ₹1,234.56
const inr = (paise) =>
  (paise / 100).toLocaleString("en-IN", { style: "currency", currency: "INR" });

const monthName = (ym) =>
  new Date(`${ym}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });

function Section({ title, children }) {
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-lg font-semibold text-slate-800">{title}</h2>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white text-slate-800">{children}</div>
    </section>
  );
}

const th = "px-4 py-2 text-left text-sm font-medium text-slate-500 bg-slate-50";
const td = "px-4 py-2 text-sm border-t border-slate-100";

export default function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);
  const [person, setPerson] = useState("All");

  async function handleUpload(e) {
    e.preventDefault();
    if (!file) return setError("Choose a CSV file first.");
    setLoading(true);
    setError("");
    setData(null);
    setPerson("All");
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${API_URL}/api/analyze/`, { method: "POST", body });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || `Server error (${res.status})`);
      setData(json);
    } catch (err) {
      setError(err.message === "Failed to fetch" ? "Cannot reach the server. Check the backend link and try again." : err.message);
    } finally {
      setLoading(false);
    }
  }

  const people = data ? data.balances.map((b) => b.person) : [];
  const match = (name) => person === "All" || name === person;

  const view = useMemo(() => {
    if (!data) return null;
    const p = person.toLowerCase();
    return {
      balances: data.balances.filter((b) => match(b.person)),
      settlements: data.settlements.filter((s) => match(s.from) || match(s.to)),
      badRows: data.bad_rows.filter(
        (r) => person === "All" || `${r.raw.paid_by};${r.raw.participants}`.toLowerCase().includes(p)
      ),
    };
  }, [data, person]);

  const months = data ? [...new Set(data.monthly_totals.map((m) => m.month))] : [];

  return (
    <div className="min-h-screen bg-slate-100 font-sans">
      <main className="mx-auto max-w-4xl px-4 py-10">
        <h1 className="text-3xl font-bold text-slate-900">SplitSmart</h1>
        <p className="mt-1 text-slate-600">Upload an expense CSV to see who owes whom.</p>

        <form onSubmit={handleUpload} className="mt-6 flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files[0] || null)}
            className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-white file:px-3 file:py-2 file:text-slate-700 file:shadow-sm"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            {loading ? "Analyzing…" : "Analyze CSV"}
          </button>
        </form>

        {error && (
          <p role="alert" className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        )}

        {data && view && (
          <>
            <div className="mt-6 flex flex-wrap items-center gap-4">
              <label className="text-sm text-slate-700">
                Filter by person{" "}
                <select
                  value={person}
                  onChange={(e) => setPerson(e.target.value)}
                  className="ml-1 rounded-md border border-slate-300 bg-white px-2 py-1"
                >
                  <option>All</option>
                  {people.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
              <p className="text-sm text-slate-600">
                {data.summary.good_rows} good rows, {data.summary.bad_rows} bad rows. Total spend {inr(data.summary.total_spend)}.
              </p>
            </div>

            <Section title="Balances">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className={th}>Person</th>
                    <th className={`${th} text-right`}>Paid</th>
                    <th className={`${th} text-right`}>Owes</th>
                    <th className={`${th} text-right`}>Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {view.balances.map((b) => (
                    <tr key={b.person}>
                      <td className={td}>{b.person}</td>
                      <td className={`${td} text-right`}>{inr(b.paid)}</td>
                      <td className={`${td} text-right`}>{inr(b.owed)}</td>
                      <td className={`${td} text-right font-medium ${b.balance < 0 ? "text-red-600" : b.balance > 0 ? "text-green-600" : ""}`}>
                        {b.balance > 0 ? "+" : ""}{inr(b.balance)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>

            <Section title="How to settle up">
              {view.settlements.length === 0 ? (
                <p className="px-4 py-3 text-sm text-slate-600">Nothing to settle.</p>
              ) : (
                <ul>
                  {view.settlements.map((s, i) => (
                    <li key={i} className="border-t border-slate-100 px-4 py-2 text-sm first:border-t-0">
                      {s.from} pays {s.to} <strong>{inr(s.amount)}</strong>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Monthly totals by category">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className={th}>Month</th>
                    <th className={th}>Category</th>
                    <th className={`${th} text-right`}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {months.map((m) =>
                    data.monthly_totals
                      .filter((t) => t.month === m)
                      .map((t, i) => (
                        <tr key={m + t.category}>
                          <td className={td}>{i === 0 ? monthName(m) : ""}</td>
                          <td className={td}>{t.category}</td>
                          <td className={`${td} text-right`}>{inr(t.total)}</td>
                        </tr>
                      ))
                  )}
                </tbody>
              </table>
            </Section>

            <Section title={`Bad rows (${view.badRows.length})`}>
              {view.badRows.length === 0 ? (
                <p className="px-4 py-3 text-sm text-slate-600">No bad rows.</p>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className={th}>Row</th>
                      <th className={th}>Expense</th>
                      <th className={th}>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.badRows.map((r) => (
                      <tr key={r.row}>
                        <td className={td}>{r.row}</td>
                        <td className={td}>{r.expense_id}</td>
                        <td className={td}>{r.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Section>
          </>
        )}
      </main>
    </div>
  );
}
