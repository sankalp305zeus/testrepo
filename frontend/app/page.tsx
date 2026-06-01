'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { HealthResponse, RecommendationRequest, RecommendationResponse } from '@/lib/types';
import Header         from '@/components/Header';
import PreferenceForm from '@/components/PreferenceForm';
import LoadingState   from '@/components/LoadingState';
import RestaurantCard from '@/components/RestaurantCard';
import EmptyState     from '@/components/EmptyState';
import FallbackBanner from '@/components/FallbackBanner';

type View     = 'init' | 'form' | 'loading' | 'results' | 'empty' | 'error';
type LoadStep = 'filter' | 'ai' | 'rank';

export default function Home() {
  const [cities,      setCities]      = useState<string[]>([]);
  const [cuisines,    setCuisines]    = useState<string[]>([]);
  const [health,      setHealth]      = useState<HealthResponse | null>(null);
  const [view,        setView]        = useState<View>('init');
  const [loadStep,    setLoadStep]    = useState<LoadStep>('filter');
  const [result,      setResult]      = useState<RecommendationResponse | null>(null);
  const [apiError,    setApiError]    = useState('');
  const [apiOffline,  setApiOffline]  = useState(false);

  // Fetch catalog metadata on mount
  useEffect(() => {
    Promise.all([api.health(), api.cities(), api.cuisines()])
      .then(([h, c, cu]) => {
        setHealth(h);
        setCities(c.cities);
        setCuisines(cu.cuisines);
        setView('form');
      })
      .catch(() => {
        setApiOffline(true);
        setView('form');   // still show form — user sees the offline warning
      });
  }, []);

  async function handleSubmit(req: RecommendationRequest) {
    setView('loading');
    setLoadStep('filter');
    await new Promise(r => setTimeout(r, 600));
    setLoadStep('ai');
    try {
      const res = await api.recommendations(req);
      setLoadStep('rank');
      await new Promise(r => setTimeout(r, 400));
      setResult(res);
      setView(res.filter_code !== 'OK' || res.recommendations.length === 0 ? 'empty' : 'results');
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Unexpected error');
      setView('error');
    }
  }

  function reset() { setView('form'); setResult(null); setApiError(''); }

  return (
    <div className="min-h-screen bg-surface">
      <Header health={health} />

      <div className="max-w-5xl mx-auto px-4 py-8">

        {/* API offline banner */}
        {apiOffline && (
          <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-2xl px-5 py-3 mb-6 text-sm text-red-800">
            <span className="text-lg">⚠️</span>
            <span>
              <strong>Backend not reachable.</strong> Start the FastAPI server:{' '}
              <code className="bg-red-100 px-1.5 py-0.5 rounded text-xs">make api</code>
            </span>
          </div>
        )}

        {/* ── INIT spinner ──────────────────────────────────────────── */}
        {view === 'init' && (
          <div className="flex flex-col items-center justify-center py-24 gap-4 text-secondary">
            <div className="w-10 h-10 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
            <p className="text-sm">Loading catalog from API…</p>
          </div>
        )}

        {/* ── FORM ──────────────────────────────────────────────────── */}
        {view === 'form' && (
          <div className="flex flex-col lg:flex-row gap-8">
            {/* Left: hero */}
            <div className="lg:w-1/2 flex flex-col justify-center">
              <p className="text-xs font-bold uppercase tracking-widest text-primary mb-3">
                AI-powered discovery
              </p>
              <h1 className="text-3xl lg:text-4xl font-extrabold text-on-surface leading-tight mb-4">
                Find your perfect<br />
                <span className="bg-gradient-to-r from-primary to-purple-700 bg-clip-text text-transparent">
                  restaurant
                </span>
              </h1>
              <p className="text-secondary text-sm mb-6">
                Tell us what you want. We search{' '}
                <strong>{health ? health.catalog_size.toLocaleString() : '40,000'}+</strong>{' '}
                restaurants across Bangalore and explain every pick.
              </p>
              <div className="flex flex-col gap-3">
                {([
                  ['🔍', 'Filter',    'We narrow the catalog using your location, budget & cuisine'],
                  ['🤖', 'AI Rank',   'Groq AI ranks picks with personalised 1-sentence explanations'],
                  ['✨', 'Discover',  'Top results with ratings, estimated cost & reasons'],
                ] as [string, string, string][]).map(([icon, title, desc]) => (
                  <div key={title} className="flex items-center gap-3 bg-white rounded-2xl px-4 py-3 border border-outline shadow-sm">
                    <span className="text-xl">{icon}</span>
                    <div>
                      <p className="text-sm font-bold text-on-surface">{title}</p>
                      <p className="text-xs text-secondary">{desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right: preference form */}
            <div className="lg:w-1/2 bg-white rounded-3xl p-6 shadow-sm border border-outline">
              <h2 className="text-lg font-extrabold text-on-surface mb-1">Your preferences</h2>
              {cities.length > 0
                ? <p className="text-xs text-secondary mb-4">{cities.length} local areas available</p>
                : apiOffline
                ? <p className="text-xs text-red-500 mb-4">Start the API to load locations</p>
                : <p className="text-xs text-secondary mb-4">Loading locations…</p>
              }
              <PreferenceForm
                cities={cities}
                cuisines={cuisines}
                onSubmit={handleSubmit}
                loading={false}
                apiOffline={apiOffline}
              />
            </div>
          </div>
        )}

        {/* ── LOADING ───────────────────────────────────────────────── */}
        {view === 'loading' && <LoadingState step={loadStep} />}

        {/* ── ERROR ─────────────────────────────────────────────────── */}
        {view === 'error' && (
          <div className="text-center py-16">
            <div className="text-5xl mb-4">⚠️</div>
            <h2 className="text-xl font-extrabold mb-2">Something went wrong</h2>
            <p className="text-sm text-secondary mb-6 max-w-md mx-auto">{apiError}</p>
            <button onClick={reset}
              className="px-6 py-2.5 rounded-full border-2 border-primary text-primary font-bold text-sm hover:bg-primary-light transition-all">
              ← Try again
            </button>
          </div>
        )}

        {/* ── EMPTY ─────────────────────────────────────────────────── */}
        {view === 'empty' && result && (
          <EmptyState hints={result.hints} onReset={reset} />
        )}

        {/* ── RESULTS ───────────────────────────────────────────────── */}
        {view === 'results' && result && (
          <div>
            {result.summary && (
              <div className="flex items-center gap-3 rounded-2xl px-5 py-3 mb-4 border border-primary/20"
                   style={{ background: 'linear-gradient(135deg,rgba(183,18,42,0.06),rgba(126,34,206,0.06))' }}>
                <span className="text-primary font-bold">✦</span>
                <span className="text-sm font-semibold bg-gradient-to-r from-primary to-purple-700 bg-clip-text text-transparent">
                  {result.summary}
                </span>
              </div>
            )}
            {result.used_fallback && <FallbackBanner />}
            <div className="flex items-center justify-between mb-4">
              <p className="text-xs text-secondary">
                {result.shortlist_size} candidates · {result.recommendations.length} recommendations · {result.latency_ms} ms
              </p>
              <button onClick={reset}
                className="text-xs font-bold text-primary border border-primary/30 rounded-full px-3 py-1 hover:bg-primary-light transition-all">
                ← Adjust preferences
              </button>
            </div>
            {result.recommendations.map((item, i) => (
              <RestaurantCard key={item.restaurant_name} item={item} index={i} isFallback={result.used_fallback} />
            ))}
          </div>
        )}

      </div>
    </div>
  );
}
