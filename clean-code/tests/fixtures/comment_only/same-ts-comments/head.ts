export function hosts(text: string): string[] {
  const scheme = /https?:\/\//g;
  return text.split(scheme).map((part) => `${part} // kept text`);
}
