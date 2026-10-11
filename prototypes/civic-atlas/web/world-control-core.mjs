const DAY = 86400000;
export function dateValue(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) throw new Error('Use a complete UTC date.');
  const time = Date.parse(`${value}T00:00:00Z`);
  if (!Number.isFinite(time) || new Date(time).toISOString().slice(0, 10) !== value) throw new Error('Use a valid UTC date.');
  return time;
}
export function addDays(value, days) {
  const result = new Date(dateValue(value) + days * DAY).toISOString().slice(0, 10);
  dateValue(result);
  return result;
}
export function validateAdvance(cursor, target) {
  const days = (dateValue(target) - dateValue(cursor)) / DAY;
  if (days < 1 || days > 31) throw new Error('Choose 1–31 new UTC days after the next unprocessed day.');
  return days;
}
// Capture the absolute target before sending. A retry uses that same target,
// so an uncertain response can never turn "next day" into two advances.
export class AdvanceController {
  constructor(request) { this.request = request; this.busy = false; this.uncertain = false; }
  async advance(id, cursor, target) {
    if (this.busy) throw new Error('An advance is already in progress.');
    if (this.uncertain) throw new Error('Refresh the saved status before another advance.');
    validateAdvance(cursor, target);
    this.busy = true;
    try { return await this.request('advance', { id }, { through: target }); }
    catch (error) { this.uncertain = true; throw error; }
    finally { this.busy = false; }
  }
  recovered() { this.uncertain = false; }
}
