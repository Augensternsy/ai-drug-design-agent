export function evaluationPercent(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value) || value < 0 || value > 100) return null;
  const percentage = value <= 1 ? value * 100 : value;
  return Math.round(percentage * 10) / 10;
}
