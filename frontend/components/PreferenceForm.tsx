'use client';
import { useState, useEffect } from 'react';
import type { Budget, RecommendationRequest } from '@/lib/types';

interface Props {
  cities: string[];
  cuisines: string[];
  onSubmit: (req: RecommendationRequest) => void;
  loading: boolean;
  apiOffline?: boolean;
}

const EXTRAS = ['family-friendly', 'quick service', 'outdoor seating', 'rooftop', 'quiet'];

export default function PreferenceForm({ cities, cuisines, onSubmit, loading, apiOffline }: Props) {
  const [location, setLocation]   = useState('');
  const [custom,   setCustom]     = useState('');

  // Sync first city once API loads
  useEffect(() => {
    if (cities.length > 0 && !location) setLocation(cities[0]);
  }, [cities]);
  const [budget,   setBudget]     = useState<Budget>('medium');
  const [cuisine,  setCuisine]    = useState('North Indian');
  const [rating,   setRating]     = useState(4.0);
  const [extras,   setExtras]     = useState<string[]>([]);
  const [maxRecs,  setMaxRecs]    = useState(5);
  const [error,    setError]      = useState('');

  function toggleExtra(tag: string) {
    setExtras(prev => prev.includes(tag) ? prev.filter(e => e !== tag) : [...prev, tag]);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const loc = custom.trim() || location;
    if (!loc)     { setError('Location is required.'); return; }
    if (!cuisine.trim()) { setError('Cuisine is required.'); return; }
    if (rating < 0 || rating > 5) { setError('Rating must be 0–5.'); return; }
    setError('');
    onSubmit({ location: loc, budget, cuisine: cuisine.trim(), min_rating: rating, extras, max_recommendations: maxRecs });
  }

  const budgetLabels: Record<Budget, string> = { low: 'Low ≤₹400', medium: 'Mid ₹400–800', high: 'High >₹800' };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Location */}
      <div>
        <label className="block text-sm font-bold text-on-surface mb-1">📍 Location</label>
        <select
          value={location}
          onChange={e => setLocation(e.target.value)}
          className="w-full rounded-2xl border border-outline bg-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        >
          {cities.map(c => <option key={c}>{c}</option>)}
        </select>
        <input
          type="text"
          placeholder="Or type a custom location…"
          value={custom}
          onChange={e => setCustom(e.target.value)}
          maxLength={100}
          className="mt-2 w-full rounded-2xl border border-outline bg-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>

      {/* Budget toggle */}
      <div>
        <label className="block text-sm font-bold text-on-surface mb-1">💰 Budget</label>
        <div className="flex gap-2">
          {(Object.keys(budgetLabels) as Budget[]).map(b => (
            <button key={b} type="button"
              onClick={() => setBudget(b)}
              className={`flex-1 text-xs font-bold py-2 rounded-full border transition-all ${
                budget === b
                  ? 'bg-primary text-white border-primary shadow-md'
                  : 'bg-white text-secondary border-outline hover:border-primary/40'
              }`}>
              {budgetLabels[b]}
            </button>
          ))}
        </div>
      </div>

      {/* Cuisine */}
      <div>
        <label className="block text-sm font-bold text-on-surface mb-1">🍜 Cuisine</label>
        <input
          list="cuisine-list"
          value={cuisine}
          onChange={e => setCuisine(e.target.value)}
          maxLength={100}
          placeholder="e.g. North Indian, Italian…"
          className="w-full rounded-2xl border border-outline bg-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        <datalist id="cuisine-list">
          {cuisines.map(c => <option key={c} value={c} />)}
        </datalist>
      </div>

      {/* Rating */}
      <div>
        <label className="block text-sm font-bold text-on-surface mb-1">
          ⭐ Minimum rating — <span className="text-primary">{rating.toFixed(1)}</span>
        </label>
        <input type="range" min={0} max={5} step={0.1} value={rating}
          onChange={e => setRating(parseFloat(e.target.value))}
          className="w-full accent-primary"
        />
        <div className="flex justify-between text-xs text-secondary mt-0.5">
          <span>0</span><span>2.5</span><span>5</span>
        </div>
      </div>

      {/* Extras */}
      <div>
        <label className="block text-sm font-bold text-on-surface mb-2">✨ Extras</label>
        <div className="flex flex-wrap gap-2">
          {EXTRAS.map(tag => (
            <button key={tag} type="button"
              onClick={() => toggleExtra(tag)}
              className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-all ${
                extras.includes(tag)
                  ? 'bg-primary text-white border-primary'
                  : 'bg-white text-secondary border-outline hover:border-primary/40'
              }`}>
              {tag}
            </button>
          ))}
        </div>
      </div>

      {/* Max results */}
      <div>
        <label className="block text-sm font-bold text-on-surface mb-1">
          🎯 Max recommendations — <span className="text-primary">{maxRecs}</span>
        </label>
        <input type="range" min={3} max={10} step={1} value={maxRecs}
          onChange={e => setMaxRecs(parseInt(e.target.value))}
          className="w-full accent-primary"
        />
      </div>

      {error && <p className="text-sm text-red-600 font-medium">{error}</p>}

      <button type="submit" disabled={loading || apiOffline || cities.length === 0}
        className="w-full py-3 rounded-full bg-primary text-white font-bold text-sm shadow-lg shadow-primary/25 hover:bg-primary-dark transition-all disabled:opacity-60 disabled:cursor-not-allowed">
        {apiOffline ? 'API offline — start with: make api' : loading ? 'Finding…' : cities.length === 0 ? 'Loading locations…' : 'Find Restaurants →'}
      </button>
    </form>
  );
}
