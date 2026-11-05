# Motiva — AI Agent UI/UX Backlog

This document contains a ready-to-use backlog for improving **Motiva** with a modern, glassy UI/UX style.

> **Product context:** Motiva (“موجَک”) is an intelligent layer above autonomous mobile robot (AMR) fleets for intralogistics and warehouse automation. It dynamically determines optimal routes in real time, optimizes material flow, and coordinates dozens of robots. This backlog focuses on the operator-facing control room: fleet monitoring, maps, missions, exceptions, safety, analytics, and administration. Before implementation, an AI agent must audit the actual frontend stack, routes, components, data model, realtime infrastructure, permissions, and backend capabilities.

## How to use

1. Copy each section into a separate GitHub Issue, or let an AI coding agent read this file directly.
2. Implement issues in the recommended order.
3. Keep each pull request small and focused.
4. Preserve existing robot-control behavior, APIs, safety rules, permissions, and audit trails.
5. Never allow the UI to bypass safety interlocks, emergency-stop controls, or operator authorization.

## Recommended implementation order

1. Create a reusable glass UI design system
2. Redesign operations console shell and navigation
3. Define accessible glass surface recipes
4. Add a fleet operations dashboard
5. Build a live warehouse map and robot monitoring view
6. Improve robot detail and health monitoring
7. Improve mission and task management
8. Improve exceptions, incidents, and alerts
9. Add material-flow and throughput analytics
10. Improve fleet configuration and zone management
11. Upgrade missions, robots, and events tables
12. Make forms, settings, and errors actionable
13. Improve Persian typography and RTL consistency
14. Add polished light and dark themes
15. Add restrained motion and interaction feedback
16. Meet WCAG AA across primary flows
17. Optimize frontend performance for realtime maps
18. Add safety, security, audit, and quality gates

## Global rules for AI agents

- Preserve existing functionality, APIs, realtime behavior, robot-control logic, permissions, and audit trails.
- Prefer the project’s existing frontend framework, styling system, map library, and component conventions.
- Use design tokens instead of hard-coded colors, spacing, radii, shadows, and blur values.
- Support both Persian/RTL and English/LTR where applicable.
- Maintain WCAG AA contrast and keyboard accessibility.
- Add loading, empty, error, offline, reconnecting, and permission-denied states to new UI.
- Avoid excessive backdrop blur; glassmorphism must not harm map readability or realtime performance.
- Never present AI routing, optimization, or predictions as guaranteed outcomes.
- Make safety-critical controls explicit, permission-controlled, confirmed, and auditable.
- Include screenshots or short recordings in pull requests when UI changes are visible.

---

## 1. Create a reusable glass UI design system

**Labels:** `design-system`, `ui/ux`, `glassmorphism`, `frontend`

### Goal

Establish a high-contrast, control-room-grade visual language for warehouse robotics operations.

### Scope

- Add design tokens for:
  - Color
  - Surface and background
  - Blur
  - Border
  - Shadow
  - Radius
  - Spacing
  - Typography
  - Motion
  - Z-index
  - Robot and mission status colors
- Create reusable components:
  - `GlassCard`
  - `GlassPanel`
  - `GlassButton`
  - `GlassIconButton`
  - `GlassInput`
  - `GlassSelect`
  - `GlassDatePicker`
  - `GlassTable`
  - `GlassTabs`
  - `GlassModal`
  - `GlassDrawer`
  - `GlassPopover`
  - `GlassToast`
  - `GlassTooltip`
  - `GlassSidebar`
  - `GlassTopBar`
  - `RobotStatusBadge`
  - `MissionStatusBadge`
  - `BatteryIndicator`
  - `ConnectivityIndicator`
  - `SeverityIndicator`
  - `MapLegend`
- Support light and dark themes.
- Support RTL/Persian text.

### Acceptance criteria

- [ ] Tokens are defined in a central theme/configuration file.
- [ ] Components use tokens rather than hard-coded styles.
- [ ] Interactive components include hover, focus-visible, active, disabled, loading, and error states.
- [ ] Robot, mission, battery, connectivity, and severity states are visually consistent.
- [ ] Components work in RTL and LTR layouts.
- [ ] Existing screens do not regress.

### AI-agent prompt

```text
Audit Motiva’s frontend stack, routing structure, component library, map library, and styling approach. Create a token-based glass design system for a warehouse robotics operations console. Include accessible robot, mission, battery, connectivity, and severity states. Prefer CSS variables or the project’s existing theme mechanism.
```

---

## 2. Redesign operations console shell and navigation

**Labels:** `ui/ux`, `frontend`, `glassmorphism`

### Goal

Make Motiva feel like a modern warehouse control room: calm, readable, and fast during live operations.

### Requirements

- Responsive application shell.
- Fixed glass sidebar on desktop.
- Collapsible drawer/sidebar on mobile.
- Sticky glass top bar.
- Global search for robots, missions, zones, and incidents where supported.
- Notifications for critical robot, mission, connectivity, and safety events.
- User/profile menu.
- Site or warehouse switcher where supported.
- Environment indicator, such as production, staging, or simulation.
- Theme toggle.
- Clear active-route indication.
- Quick links to live map, fleet, missions, exceptions, and analytics.

### Acceptance criteria

- [ ] Sidebar collapses on smaller viewports.
- [ ] Top bar remains usable while scrolling.
- [ ] Active navigation item is visually and programmatically indicated.
- [ ] All navigation is reachable by keyboard.
- [ ] Environment is clearly identifiable to reduce operational mistakes.
- [ ] Layout works correctly in RTL.
- [ ] No business logic is changed.

### AI-agent prompt

```text
Refactor Motiva’s app layout into a responsive robotics operations console with a glass sidebar, sticky top bar, and content area. Preserve existing routes and data behavior. Include a clear environment indicator and ensure navigation works with keyboard, screen readers, and RTL.
```

---

## 3. Define accessible glass surface recipes

**Labels:** `ui/ux`, `glassmorphism`, `accessibility`

### Goal

Avoid unreadable text, inconsistent blur, and inaccessible contrast.

### Surface variants

| Variant | Use case |
|---|---|
| `subtle` | Page background layers, quiet containers |
| `medium` | KPI cards, panels, filters, forms |
| `elevated` | Modals, drawers, robot controls, incident review, toasts, popovers |

### Requirements

- Use restrained blur and semi-transparent fills.
- Add a subtle 1px light border for definition.
- Guarantee WCAG AA contrast for text, icons, robot statuses, and interactive controls.
- Provide fallbacks when `backdrop-filter` is unavailable.
- Respect `prefers-reduced-motion`.
- Do not reduce readability of maps, robot paths, alerts, or dense operational tables.

### Acceptance criteria

- [ ] `GlassSurface` component exists with `subtle`, `medium`, and `elevated` variants.
- [ ] Contrast passes WCAG AA in light and dark themes.
- [ ] A no-backdrop-filter fallback is implemented.
- [ ] Focus states are visible on glass surfaces.
- [ ] Map overlays and realtime data remain readable.

### AI-agent prompt

```text
Create a GlassSurface primitive with subtle, medium, and elevated variants. Include hover, focus-visible, disabled, loading, and error states. Add reduced-motion and no-backdrop-filter fallbacks.
```

---

## 4. Add a fleet operations dashboard

**Labels:** `feature`, `ui/ux`, `frontend`

### Goal

Give warehouse operators an immediate view of fleet health, throughput, and operational exceptions.

### Dashboard content

- KPI cards:
  - Active robots
  - Idle robots
  - Robots charging
  - Robots offline or disconnected
  - Active missions
  - Queued missions
  - Completed missions
  - Failed or blocked missions
  - Average mission time, where available
  - Throughput or completed transfers, where available
- Charts:
  - Mission volume over time
  - Robot utilization
  - Mission duration distribution
  - Exceptions by type or zone
  - Battery and charging trends
  - Throughput trends
- Filters:
  - Date range
  - Warehouse or site
  - Robot
  - Mission type
  - Zone or area
  - Status
  - Severity

### Acceptance criteria

- [ ] KPI cards are clickable and navigate to filtered views.
- [ ] Charts have accessible labels, legends, and tooltips.
- [ ] Filters update the dashboard without a full-page reload where practical.
- [ ] Loading skeletons are shown during data fetches.
- [ ] Empty, error, offline, and no-permission states are implemented.
- [ ] Operational metrics respect user permissions and data scope.

### AI-agent prompt

```text
Add a fleet operations dashboard to Motiva using existing data sources and metrics. If an endpoint does not exist, create clearly typed mock services marked with TODOs. Use glass KPI cards, charts, filters, and accessible empty/loading/error states.
```

---

## 5. Build a live warehouse map and robot monitoring view

**Labels:** `feature`, `ux`, `frontend`, `realtime`

### Goal

Make robot positions, routes, zones, and operational state understandable at a glance.

### Requirements

- Warehouse floorplan or map view using the project’s existing map/visualization capability.
- Robot markers with status, battery, connectivity, and current mission where available.
- Optional route or path visualization.
- Zone, aisle, dock, charging station, and restricted-area overlays where data exists.
- Map legend with clear color meanings.
- Select a robot or zone to open contextual details.
- Filter robots by status, battery, mission, zone, or connectivity.
- Handle realtime connection loss, reconnecting, stale data, and offline states clearly.
- Avoid obstructing the map with excessive glass panels.

### Acceptance criteria

- [ ] Users can identify robot locations and statuses quickly.
- [ ] Map legend explains all visual states.
- [ ] Users can filter and select robots or zones.
- [ ] Connection and data-freshness states are clear.
- [ ] Map remains readable and performant.
- [ ] Existing realtime and robot data behavior is preserved.

### AI-agent prompt

```text
Improve Motiva’s live warehouse map and robot monitoring view using the existing map and realtime infrastructure. Add clear robot markers, status visualization, filters, contextual details, and connection-state handling. Do not change robot-control behavior.
```

---

## 6. Improve robot detail and health monitoring

**Labels:** `feature`, `ux`, `frontend`

### Goal

Help operators inspect a robot’s state, mission, health, and history quickly.

### Requirements

- Robot header with ID, name, type, status, battery, connectivity, current zone, and active mission.
- Mission history and current mission details where available.
- Health indicators for battery, connectivity, errors, and maintenance state where supported.
- Timeline of robot events, errors, missions, and status changes.
- Safe, permission-aware operator actions only where the backend supports them.
- Require confirmation for consequential robot commands.
- Clearly distinguish observed telemetry from AI-generated insights or predictions.

### Acceptance criteria

- [ ] Users can understand a robot’s current state and history.
- [ ] Battery, connectivity, and error states are clear.
- [ ] Robot actions are permission-aware and confirmed where appropriate.
- [ ] AI insights are distinguishable from telemetry.
- [ ] Loading, empty, error, offline, and unauthorized states are implemented.
- [ ] Existing robot-control and safety behavior is preserved.

### AI-agent prompt

```text
Improve Motiva’s robot detail and health-monitoring UX. Use existing robot telemetry, mission, and event data. Create a clear robot header, timeline, health indicators, and permission-aware actions. Preserve all safety and control behavior.
```

---

## 7. Improve mission and task management

**Labels:** `feature`, `ux`, `frontend`

### Goal

Make material-transfer missions easy to create, monitor, prioritize, and resolve.

### Requirements

- Mission list with type, origin, destination, robot, priority, status, deadline, and progress where available.
- Mission detail with route, assigned robot, milestones, related events, and failure reason.
- Clear workflow states: queued, assigned, in progress, paused, completed, failed, cancelled, or equivalent existing states.
- Create, assign, reprioritize, pause, resume, cancel, and retry actions according to permissions.
- Require confirmation and reason for consequential actions.
- Show queue position and estimated completion only when the backend provides reliable data.
- Preserve an audit trail for every consequential action.

### Acceptance criteria

- [ ] Users can understand mission progress and ownership.
- [ ] Mission failures and blocked states are actionable.
- [ ] Mission actions are permission-aware and confirmed where appropriate.
- [ ] Mission history is traceable.
- [ ] Loading, empty, error, and unauthorized states are implemented.
- [ ] Existing mission orchestration behavior is preserved.

### AI-agent prompt

```text
Improve Motiva’s mission and task-management UX. Create clear mission lists, detail views, progress indicators, failure context, and permission-aware actions. Preserve all routing, orchestration, safety, and audit behavior.
```

---

## 8. Improve exceptions, incidents, and alerts

**Labels:** `feature`, `ux`, `frontend`

### Goal

Help operators identify, prioritize, and resolve robot and warehouse incidents quickly.

### Requirements

- Incident list with severity, type, robot, zone, mission, owner, age, and status.
- Incident detail with timeline, affected robot or mission, likely cause, and recommended next step where available.
- Assignment, acknowledgment, escalation, resolution, and reopening actions based on permissions.
- Require a reason or resolution note for consequential actions.
- Show related robot, mission, map location, and event context.
- Provide filters for open, critical, unassigned, overdue, and resolved incidents.
- Preserve an audit trail for every action.

### Acceptance criteria

- [ ] Users can prioritize incidents effectively.
- [ ] Incident ownership and status are clear.
- [ ] Users can understand operational impact and history.
- [ ] Actions are permission-aware and confirmed where appropriate.
- [ ] Every action is recorded in the existing audit mechanism.
- [ ] Loading, empty, error, and unauthorized states are implemented.

### AI-agent prompt

```text
Improve Motiva’s exception, incident, and alert-management workflow. Create clear incident lists, detail views, assignment and resolution flows, and audit-friendly actions. Preserve all safety and operational behavior.
```

---

## 9. Add material-flow and throughput analytics

**Labels:** `feature`, `ux`, `frontend`

### Goal

Help warehouse teams understand flow efficiency and identify bottlenecks.

### Requirements

- Material-flow overview showing transfer volume, completion rate, cycle time, and bottlenecks where data supports them.
- Zone, route, robot-type, and time-period comparisons where available.
- Trend indicators and comparison against a selected baseline or period.
- Drill-down from a metric to underlying missions or events.
- Clear metric definitions and tooltips.
- Avoid presenting incomplete data as definitive performance.

### Acceptance criteria

- [ ] Users can compare flow performance across relevant dimensions.
- [ ] Metric definitions are understandable.
- [ ] Users can drill down from a metric to source missions.
- [ ] Data limitations and empty states are communicated clearly.
- [ ] Existing calculations and data permissions are preserved.

### AI-agent prompt

```text
Improve Motiva’s material-flow and throughput analytics UX using existing metrics and calculations only. Add clear metric definitions, trends, filters, and drill-down navigation to underlying missions or robots.
```

---

## 10. Improve fleet configuration and zone management

**Labels:** `feature`, `ux`, `frontend`

### Goal

Make warehouse zones, robot settings, and operational rules easier to configure safely.

### Requirements

- Zone list with name, type, status, robot capacity, and associated rules where supported.
- Zone detail with map context, active robots, missions, and recent events.
- Robot configuration views with clear grouping and safe defaults.
- Clear save, saving, saved, unsaved-changes, and discard states.
- Require confirmation for high-impact configuration changes.
- Prevent configuration changes that would bypass safety constraints.
- Preserve an audit trail for configuration changes.

### Acceptance criteria

- [ ] Users can understand warehouse zones and robot assignments.
- [ ] Configuration changes are clear and reversible where supported.
- [ ] High-impact changes are confirmed.
- [ ] Safety constraints remain enforced.
- [ ] Existing configuration and permissions are preserved.

### AI-agent prompt

```text
Improve Motiva’s fleet configuration and zone-management UX using existing configuration and map capabilities. Do not alter routing, safety, or robot-control logic. Add clear configuration states, map context, and confirmation for high-impact changes.
```

---

## 11. Upgrade missions, robots, and events tables

**Labels:** `ui/ux`, `performance`, `frontend`

### Goal

Make large volumes of robots, missions, events, and incidents fast to review.

### Requirements

- Sticky headers.
- Column sorting.
- Advanced filtering by date, robot, mission, zone, status, severity, and owner.
- Saved views or operational queues where supported.
- Pagination or virtualization for large datasets.
- CSV export only when authorized and safe.
- Numeric alignment and localized number/date formatting.
- Bulk actions with confirmation and permission checks.
- Loading skeletons.
- Mobile-friendly behavior through responsive columns or a detail drawer.

### Acceptance criteria

- [ ] A reusable data-table component exists.
- [ ] Large datasets remain responsive.
- [ ] Filters and exports do not block the UI.
- [ ] Bulk actions are permission-aware and confirmed.
- [ ] Persian and English number/date formats are handled correctly.
- [ ] Empty and error states are implemented.

### AI-agent prompt

```text
Audit Motiva’s robot, mission, event, and incident tables. Implement a reusable high-performance data table with filtering, sorting, bulk actions, and export only where the backend and permissions support them.
```

---

## 12. Make forms, settings, and errors actionable

**Labels:** `ux`, `frontend`, `accessibility`

### Goal

Help administrators configure sites, robots, zones, integrations, and user preferences confidently.

### Requirements

- Inline field-level validation.
- Summary of validation failures at the top of long forms.
- Links from summary items to the relevant fields.
- Distinct handling for validation errors, permission errors, connectivity errors, and system failures.
- Preserve user input after an error.
- Clear save, saving, saved, unsaved-changes, and discard states.
- Group related settings and use progressive disclosure for advanced options.
- Require confirmation for high-impact configuration changes.

### Acceptance criteria

- [ ] A shared error-message catalog exists.
- [ ] Error messages are specific and actionable.
- [ ] Users can recover from failed submissions without losing input.
- [ ] Connectivity failures are handled gracefully.
- [ ] Errors are announced accessibly.
- [ ] Persian and English messages are available.

### AI-agent prompt

```text
Standardize Motiva’s form, settings, and API error handling. Create a shared error-message catalog and ensure validation, permission, connectivity, and system failures are visible, specific, and recoverable.
```

---

## 13. Improve Persian typography and RTL consistency

**Labels:** `i18n`, `ui/ux`, `accessibility`

### Goal

Make the Persian-first robotics console feel native and polished.

### Requirements

- Use a high-quality Persian font with sensible fallbacks.
- Set correct `dir`, alignment, punctuation, numerals, and mixed Persian/English handling.
- Test dashboards, maps, robot details, missions, tables, forms, modals, and toasts in RTL.
- Avoid mirroring direction-sensitive icons.
- Prevent clipping or overflow with longer Persian labels.
- Handle robot IDs, coordinates, zone names, URLs, and technical values correctly in bidirectional text.

### Acceptance criteria

- [ ] All primary screens render correctly in RTL.
- [ ] Mixed Persian/English content is readable.
- [ ] Icons with directional meaning are not incorrectly mirrored.
- [ ] No major text overflow or clipping.
- [ ] Typography hierarchy is consistent.

### AI-agent prompt

```text
Audit every Motiva screen for RTL and Persian typography issues. Fix layout mirroring, icon direction, number formatting, bidirectional text handling, and overflow. Add visual regression checks if the project has a testing setup.
```

---

## 14. Add polished light and dark themes

**Labels:** `ui/ux`, `glassmorphism`, `frontend`

### Goal

Provide a premium dark control-room experience without losing map or operational readability.

### Requirements

- Theme toggle persisted in user preferences.
- Default to the operating-system preference.
- Use tokens rather than hard-coded colors.
- Tune glass opacity, blur, borders, and shadows separately per theme.
- Ensure maps, charts, tables, badges, timelines, and status indicators remain legible.

### Acceptance criteria

- [ ] Users can switch between light and dark themes.
- [ ] Theme preference persists across sessions.
- [ ] All major screens are verified in both themes.
- [ ] Hard-coded colors are replaced with tokens.
- [ ] Glass surfaces remain readable in dark mode.

### AI-agent prompt

```text
Implement theme tokens and a persisted light/dark toggle for Motiva. Refactor hard-coded colors into tokens. Verify dashboards, maps, robots, missions, incidents, and settings in both themes.
```

---

## 15. Add restrained motion and interaction feedback

**Labels:** `ui/ux`, `glassmorphism`, `accessibility`

### Goal

Make the interface feel responsive without distracting operators from live warehouse activity.

### Requirements

- Subtle transitions for page changes, drawers, modals, toasts, popovers, and hover states.
- UI feedback animations should generally be 200–300ms or less.
- Loading skeletons.
- Success and error toasts.
- Optimistic updates only for safe actions, with rollback on failure.
- Respect `prefers-reduced-motion`.

### Acceptance criteria

- [ ] Motion tokens are centralized.
- [ ] Interactive components have consistent transitions.
- [ ] Reduced-motion users receive a non-animated equivalent.
- [ ] Animations do not delay comprehension of robot, mission, or incident status.
- [ ] No excessive or decorative animation is added.

### AI-agent prompt

```text
Add a motion token set and apply consistent transitions to Motiva’s interactive components. Ensure reduced-motion users get a non-animated equivalent.
```

---

## 16. Meet WCAG AA across primary flows

**Labels:** `accessibility`, `ui/ux`

### Goal

Ensure the redesigned operations console is usable by everyone.

### Requirements

- Visible focus rings on all interactive elements.
- Keyboard-only operation for navigation, maps, tables, filters, forms, modals, drawers, and robot actions.
- Semantic HTML, landmarks, labels, and ARIA only where necessary.
- WCAG AA contrast, including text over glass surfaces and map overlays.
- Screen-reader testing for fleet monitoring, mission management, and incident review.
- Do not rely on color alone to communicate robot, mission, battery, or incident status.

### Acceptance criteria

- [ ] All interactive controls are keyboard accessible.
- [ ] Focus is visible and logically managed.
- [ ] Modals, drawers, and popovers manage focus appropriately.
- [ ] Operational status is conveyed with text or icons as well as color.
- [ ] Primary flows pass WCAG AA checks.

### AI-agent prompt

```text
Run an accessibility review of Motiva’s primary pages and flows. Fix issues without changing backend behavior. Prioritize keyboard navigation, focus management, contrast, semantic structure, and non-color-dependent operational status indicators.
```

---

## 17. Optimize frontend performance for realtime maps

**Labels:** `performance`, `frontend`, `realtime`

### Goal

Keep the glass UI fast for live maps, robot telemetry, and data-heavy operational tables.

### Requirements

- Avoid excessive nested backdrop filters and large blur radii.
- Lazy-load routes, maps, charts, timelines, and heavy components.
- Virtualize long robot, mission, event, or incident lists only where justified.
- Throttle or batch high-frequency telemetry updates where appropriate.
- Memoize expensive map, chart, and table calculations where appropriate.
- Add skeleton loaders and avoid layout shift.
- Measure rendering, interaction, and network performance before and after changes.

### Acceptance criteria

- [ ] Heavy routes and components are code-split or lazy-loaded where appropriate.
- [ ] Glass effects do not cause severe scroll, pan, zoom, or interaction jank.
- [ ] Live map updates remain smooth.
- [ ] Large operational tables remain responsive.
- [ ] Layout shift is minimized.
- [ ] Before/after performance metrics are documented.
- [ ] No functional regressions are introduced.

### AI-agent prompt

```text
Profile Motiva’s live map, fleet dashboard, and mission-management flows. Identify render, realtime-update, bundle, map, chart, table, and blur-performance bottlenecks, then optimize without changing functionality. Document before/after metrics in the pull request.
```

---

## 18. Add safety, security, audit, and quality gates

**Labels:** `safety`, `security`, `privacy`, `testing`, `ui/ux`, `frontend`

### Goal

Ensure the redesigned console remains safe, secure, auditable, and maintainable.

### Requirements

- Verify role-based access for every new screen, action, export, and sensitive operational control.
- Make emergency, stop, pause, resume, and robot-command controls explicit, permission-controlled, confirmed, and auditable.
- Prevent UI actions from bypassing safety interlocks or authorization rules.
- Mask or restrict sensitive site, robot, customer, and operational data where appropriate.
- Ensure consequential operator actions remain auditable.
- Add or improve linting, type checking, formatting, and test checks.
- Add unit tests for reusable UI components where a test setup exists.
- Add visual regression coverage for light/dark and RTL/LTR states where practical.
- Test primary flows: dashboard, live map, robot detail, missions, incidents, and settings.
- Document how contributors run checks locally.

### Acceptance criteria

- [ ] New UI respects existing authentication and authorization rules.
- [ ] Safety-critical controls cannot be accessed or triggered without appropriate authorization.
- [ ] Sensitive data is not exposed in DOM, logs, exports, or client state.
- [ ] Consequential actions are auditable.
- [ ] Contributors can run quality checks with a documented command where practical.
- [ ] Core reusable components have tests or documented manual test steps.
- [ ] Visual checks cover RTL and dark mode where tooling exists.
- [ ] CI fails on meaningful safety, security, UI, type, lint, or accessibility regressions.

### AI-agent prompt

```text
Audit Motiva’s safety, security, authorization, audit, test, and CI setup. Ensure the glass UI redesign does not weaken safety interlocks, expose sensitive operational data, or allow unauthorized robot control. Add pragmatic quality gates without over-engineering the project.
```
