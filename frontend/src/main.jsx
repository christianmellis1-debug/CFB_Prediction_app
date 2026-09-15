import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';

// In production the Node server proxies /api to the prediction service.
// VITE_API_URL is only needed when running the Vite dev server directly.
const API = import.meta.env.VITE_API_URL || '';
const pct = value => `${(Number(value || 0) * 100).toFixed(1)}%`;

function GameCard({game}) {
  const signal = Number(game['Expected Value'] || 0) > 0 ? 'Value' : 'Pass';
  return <article className="game-card">
    <div className="card-meta"><span>{game.Status || 'Awaiting final'}</span><span className={`confidence ${String(game['Confidence Label'] || '').toLowerCase().replace(/[^a-z]+/g,'-')}`}>{game['Confidence Label']}</span></div>
    <div className="teams"><div><img src={game['Away Logo']} /><span>{game['Away Team']}</span><b>{pct(game['Away Win %'])}</b></div><div className="at">@</div><div><img src={game['Home Logo']} /><span>{game['Home Team']}</span><b>{pct(game['Home Win %'])}</b></div></div>
    <div className="pick"><small>MODEL PICK</small><strong>{game['Predicted Winner']}</strong><span>{pct(game.Confidence)} confidence · {signal}</span></div>
    <div className="odds"><span>Moneyline</span><b>{game['Away ML'] || 'Unavailable'} / {game['Home ML'] || 'Unavailable'}</b></div>
    {game['Actual Winner'] && game['Actual Winner'] !== '—' && <div className="result">Final: {game['Final Score']} · {game['Predicted Winner'] === game['Actual Winner'] ? 'Correct' : 'Incorrect'}</div>}
  </article>;
}

function App() {
  const [season, setSeason] = useState(new Date().getUTCMonth() >= 6 ? new Date().getUTCFullYear() : new Date().getUTCFullYear()-1);
  const [week, setWeek] = useState(1), [weeks, setWeeks] = useState([]), [data, setData] = useState(null), [error, setError] = useState('');
  useEffect(() => { fetch(`${API}/api/weeks?season=${season}`).then(r=>r.json()).then(x=>{setWeeks(x.weeks||[]); if (x.weeks?.length && !x.weeks.includes(week)) setWeek(x.weeks[0]);}).catch(e=>setError(e.message)); }, [season]);
  useEffect(() => { if (!week) return; setData(null); fetch(`${API}/api/predictions?season=${season}&week=${week}`).then(r=>r.json()).then(setData).catch(e=>setError(e.message)); }, [season, week]);
  return <main><header className="hero"><div className="ball">🏈</div><div><p className="eyebrow">SATURDAY SCOUTING REPORT · COLLEGE FOOTBALL</p><h1>Your weekly game plan.</h1><p>Every matchup. A clear pick. Confidence at a glance.</p></div></header>
    <section className="controls"><label>Season<input type="number" value={season} onChange={e=>setSeason(Number(e.target.value))}/></label><label>Week<select value={week} onChange={e=>setWeek(Number(e.target.value))}>{weeks.map(w=><option key={w} value={w}>Week {w}</option>)}</select></label><button onClick={()=>{setData(null); fetch(`${API}/api/predictions?season=${season}&week=${week}`).then(r=>r.json()).then(setData)}}>Refresh</button></section>
    {error && <div className="error">{error}. Start the API with <code>uvicorn backend.main:app --reload</code>.</div>}
    {data && <><div className="summary"><div><b>{data.games.length}</b><span>Matchups</span></div><div><b>{data.games.filter(g=>Number(g.Confidence)>=.8).length}</b><span>High confidence</span></div><div><b>{data.games.filter(g=>Number(g.Confidence)<.6).length}</b><span>Toss-ups</span></div></div><div className="grid">{data.games.map((g,i)=><GameCard game={g} key={g['Game ID'] || i}/>)}</div></>}
  </main>;
}

createRoot(document.getElementById('root')).render(<App/>);
