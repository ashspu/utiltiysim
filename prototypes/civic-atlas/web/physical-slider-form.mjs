// JSON-schema numeric controls. The server owns the schema and physical effects.
const clone = value => structuredClone(value);
export function getPath(value, path) { return path.split('.').reduce((node, key) => node?.[key], value); }
export function setPath(value, path, next) { const keys = path.split('.'); let node = value; for (const key of keys.slice(0, -1)) node = node[key] ||= {}; node[keys.at(-1)] = next; }
export function physicalFields(schema, prefix = '') {
  const result = [];
  for (const [key, field] of Object.entries(schema.properties || {})) {
    if (field['x-supported'] === false || field.readOnly) continue;
    const path = prefix ? `${prefix}.${key}` : key;
    if (field.type === 'object') result.push(...physicalFields(field, path));
    else if (['number', 'integer', 'boolean'].includes(field.type) || (field.type === 'string' && Array.isArray(field.enum))) result.push({ path, schema: field });
  }
  return result;
}
export function physicalDefaults(schema, supplied = {}) {
  const value = {};
  for (const field of physicalFields(schema)) {
    const provided = getPath(supplied, field.path);
    if (provided !== undefined || field.schema.default !== undefined) setPath(value, field.path, provided ?? field.schema.default);
  }
  return value;
}
export function restorePhysicalPreset(schema, defaults, preset = {}) {
  const value = physicalDefaults(schema, defaults);
  for (const field of physicalFields(schema)) {
    const next = getPath(preset, field.path);
    if (next !== undefined) setPath(value, field.path, next);
  }
  return value;
}
export function validatePhysicalValues(schema, value) {
  const errors = [];
  for (const { path, schema: field } of physicalFields(schema)) {
    const next = getPath(value, path);
    if (field.type === 'boolean') { if (typeof next !== 'boolean') errors.push({path,message:'Choose enabled or disabled.'}); continue; }
    if (field.type === 'string') { if (!field.enum.includes(next)) errors.push({path,message:'Choose a supported option.'}); continue; }
    if (typeof next !== 'number' || !Number.isFinite(next)) { errors.push({ path, message: 'Enter a finite number.' }); continue; }
    if (field.type === 'integer' && !Number.isInteger(next)) errors.push({ path, message: 'Enter a whole number.' });
    if (field.minimum !== undefined && next < field.minimum) errors.push({ path, message: `Minimum: ${field.minimum}.` });
    if (field.maximum !== undefined && next > field.maximum) errors.push({ path, message: `Maximum: ${field.maximum}.` });
    if (field.exclusiveMinimum !== undefined && next <= field.exclusiveMinimum) errors.push({ path, message: `Must exceed ${field.exclusiveMinimum}.` });
    if (field.exclusiveMaximum !== undefined && next >= field.exclusiveMaximum) errors.push({ path, message: `Must be below ${field.exclusiveMaximum}.` });
    const multiple = field.multipleOf;
    if (multiple && Math.abs(next / multiple - Math.round(next / multiple)) > 1e-8) errors.push({ path, message: `Use multiples of ${multiple}.` });
  }
  const supported = new Set(physicalFields(schema).map(field => field.path));
  for (const mix of schema['x-distributions'] || []) {
    if (!mix.paths.every(path => supported.has(path))) continue;
    const total = mix.total ?? 100, sum = mix.paths.reduce((sum, path) => sum + getPath(value, path), 0);
    if (!Number.isFinite(sum) || Math.abs(sum - total) > 1e-8) errors.push({ paths: mix.paths, message: `${mix.title || 'Linked mix'} must total ${total}; current total ${Number.isFinite(sum) ? Number(sum.toFixed(8)) : 'incomplete'}.` });
  }
  for(const requirement of schema['x-requires'] || []){
    if(getPath(value,requirement.when)===true&&getPath(value,requirement.path)!==true)errors.push({paths:[requirement.when,requirement.path],message:requirement.message || 'Enable the required physical setting first.'});
  }
  return errors;
}
export function configurationFormSchema(configuration, saved) {
  const properties = {world:configuration.schemas.world};
  if(saved.schemaVersion==='physical-setup/2'&&configuration.schemas.physical)properties.physical=configuration.schemas.physical;
  return {type:'object',properties,...(properties.physical?{'x-requires':[{when:'physical.householdCashflow.enabled',path:'physical.householdFinance.enabled',message:'Recurring household cashflow requires household finances to be enabled.'}]}:{})};
}
export function upgradePhysicalConfiguration(saved, defaults) {
  if(defaults.schemaVersion!=='physical-setup/2'||!defaults.physical)throw new Error('Customer settings are not supported by the current catalog.');
  return {...clone(defaults),world:clone(saved.world)};
}
export function sliderExtent(field, value) {
  let step = field['x-control']?.step ?? field['x-step'] ?? field.multipleOf ?? (field.type === 'integer' ? 1 : 'any');
  // Display extents are distinct from validation bounds. Unbounded server fields
  // keep an exact input; typed values extend the visual slider instead of clipping.
  const center = Number.isFinite(value) ? value : field.default ?? 0;
  let min = field['x-control']?.displayMinimum ?? field['x-slider']?.min ?? field.minimum ?? Math.min(0, center - 20);
  let max = field['x-control']?.displayMaximum ?? field['x-slider']?.max ?? field.maximum ?? Math.max(1, center + 20);
  min = Math.min(min, center); max = Math.max(max, center);
  if(field.minimum !== undefined)min = Math.max(min,field.minimum);
  if(field.maximum !== undefined)max = Math.min(max,field.maximum);
  if (max <= min) max = min + 1;
  // Native range inputs snap to min+n*step. Exact engine-valid values need not
  // share that presentation grid; prevent the browser displaying a different
  // value from the saved exact input. Keep coarse steps when already aligned.
  if(Number.isFinite(step)&&step>0&&Number.isFinite(value)){
    const position=(value-min)/step;
    if(Math.abs(position-Math.round(position))>1e-8)step='any';
  }
  return { min, max, step };
}
export function physicalChoiceLabel(path, field, choice) {
  const supplied=field['x-control']?.optionLabels?.[choice];
  if(supplied)return supplied;
  // Existing physical engine labels, utilsim/world/customer_cashflow.html.
  if(path.split('.').at(-1)==='insufficientCashPolicy')return {
    'available-cash':'Spend available cash; record remainder',
    'all-or-nothing':'Spend only if the whole expense is covered',
  }[choice] || choice;
  return choice;
}
let sequence = 0;
export function renderPhysicalSliderForm(container, schema, options = {}) {
  const defaults = physicalDefaults(schema, options.defaults || {});
  let values = restorePhysicalPreset(schema, defaults, options.values || {});
  const controls = new Map(), scope = `physical-slider-${++sequence}`;
  const make = (tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; };
  container.replaceChildren(); container.classList.add('physical-slider-form');
  const toolbar = make('div'), restore = make('button', 'Restore defaults'); restore.type = 'button'; toolbar.append(restore);
  for (const preset of options.presets || schema['x-presets'] || []) {
    const button = make('button', preset.title || preset.name); button.type = 'button'; button.onclick = () => apply(preset.values); toolbar.append(button);
  }
  container.append(toolbar);
  const summary = make('p'); summary.className = 'physical-errors'; summary.setAttribute('role', 'status'); summary.setAttribute('aria-live', 'polite');
  const groups = new Map();
  for (const { path, schema: field } of physicalFields(schema)) {
    const groupPath = path.split('.').slice(0,-1).join('.');
    if(!groups.has(groupPath)) {
      const group = make('fieldset'); group.className='physical-setting-group';
      const titles=[];let node=schema;for(const part of groupPath.split('.').filter(Boolean)){node=node.properties[part];if(node.title)titles.push(node.title);}
      group.append(make('legend',titles.join(' · ') || 'Physical settings'));groups.set(groupPath,group);container.append(group);
    }
    const section = make('div'); section.className = 'physical-slider-row';
    const id = `${scope}-${path.replaceAll('.', '-')}`, label = make('label', field.title || path); label.htmlFor = `${id}-number`;
    const slider = make('input'); slider.type = 'range'; slider.id = `${id}-range`; slider.setAttribute('aria-label', `${field.title || path} slider`);
    const exact = make('input'); exact.type = 'number'; exact.id = `${id}-number`; exact.setAttribute('aria-describedby', `${id}-help ${id}-error`);
    const help = make('p'); help.id = `${id}-help`; help.className = 'physical-help';
    const marker = make('p'); marker.className = 'physical-default';
    const error = make('p'); error.id = `${id}-error`; error.className = 'physical-errors';
    const effect = field['x-control']?.effect ?? field['x-effect'], unit = field['x-control']?.unit ?? field['x-unit']; help.textContent = [field.description, typeof effect === 'string' ? effect : effect?.description, unit ? `Unit: ${unit}.` : ''].filter(Boolean).join(' ');
    slider.setAttribute('aria-describedby', help.id);
    if(field.type==='boolean' || field.type==='string') {
      const input = field.type==='boolean' ? make('input') : make('select');input.id=`${id}-number`;
      if(field.type==='boolean')input.type='checkbox';else for(const choice of field.enum){const option=make('option',physicalChoiceLabel(path,field,choice));option.value=choice;input.append(option);}
      input.setAttribute('aria-describedby',`${id}-help ${id}-error`);
      section.classList.add('physical-choice-row');section.append(label,input,marker,help,error);groups.get(groupPath).append(section);
      controls.set(path,{field,exact:input,marker,error});
      input.onchange=()=>{setPath(values,path,field.type==='boolean'?input.checked:input.value);update();options.onChange?.(clone(values),validatePhysicalValues(schema,values));};continue;
    }
    const endpoints = make('div');endpoints.className='physical-slider-labels';for(const text of field['x-control']?.labels || [])endpoints.append(make('span',text));
    section.append(label, slider, exact,endpoints, marker, help, error); groups.get(groupPath).append(section);
    controls.set(path, { field, slider, exact, marker, error });
    function change(input) { setPath(values, path, input.value === '' ? NaN : Number(input.value)); update(input === exact ? path : null); options.onChange?.(clone(values), validatePhysicalValues(schema, values)); }
    slider.oninput = () => change(slider); exact.oninput = () => change(exact);
  }
  container.append(summary);
  function update(editingPath) {
    const errors = validatePhysicalValues(schema, values);
    for (const [path, control] of controls) {
      const next = getPath(values, path), baseline = getPath(defaults, path);
      if(!control.slider){
        if(control.field.type==='boolean')control.exact.checked=next===true;else control.exact.value=next??'';
        control.marker.textContent=`Default: ${control.field.type==='boolean'?(baseline?'Enabled':'Disabled'):baseline}${next===baseline?' · current value':''}`;
        const relevant=errors.filter(error=>error.path===path||error.paths?.includes(path));control.error.textContent=relevant.map(error=>error.message).join(' ');control.exact.setAttribute('aria-invalid',String(!!relevant.length));continue;
      }
      const extent = sliderExtent(control.field, next), unit=control.field['x-control']?.unit ?? control.field['x-unit'];
      Object.assign(control.slider, { min: extent.min, max: extent.max, step: extent.step });
      control.exact.step = control.field.multipleOf ?? (control.field.type === 'integer' ? 1 : 'any');
      if (control.field.minimum !== undefined) control.exact.min = control.field.minimum;
      if (control.field.maximum !== undefined) control.exact.max = control.field.maximum;
      if (editingPath !== path) control.exact.value = Number.isFinite(next) ? next : '';
      if (Number.isFinite(next)) control.slider.value = next;
      const atDefault = Number.isFinite(next) && next === baseline;
      const reference=control.field['x-control']?.referenceValue ?? baseline, referenceLabel=control.field['x-control']?.referenceLabel || 'Default';
      control.marker.textContent = baseline === undefined ? 'No server default supplied.' : `Default: ${baseline}${unit ? ` ${unit}` : ''}${atDefault ? ' · current value' : ''}`;
      if(reference!==baseline || referenceLabel!=='Default')control.marker.textContent+=` · ${referenceLabel}: ${reference}`;
      if(Number.isFinite(next)&&Number.isFinite(baseline)&&!atDefault)control.marker.textContent+=next>baseline?' · above preset':' · below preset';
      const position = reference === undefined ? null : Math.max(0, Math.min(100, 100 * (reference - extent.min) / (extent.max - extent.min)));
      control.slider.style.setProperty('--default-position', position === null ? '0%' : `${position}%`);
      control.slider.dataset.hasDefault = String(position !== null);
      const relevant = errors.filter(error => error.path === path || error.paths?.includes(path));
      control.error.textContent = relevant.map(error => error.message).join(' '); control.exact.setAttribute('aria-invalid', String(!!relevant.length));
      // Descriptive server labels carry meaning; age/technology get no invented score.
      const bands = control.field['x-effect']?.bands || [];
      const band = bands.find(band => next >= (band.min ?? -Infinity) && next <= (band.max ?? Infinity));
      if (band?.label) control.marker.textContent += ` · ${band.label}`;
      control.slider.setAttribute('aria-valuetext', `${Number.isFinite(next) ? next : 'unset'}${unit || ''}${band?.label ? ` · ${band.label}` : ''}`);
    }
    summary.textContent = errors.length ? 'Complete the highlighted values before saving.' : '';
  }
  function apply(preset = {}) { values = restorePhysicalPreset(schema, defaults, preset); update(); options.onChange?.(clone(values), validatePhysicalValues(schema, values)); }
  restore.onclick = () => apply(); update();
  return { get values() { return clone(values); }, validate: () => validatePhysicalValues(schema, values), restoreDefaults: () => apply(), applyPreset: apply, setValues: apply };
}
