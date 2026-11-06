# Bolt's Performance Journal

## 2026-11-06 - Dashboard Card Template Global Object Memoization
**Learning:** In client-side Lovelace card templates evaluated at interval ticks (`update_timer: 1000`), caching static translation dictionaries (`I18N`) or string escaping maps (`htmlEscapes`) on `globalThis` creates global namespace pollution and carries side effects (e.g. state retention across config edits or multiple cards) while providing virtually unmeasurable real-world gains compared to the engine's nursery GC on tiny local dicts.
**Action:** Do not memoize small static translation/lookup dictionaries in Lovelace card templates onto `globalThis`; reserve optimizations for true compute bottlenecks, DOM churn, or O(N) object allocations.
