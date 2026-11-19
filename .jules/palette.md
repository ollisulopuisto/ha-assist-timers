## 2026-11-19 - button-card re-render destroys keyboard focus in custom fields

**Learning:** A `custom_fields` template in button-card is re-evaluated and its HTML replaced on every `update_timer` tick. Any `tabindex`/`role="button"` rows inside it look keyboard-accessible in markup, but a focused row silently loses focus to `<body>` within one second, so tabbing through the card never works. Verified in headless Chrome with the real button-card runtime (button-card v7.0.1).

**Action:** When adding keyboard support to a button-card custom field, give each control a stable `data-focus-key`, capture `shadowRoot.activeElement` during the template evaluation, and restore focus in a `setTimeout(0)` after the commit only when focus was actually dropped and has not moved elsewhere. Update the optimistic `aria-label` too, so the name always describes the next press.
