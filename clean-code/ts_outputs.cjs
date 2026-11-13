// Resolve lexical bindings before tracking direct mutations of caller-owned collections.
const ts = require("typescript");
const MUTATORS = new Set([
  "push", "pop", "shift", "unshift", "splice", "sort", "reverse", "fill", "copyWithin",
  "add", "set", "delete", "clear",
]);

const HANDLERS = new Map([
  [ts.SyntaxKind.Block, "block"],
  [ts.SyntaxKind.CallExpression, "call"],
  [ts.SyntaxKind.TryStatement, "tryStatement"],
  [ts.SyntaxKind.ReturnStatement, "terminate"],
  [ts.SyntaxKind.ThrowStatement, "terminate"],
  [ts.SyntaxKind.BreakStatement, "terminate"],
  [ts.SyntaxKind.ContinueStatement, "terminate"],
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
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      return this.aliases(node.right);
    }
    const symbol = ts.isIdentifier(node) ? this.checker.getSymbolAtLocation(node) : undefined;
    return new Set(symbol ? this.bindings.get(symbol) ?? [] : []);
  }

  bind(target, value) {
    if (ts.isIdentifier(target)) {
      this.bindings.set(this.checker.getSymbolAtLocation(target), this.aliases(value));
    }
  }

  mutationAliases(target) {
    return ts.isElementAccessExpression(target) || ts.isPropertyAccessExpression(target)
      ? this.aliases(target.expression) : new Set();
  }

  record(names) {
    for (const name of names) this.outputs.add(name);
  }

  mark(target) {
    this.record(this.mutationAliases(target));
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
    const broken = [];
    let initial;
    do {
      initial = copyBindings(this.bindings);
      this.loopIteration(node, broken);
      this.bindings = mergeBindings([initial, this.bindings]);
    } while (!sameBindings(initial, this.bindings));
    this.bindings = mergeBindings([this.bindings, ...broken]);
  }

  loopIteration(node, broken) {
    if (this.collectionLoop(node)) this.bind(this.loopTarget(node), undefined);
    const { normal, exits } = this.capturedBlock(node.statement);
    const continuing = normal ? [this.bindings] : [];
    for (const exit of exits) {
      if (exit.kind === "break") broken.push(exit.bindings);
      else if (exit.kind === "continue") continuing.push(exit.bindings);
      else if (this.exits.length) this.exits.at(-1).push(exit);
    }
    this.bindings = mergeBindings(continuing);
    if (!continuing.length) return;
    if (node.incrementor) this.visit(node.incrementor);
    if (node.condition) this.visit(node.condition);
  }

  capturedBlock(block) {
    this.exits.push([]);
    const normal = this.visit(block) !== false;
    const exits = this.exits.pop();
    return { normal, exits };
  }

  exceptionPaths(node) {
    const { normal, exits } = this.capturedBlock(node.tryBlock);
    const exceptional = mergeBindings(exits.filter((exit) => exit.kind === "throw").map((exit) => exit.bindings));
    const paths = normal ? [{ bindings: this.bindings, normal: true }] : [];
    paths.push(...exits.filter((exit) => exit.kind !== "throw" || !node.catchClause)
      .map((exit) => ({ ...exit, normal: false })));
    if (node.catchClause && exits.some((exit) => exit.kind === "throw")) {
      this.bindings = copyBindings(exceptional);
      if (node.catchClause.variableDeclaration) this.bind(node.catchClause.variableDeclaration.name, undefined);
      const caught = this.capturedBlock(node.catchClause.block);
      if (caught.normal) paths.push({ bindings: this.bindings, normal: true });
      paths.push(...caught.exits.map((exit) => ({ ...exit, normal: false })));
    }
    return paths;
  }

  tryStatement(node) {
    const endings = [];
    for (const path of this.exceptionPaths(node)) {
      this.bindings = copyBindings(path.bindings);
      const final = node.finallyBlock ? this.capturedBlock(node.finallyBlock) : { normal: true, exits: [] };
      this.propagateFinal(path, final);
      if (final.normal && path.normal) endings.push(this.bindings);
    }
    this.bindings = mergeBindings(endings);
    return endings.length > 0;
  }

  propagateFinal(path, final) {
    if (!this.exits.length) return;
    this.exits.at(-1).push(...final.exits);
    if (final.normal && !path.normal) {
      this.exits.at(-1).push({ bindings: copyBindings(this.bindings), kind: path.kind });
    }
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
    this.visit(node.left);
    const receiver = this.mutationAliases(node.left);
    if ([ts.SyntaxKind.AmpersandAmpersandEqualsToken, ts.SyntaxKind.BarBarEqualsToken,
      ts.SyntaxKind.QuestionQuestionEqualsToken].includes(node.operatorToken.kind)) {
      const skipped = copyBindings(this.bindings);
      this.visit(node.right);
      this.record(receiver);
      this.bind(node.left, node.right);
      this.bindings = mergeBindings([skipped, this.bindings]);
      return;
    }
    this.visit(node.right);
    this.record(receiver);
    if (node.operatorToken.kind === ts.SyntaxKind.EqualsToken) this.bind(node.left, node.right);
  }

  block(node) {
    return this.statements(node.statements);
  }

  terminate(node) {
    if (node.expression) this.visit(node.expression);
    if (this.exits.length) {
      this.exits.at(-1).push({ bindings: copyBindings(this.bindings), kind: ts.tokenToString(node.kind) ?? ts.SyntaxKind[node.kind].replace("Statement", "").toLowerCase() });
    }
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
    const handler = HANDLERS.get(node.kind);
    let result;
    if (handler) result = this[handler](node);
    else {
      this.mutation(node);
      ts.forEachChild(node, (child) => { this.visit(child); });
    }
    if (this.exits.length && (ts.isCallExpression(node) || ts.isNewExpression(node)
        || ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node))) {
      this.exits.at(-1).push({ bindings: copyBindings(this.bindings), kind: "throw" });
    }
    return result;
  }

  call(node) {
    this.visit(node.expression);
    const receiver = ts.isPropertyAccessExpression(node.expression) && MUTATORS.has(node.expression.name.text)
      ? this.aliases(node.expression.expression) : new Set();
    for (const argument of node.arguments) this.visit(argument);
    this.record(receiver);
  }

  mutation(node) {
    if (ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) {
      this.markUnary(node);
    }
    if (ts.isDeleteExpression(node)) this.mark(node.expression);
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
