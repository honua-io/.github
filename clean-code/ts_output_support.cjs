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

function patternEntries(target, value) {
  target = unwrap(target);
  value = unwrap(value);
  if (ts.isArrayLiteralExpression(target) || ts.isArrayBindingPattern(target)) {
    return target.elements.flatMap((entry, index) => ts.isOmittedExpression(entry) ? []
      : patternEntries(entry, value && ts.isArrayLiteralExpression(value) ? value.elements[index] : undefined));
  }
  if (ts.isObjectLiteralExpression(target) || ts.isObjectBindingPattern(target)) {
    return target.properties?.flatMap((entry) => objectEntry(entry, value))
      ?? target.elements.flatMap((entry) => objectEntry(entry, value));
  }
  if (ts.isBindingElement(target)) return patternEntries(target.name, value);
  if (ts.isSpreadElement(target) || ts.isSpreadAssignment(target)) return patternEntries(target.expression, undefined);
  if (ts.isBinaryExpression(target) && target.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
    return patternEntries(target.left, value ?? target.right);
  }
  return [[target, value]];
}

function objectEntry(entry, value) {
  const key = entry.propertyName ?? entry.name;
  const source = value && ts.isObjectLiteralExpression(value)
    ? value.properties.find((property) => property.name?.getText() === key?.getText()) : undefined;
  const target = ts.isPropertyAssignment(entry) ? entry.initializer : entry.name ?? entry.expression;
  return patternEntries(target, source?.initializer);
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

module.exports = { unwrap, copyBindings, sameBindings, mergeBindings, patternEntries, loopLabels, mutatorName };
