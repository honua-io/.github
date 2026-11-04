export function first(items: number[]) {
  const kept = items.filter((item) => item > 0);
  const doubled = kept.map((item) => item * 2);
  return doubled.length;
}
export function second(items: number[]) {
  const kept = items.filter((item) => item > 0);
  const doubled = kept.map((item) => item * 2);
  return doubled.length;
}
