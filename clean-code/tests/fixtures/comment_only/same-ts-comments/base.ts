/** Restates the function. */
export function hosts(text: string): string[] {
  const scheme = /https?:\/\//g; // a regex, not a comment
  // explains nothing
  return text.split(scheme).map((part) => `${/* inside */ part} // kept text`);
}
