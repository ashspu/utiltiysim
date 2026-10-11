# Physical slider form integration

Reusable UI only; no workspace, server catalog, physical engine or billing edits. Created at Greg's direct request on 2026-10-11. Parent shell owner integrates after the backend publishes its tested schema. Broader physical assumptions can include meter technology mix, housing age, household behavior and finances. Virtual Systems continues to own staffing, throughput, enterprise queues and billing decisions.

Publish `physical-slider-form.mjs` and `physical-slider-form.css` and import:

```js
import { renderPhysicalSliderForm } from './physical-slider-form.mjs';
const form = renderPhysicalSliderForm(container, server.schemas.world, {
  defaults: server.defaults.world,
  values: draft.configuration.world,
  presets: server.presets, // optional [{title,values}]
  onChange(values, errors) {
    draft.configuration.world = values;
    saveButton.disabled = errors.length > 0;
  },
});
// Save only after form.validate() returns []; backend validates again.
```

The renderer traverses nested object `properties`, rendering writable `number` and `integer` fields. Server-provided `x-supported:false` and `readOnly:true` fields are excluded along with their values. It uses `title`, `description`, `default`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`. Unknown nonnumeric fields need separate renderers and must not silently be treated as slider values. Do not replace a complete configuration with this numeric-only result when a future schema includes nonnumeric editable settings; merge its supported numeric paths into the complete draft instead.

Optional presentation extensions:

- `x-unit`: displayed unit.
- `x-step`: slider step; this is presentation, not an additional validation constraint. Use `multipleOf` for authoritative precision.
- `x-slider:{min,max}`: visual extents only, used when corresponding server bounds are absent. Exact inputs remain unbounded and sliders expand to include typed values. No invented engine restriction.
- `x-effect`: plain description string, or `{description,bands:[{min,max,label}]}`. Band labels appear alongside the default marker and in slider assistive text. Effects/severity labels must be server supplied; age/technology fields get no invented good/bad score.
- Root `x-distributions:[{title,paths:['meters.ami','meters.amr','meters.manual'],total:100}]`: linked shares must total 100 (or declared total) within floating tolerance. Invalid totals highlight all linked fields. Editing one share never silently reallocates another. Distributions referencing unsupported fields are excluded.
- Root `x-presets:[{title,values}]` or `options.presets`: a preset starts from all server defaults and replaces only supported paths. Restore defaults uses the same path. Values/defaults are cloned, never mutated by the renderer.

API returns cloned `values`, `validate()`, `restoreDefaults()`, `applyPreset(values)` and `setValues(values)`. `setValues` resets unspecified numeric fields to defaults; it does not perform a partial patch. Missing defaults remain unset/invalid rather than inventing physical assumptions.

Preview `/physical-slider-demo.html` plus `physical-slider-demo.mjs` uses the exact existing five fields and engine defaults from base `0067f61`, with explicitly separate slider presentation extents. It is a component demonstration, saves nothing, and should not be exposed as a working world builder. Production should pass fresh server schema, not copy the demo fixture.

Verification: six Node tests pass in `test_physical_slider_form.mjs`: supported-field filtering, linked mix validation, numeric/integer/precision constraints, full preset/default restoration without mutation, unbounded slider extents, exclusive bounds. Syntax check passes. Approved CUA opening the local preview timed out twice; visual/mobile/keyboard browser QA remains an integration gate. No alternative browser automation or deployment used.

Standing chat continuity authority: Greg, 2026-10-11, chat `01a12aa3-5c1e-7142-aad0-dd177c7c9f09`. Root owns relevant #vbs-agents coordination and release.
