// Resolve lexical bindings before tracking direct mutations of caller-owned collections.
const ts = require("typescript");
const MUTATORS = new Set([
  "push", "pop", "shift", "unshift", "splice", "sort", "reverse", "fill", "copyWithin",
  "add", "set", "delete", "clear",
]);

const HANDLERS = new Map([
  [ts.SyntaxKind.Block, "block"],
  [ts.SyntaxKind.TryStatement, "tryStatement"],
  [ts.SyntaxKind.ReturnStatement, "terminate"],
  [ts.SyntaxKind.ThrowStatement, "terminate"],
  [ts.SyntaxKind.WhileStatement, "loop"],
  [ts.SyntaxKind.ForStatement, "loop"],
  [ts.SyntaxKind.ForOfStatement, "loop"],
  [ts.SyntaxKind.ForInStatement, "loop"],
  [ts.SyntaxKind.IfStatement, "branch"],
  [ts.SyntaxKind.ConditionalExpression, "branch"],
  [ts.SyntaxKind.VariableDeclaration, "declaration"],
  [ts.SyntaxKind.BinaryExpression, "assignment"],
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
    this.exits = [];
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

  collectionLoop(node) {
    return ts.isForOfStatement(node) || ts.isForInStatement(node);
  }

  loopTarget(node) {
    return ts.isVariableDeclarationList(node.initializer)
      ? node.initializer.declarations[0].name : node.initializer;
  }

  loop(node) {
    if (node.initializer && !this.collectionLoop(node)) this.visit(node.initializer);
    const condition = node.condition ?? node.expression;
    if (condition) this.visit(condition);
    const initial = copyBindings(this.bindings);
    if (this.collectionLoop(node)) this.bind(this.loopTarget(node), undefined);
    const fallsThrough = this.visit(node.statement) !== false;
    if (node.incrementor && fallsThrough) this.visit(node.incrementor);
    this.bindings = mergeBindings(fallsThrough ? [initial, this.bindings] : [initial]);
  }

  capturedBlock(block) {
    this.exits.push([]);
    const normal = this.visit(block) !== false;
    const exits = this.exits.pop();
    if (this.exits.length) this.exits.at(-1).push(...exits);
    return { normal, exits };
  }

  exceptionPaths(node) {
    const { normal, exits } = this.capturedBlock(node.tryBlock);
    const exceptional = mergeBindings(exits.filter((exit) => exit.throws).map((exit) => exit.bindings));
    const paths = [{ bindings: this.bindings, normal }, { bindings: mergeBindings(exits.map((exit) => exit.bindings)), normal: false }];
    if (node.catchClause) {
      this.bindings = copyBindings(exceptional);
      if (node.catchClause.variableDeclaration) this.bind(node.catchClause.variableDeclaration.name, undefined);
      const caught = this.capturedBlock(node.catchClause.block);
      paths.push({ bindings: this.bindings, normal: caught.normal });
      paths.push({ bindings: mergeBindings(caught.exits.map((exit) => exit.bindings)), normal: false });
    }
    return paths;
  }

  tryStatement(node) {
    const endings = [];
    for (const path of this.exceptionPaths(node)) {
      this.bindings = copyBindings(path.bindings);
      const normal = !node.finallyBlock || this.visit(node.finallyBlock) !== false;
      if (normal && path.normal) endings.push(this.bindings);
    }
    this.bindings = mergeBindings(endings);
    return endings.length > 0;
  }

  assignment(node) {
    if ([ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken].includes(node.operatorToken.kind)) {
      this.visit(node.left);
      this.branches([undefined, node.right]);
      return;
    }
    if (node.operatorToken.kind < ts.SyntaxKind.FirstAssignment
        || node.operatorToken.kind > ts.SyntaxKind.LastAssignment) {
      ts.forEachChild(node, (child) => { this.visit(child); });
      return;
    }
    this.visit(node.right);
    this.visit(node.left);
    this.mark(node.left);
    if (node.operatorToken.kind === ts.SyntaxKind.EqualsToken) this.bind(node.left, node.right);
  }

  block(node) {
    return this.statements(node.statements);
  }

  terminate(node) {
    if (node.expression) this.visit(node.expression);
    return false;
  }

  branch(node) {
    this.visit(node.expression ?? node.condition);
    return this.branches([node.thenStatement ?? node.whenTrue, node.elseStatement ?? node.whenFalse]);
  }

  declaration(node) {
    if (!node.initializer) return;
    this.visit(node.initializer);
    this.bind(node.name, node.initializer);
  }

  visit(node) {
    if (ts.isFunctionLike(node) || ts.isClassLike(node)) return;
    if (this.exits.length && (ts.isCallExpression(node) || ts.isNewExpression(node)
        || ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)
        || ts.isReturnStatement(node) || ts.isThrowStatement(node))) {
      this.exits.at(-1).push({ bindings: copyBindings(this.bindings), throws: !ts.isReturnStatement(node) });
    }
    const handler = HANDLERS.get(node.kind);
    if (handler) return this[handler](node);
    this.mutation(node);
    ts.forEachChild(node, (child) => { this.visit(child); });
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
