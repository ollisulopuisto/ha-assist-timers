# Bolt's Performance Journal

## 2026-11-06 - Dashboard Card Template Global Object Memoization
**Learning:** In client-side Lovelace card templates evaluated at interval ticks (`update_timer: 1000`), caching static translation dictionaries (`I18N`) or string escaping maps (`htmlEscapes`) on `globalThis` creates global namespace pollution and carries side effects (e.g. state retention across config edits or multiple cards) while providing virtually unmeasurable real-world gains compared to the engine's nursery GC on tiny local dicts.
**Action:** Do not memoize small static translation/lookup dictionaries in Lovelace card templates onto `globalThis`; reserve optimizations for true compute bottlenecks, DOM churn, or O(N) object allocations.

## 2026-11-07 - Jinja Direct State Lookup Micro-optimization in Lovelace Badges
**Learning:** Replacing standard `state_attr(entity_id, attribute)` calls with direct `states[entity_id]` dictionary access in Home Assistant Jinja templates introduces significant boilerplate and degrades readability for negligible real-world execution differences on low-frequency update paths (e.g. 5s dashboard updates). Furthermore, direct `states[...]` attribute indexing bypasses standard state safety checks recommended by Home Assistant documentation.
**Action:** Keep idiomatic `state_attr()` in dashboard badge templates; do not replace safe template helpers with direct state dictionary access unless profiling reveals an actual template rendering bottleneck.
