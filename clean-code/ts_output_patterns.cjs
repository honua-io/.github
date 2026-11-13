const ts = require("typescript");
const { unwrap, copyBindings, mergeBindings } = require("./ts_output_support.cjs");

function isPattern(node) {
  node = unwrap(node);
  return ts.isArrayLiteralExpression(node) || ts.isArrayBindingPattern(node)
    || ts.isObjectLiteralExpression(node) || ts.isObjectBindingPattern(node);
}

function propertyKey(node) {
  const computed = ts.isComputedPropertyName(node);
  if (computed) node = unwrap(node.expression);
  if (ts.isIdentifier(node)) return computed ? undefined : node.text;
  if (ts.isNumericLiteral(node)) return String(Number(node.text));
  if (ts.isStringLiteralLike(node)) return node.text;
}

class Patterns {
  constructor(mutations) {
    this.mutations = mutations;
  }

  evaluate(node) {
    node = unwrap(node);
    if (ts.isArrayLiteralExpression(node)) return this.evaluateArray(node);
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.CommaToken) {
      this.mutations.visit(node.left);
      return this.evaluate(node.right);
    }
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      const assign = this.setter(node.left);
      const value = this.evaluate(node.right);
      assign(value);
      return value;
    }
    if (ts.isObjectLiteralExpression(node)) return this.evaluateObject(node);
    this.mutations.visit(node);
    return this.snapshot(node);
  }

  evaluateArray(node) {
    const value = { aliases: new Set(), state: "present", elements: [] };
    for (const entry of node.elements) {
      const spread = ts.isSpreadElement(entry);
      const item = ts.isOmittedExpression(entry) ? this.snapshot() : this.evaluate(spread ? entry.expression : entry);
      if (value.unknownElements) continue;
      if (spread && item.elements) value.elements.push(...item.elements);
      else if (spread) value.unknownElements = true;
      else value.elements.push(item);
      if (spread && item.unknownElements) value.unknownElements = true;
    }
    return value;
  }

  evaluateObject(node) {
    const value = { aliases: new Set(), state: "present", properties: new Map() };
    for (const entry of node.properties) {
      if (ts.isSpreadAssignment(entry)) {
        const spread = this.evaluate(entry.expression);
        if (!spread.properties || spread.unknownProperties) {
          value.properties.clear();
          value.unknownProperties = true;
        }
        for (const [key, item] of spread.properties ?? []) value.properties.set(key, item);
        continue;
      }
      if (ts.isComputedPropertyName(entry.name)) this.mutations.visit(entry.name.expression);
      const item = this.evaluate(entry.initializer ?? entry.name);
      const key = propertyKey(entry.name);
      if (key !== undefined) value.properties.set(key, item);
    }
    return value;
  }

  snapshot(node) {
    node = unwrap(node);
    if (!node) return { aliases: new Set(), state: "missing" };
    if (ts.isBinaryExpression(node) && [ts.SyntaxKind.EqualsToken, ts.SyntaxKind.CommaToken].includes(node.operatorToken.kind)) {
      return this.snapshot(node.right);
    }
    const value = { aliases: this.mutations.aliases(node), state: "unknown" };
    if (ts.isArrayLiteralExpression(node)) {
      value.elements = node.elements.map((entry) => ts.isOmittedExpression(entry) ? this.snapshot() : this.snapshot(entry));
      value.state = "present";
    } else if (ts.isObjectLiteralExpression(node)) {
      value.properties = new Map(node.properties.filter((entry) => entry.name).map((entry) => [propertyKey(entry.name), this.snapshot(entry.initializer ?? entry.name)]));
      value.state = "present";
    } else if (ts.isLiteralExpression(node) || [ts.SyntaxKind.NullKeyword, ts.SyntaxKind.TrueKeyword,
      ts.SyntaxKind.FalseKeyword].includes(node.kind)) value.state = "present";
    else if (ts.isVoidExpression(node) || ts.isIdentifier(node) && node.text === "undefined"
      && !this.mutations.aliasSymbol(node)?.declarations?.length) value.state = "missing";
    return value;
  }

  assign(target, source) {
    target = unwrap(target);
    if (ts.isBindingElement(target)) {
      this.initialize(target.name, source, target.initializer);
    } else if (ts.isBinaryExpression(target) && target.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      this.initialize(target.left, source, target.right);
    } else if (ts.isArrayLiteralExpression(target) || ts.isArrayBindingPattern(target)) {
      this.array(target, source);
    } else if (ts.isObjectLiteralExpression(target) || ts.isObjectBindingPattern(target)) {
      this.object(target, source);
    } else if (ts.isIdentifier(target)) {
      this.mutations.bindings.set(this.mutations.aliasSymbol(target), source.aliases);
    } else this.mutations.record(this.mutations.directReceiver(target));
  }

  initialize(target, source, fallback) {
    const assign = this.setter(target);
    if (!fallback || source.state === "present") return assign(source);
    if (source.state === "missing") {
      return assign(this.evaluate(fallback));
    }
    const initial = copyBindings(this.mutations.bindings);
    assign(source);
    const unchanged = copyBindings(this.mutations.bindings);
    this.mutations.bindings = initial;
    assign(this.evaluate(fallback));
    this.mutations.bindings = mergeBindings([unchanged, this.mutations.bindings]);
  }

  setter(target) {
    const node = unwrap(target);
    if (ts.isElementAccessExpression(node) || ts.isPropertyAccessExpression(node)) {
      const receiver = this.mutations.directReceiver(node);
      return () => this.mutations.record(receiver);
    }
    return (source) => this.assign(target, source);
  }

  array(target, source) {
    target.elements.forEach((entry, index) => {
      if (ts.isOmittedExpression(entry)) return;
      if (ts.isSpreadElement(entry) || ts.isBindingElement(entry) && entry.dotDotDotToken) {
        const rest = { aliases: new Set(), state: "present" };
        if (source.elements) rest.elements = source.elements.slice(index);
        rest.unknownElements = source.unknownElements;
        this.assign(entry.expression ?? entry.name, rest);
      } else this.assign(entry, this.element(source, index));
    });
  }

  element(source, index) {
    if (source.elements?.[index]) return source.elements[index];
    return source.elements && !source.unknownElements ? this.snapshot() : { aliases: new Set(), state: "unknown" };
  }

  object(target, source) {
    const entries = target.properties ?? target.elements;
    const remaining = source.properties ? new Map(source.properties) : undefined;
    for (const entry of entries) {
      if (ts.isSpreadAssignment(entry) || entry.dotDotDotToken) {
        this.assign(entry.expression ?? entry.name, { aliases: new Set(), state: "present", properties: remaining,
          unknownProperties: source.unknownProperties });
        continue;
      }
      const key = entry.propertyName ?? entry.name;
      if (ts.isComputedPropertyName(key)) this.mutations.visit(key.expression);
      const name = propertyKey(key);
      const value = source.properties?.get(name) ?? (source.properties && !source.unknownProperties
        && name !== undefined ? this.snapshot() : { aliases: new Set(), state: "unknown" });
      remaining?.delete(name);
      this.objectEntry(entry, value);
    }
  }

  objectEntry(entry, value) {
    if (ts.isPropertyAssignment(entry)) this.assign(entry.initializer, value);
    else if (ts.isShorthandPropertyAssignment(entry)) this.initialize(entry.name, value, entry.objectAssignmentInitializer);
    else this.assign(entry, value);
  }
}

module.exports = { Patterns, isPattern };
