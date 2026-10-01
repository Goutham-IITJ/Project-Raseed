import { Icon } from "./icon";
export function PeriodSelect({ value, onChange, label = "Time period", custom = false }: { value: string; onChange: (value: string) => void; label?: string; custom?: boolean }) {
  return <label className="select-label"><Icon name="calendar" size={17} /><span className="sr-only">{label}</span><select value={value} onChange={event => onChange(event.target.value)}><option value="this_month">This month</option><option value="last_month">Last month</option><option value="this_week">This week</option><option value="last_week">Last week</option><option value="this_year">This year</option><option value="last_year">Last year</option>{custom && <option value="custom">Custom dates</option>}</select></label>;
}
