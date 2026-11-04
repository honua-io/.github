export function first(items: number[]) {
  const kept = items.filter((item) => item > 0);
  return kept.length;
}
