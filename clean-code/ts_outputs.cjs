// Resolve lexical bindings before tracking direct mutations of caller-owned collections.
const ts = require("typescript");
const MUTATORS = new Set([
  "push", "pop", "shift", "unshift", "splice", "sort", "reverse", "fill", "copyWithin",
  "add", "set", "delete", "clear",
]);

function copyBindings(bindings) {
  return new Map([...bindings].map(([key, values]) => [key, new Set(values)]));
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

class Mutations {
  constructor(functionNode, checker) {
    this.checker = checker;
    this.outputs = new Set();
    this.bindings = new Map(functionNode.parameters.filter((parameter) => ts.isIdentifier(parameter.name)).map((parameter) => [
      checker.getSymbolAtLocation(parameter.name), new Set([parameter.name.getText()]),
    ]));
  }

  aliases(node) {
    if (!node) return new Set();
    if (ts.isParenthesizedExpression(node)) return this.aliases(node.expression);
    const symbol = ts.isIdentifier(node) ? this.checker.getSymbolAtLocation(node) : undefined;
    return new Set(symbol ? this.bindings.get(symbol) ?? [] : []);
  }

  bind(target, value) {
    if (ts.isIdentifier(target)) {
      this.bindings.set(this.checker.getSymbolAtLocation(target), this.aliases(value));
    }
  }

  mark(target) {
    if (!ts.isElementAccessExpression(target) && !ts.isPropertyAccessExpression(target)) return;
    for (const name of this.aliases(target.expression)) this.outputs.add(name);
  }

  branches(paths) {
    const initial = copyBindings(this.bindings);
    const endings = paths.map((path) => {
      this.bindings = copyBindings(initial);
      return !path || this.visit(path) !== false ? this.bindings : undefined;
    });
    this.bindings = mergeBindings(endings.filter(Boolean));
    return endings.some(Boolean);
  }

  statements(nodes) {
    for (const node of nodes) if (this.visit(node) === false) return false;
    return true;
  }

  loop(node) {
    if (node.initializer && !ts.isForOfStatement(node) && !ts.isForInStatement(node)) this.visit(node.initializer);
    if (node.condition ?? node.expression) this.visit(node.condition ?? node.expression);
    const initial = copyBindings(this.bindings);
    if (ts.isForOfStatement(node) || ts.isForInStatement(node)) {
      const target = ts.isVariableDeclarationList(node.initializer)
        ? node.initializer.declarations[0].name : node.initializer;
      this.bind(target, undefined);
    }
    const fallsThrough = this.visit(node.statement) !== false;
    if (node.incrementor && fallsThrough) this.visit(node.incrementor);
    this.bindings = mergeBindings(fallsThrough ? [initial, this.bindings] : [initial]);
  }

  assignment(node) {
    this.visit(node.right);
    this.visit(node.left);
    this.mark(node.left);
    if (node.operatorToken.kind === ts.SyntaxKind.EqualsToken) this.bind(node.left, node.right);
  }

  visit(node) {
    if (ts.isBlock(node)) return this.statements(node.statements);
    if (ts.isReturnStatement(node) || ts.isThrowStatement(node)) {
      if (node.expression) this.visit(node.expression);
      return false;
    }
    if (ts.isWhileStatement(node) || ts.isForStatement(node)
        || ts.isForOfStatement(node) || ts.isForInStatement(node)) return this.loop(node);
    if (ts.isFunctionLike(node) || ts.isClassLike(node)) return;
    if (ts.isIfStatement(node) || ts.isConditionalExpression(node)) {
      this.visit(node.expression ?? node.condition);
      return this.branches([node.thenStatement ?? node.whenTrue, node.elseStatement ?? node.whenFalse]);
    }
    if (ts.isVariableDeclaration(node) && node.initializer) {
      this.visit(node.initializer);
      this.bind(node.name, node.initializer);
      return;
    }
    if (ts.isBinaryExpression(node) && node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment
        && node.operatorToken.kind <= ts.SyntaxKind.LastAssignment) return this.assignment(node);
    this.mutation(node);
    ts.forEachChild(node, (child) => this.visit(child));
  }

  mutation(node) {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
      const { expression, name } = node.expression;
      if (MUTATORS.has(name.text)) this.markCall(expression);
    }
    if (ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) {
      this.markUnary(node);
    }
    if (ts.isDeleteExpression(node)) this.mark(node.expression);
  }

  markCall(expression) {
    for (const parameter of this.aliases(expression)) this.outputs.add(parameter);
  }

  markUnary(node) {
    if ([ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(node.operator)) this.mark(node.operand);
  }

}

function outputNames(functionNode, checker) {
  const mutations = new Mutations(functionNode, checker);
  mutations.visit(functionNode.body);
  return mutations.outputs;
}

module.exports = { outputNames };
