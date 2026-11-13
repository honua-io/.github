const ts = require("typescript");
const { unwrap, copyBindings, mergeBindings } = require("./ts_output_support.cjs");

function isPattern(node) {
  node = unwrap(node);
  return ts.isArrayLiteralExpression(node) || ts.isArrayBindingPattern(node)
    || ts.isObjectLiteralExpression(node) || ts.isObjectBindingPattern(node);
}

class Patterns {
  constructor(mutations) {
    this.mutations = mutations;
  }

  evaluate(node) {
    node = unwrap(node);
    if (ts.isArrayLiteralExpression(node) && !node.elements.some(ts.isSpreadElement)) {
      return { aliases: new Set(), state: "present", elements: node.elements.map((entry) =>
        ts.isOmittedExpression(entry) ? this.snapshot() : this.evaluate(entry)) };
    }
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.CommaToken) {
      this.mutations.visit(node.left);
      return this.evaluate(node.right);
    }
    if (ts.isObjectLiteralExpression(node) && !node.properties.some(ts.isSpreadAssignment)) {
      return this.evaluateObject(node);
    }
    this.mutations.visit(node);
    return this.snapshot(node);
  }

  evaluateObject(node) {
    const properties = new Map();
    for (const entry of node.properties) {
      if (ts.isComputedPropertyName(entry.name)) this.mutations.visit(entry.name.expression);
      properties.set(entry.name.getText(), this.evaluate(entry.initializer ?? entry.name));
    }
    return { aliases: new Set(), state: "present", properties };
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
      value.properties = new Map(node.properties.map((entry) => [entry.name?.getText(), this.snapshot(entry.initializer ?? entry.name)]));
      value.state = "present";
    } else if (ts.isLiteralExpression(node) || node.kind === ts.SyntaxKind.NullKeyword) value.state = "present";
    else if (ts.isVoidExpression(node) || ts.isIdentifier(node) && node.text === "undefined") value.state = "missing";
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
        this.assign(entry.expression ?? entry.name, rest);
      } else this.assign(entry, source.elements ? source.elements[index] ?? this.snapshot() : { aliases: new Set(), state: "unknown" });
    });
  }

  object(target, source) {
    const entries = target.properties ?? target.elements;
    const remaining = source.properties ? new Map(source.properties) : undefined;
    for (const entry of entries) {
      if (ts.isSpreadAssignment(entry) || entry.dotDotDotToken) {
        this.assign(entry.expression ?? entry.name, { aliases: new Set(), state: "present", properties: remaining });
        continue;
      }
      const key = entry.propertyName ?? entry.name;
      if (ts.isComputedPropertyName(key)) this.mutations.visit(key.expression);
      const value = source.properties ? source.properties.get(key.getText()) ?? this.snapshot() : { aliases: new Set(), state: "unknown" };
      remaining?.delete(key.getText());
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
