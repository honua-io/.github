const ts = require("typescript");

function unwrap(node) {
  while (node && (ts.isParenthesizedExpression(node) || ts.isAsExpression(node)
      || ts.isTypeAssertionExpression(node) || ts.isNonNullExpression(node)
      || ts.isSatisfiesExpression(node))) node = node.expression;
  return node;
}

function copyBindings(bindings) {
  return new Map([...bindings].map(([key, values]) => [key, new Set(values)]));
}

function sameBindings(left, right) {
  return left.size === right.size && [...left].every(([key, values]) =>
    values.size === right.get(key)?.size && [...values].every((value) => right.get(key).has(value)));
}

function mergeBindings(endings) {
  const merged = new Map();
  for (const ending of endings) {
    for (const [symbol, names] of ending) {
      merged.set(symbol, new Set([...(merged.get(symbol) ?? []), ...names]));
    }
  }
  return merged;
}

function loopLabels(node) {
  const labels = new Set();
  for (let parent = node.parent; parent && ts.isLabeledStatement(parent); parent = parent.parent) {
    labels.add(parent.label.text);
  }
  return labels;
}

function mutatorName(callee) {
  if (ts.isPropertyAccessExpression(callee)) return callee.name.text;
  if (ts.isElementAccessExpression(callee) && (ts.isStringLiteral(callee.argumentExpression)
      || ts.isNoSubstitutionTemplateLiteral(callee.argumentExpression))) return callee.argumentExpression.text;
}

module.exports = { unwrap, copyBindings, sameBindings, mergeBindings, loopLabels, mutatorName };
