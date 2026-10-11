import { renderPhysicalSliderForm } from './physical-slider-form.mjs';
// Mirrors utilsim.config.wizard.world_configuration() at base 0067f61.
// x-slider and x-step are presentation metadata, not engine constraints.
const number = (title, value, effect, extra = {}) => ({ type: 'number', title, default: value, 'x-effect': effect, ...extra });
const schema = { type: 'object', properties: {
  weather: { type: 'object', properties: {
    winter_mean_c: number('Winter average', 2, 'Sets the winter end of the seasonal daily temperature curve.', { 'x-unit': '°C', 'x-slider': { min: -20, max: 40 }, 'x-step': .1 }),
    summer_mean_c: number('Summer average', 26, 'Sets the summer end of the seasonal daily temperature curve.', { 'x-unit': '°C', 'x-slider': { min: -20, max: 50 }, 'x-step': .1 }),
    daily_weather_spread_c: number('Daily variation', 6, 'Scales daily temperature variation around the seasonal curve.', { minimum: 0, 'x-unit': '°C', 'x-slider': { max: 20 }, 'x-step': .1 }),
  } },
  meters: { type: 'object', properties: {
    annual_meter_failure: number('Annual base failure probability', .015, 'Changes the annual baseline chance of physical meter failure; the engine also applies meter age.', { minimum: 0, maximum: 1, 'x-step': .001 }),
    annual_meter_drift: number('Annual drift probability', .01, 'Changes the annual probability used for daily physical meter drift onset.', { minimum: 0, maximum: 1, 'x-step': .001 }),
  } },
} };
const output = document.getElementById('values');
const form = renderPhysicalSliderForm(document.getElementById('fields'), schema, { onChange: values => { output.textContent = JSON.stringify(values, null, 2); } });
output.textContent = JSON.stringify(form.values, null, 2);
