// Resolve lexical bindings before tracking direct mutations of caller-owned collections.
const ts = require("typescript");
const { unwrap, copyBindings, sameBindings, mergeBindings, patternEntries, loopLabels, mutatorName } = require("./ts_output_support.cjs");
const MUTATORS = new Set([
  "push", "pop", "shift", "unshift", "splice", "sort", "reverse", "fill", "copyWithin",
  "add", "set", "delete", "clear",
]);

const HANDLERS = new Map([
  [ts.SyntaxKind.Block, "block"],
  [ts.SyntaxKind.LabeledStatement, "labeled"],
  [ts.SyntaxKind.CallExpression, "call"],
  [ts.SyntaxKind.TryStatement, "tryStatement"],
  [ts.SyntaxKind.SwitchStatement, "switchStatement"],
  [ts.SyntaxKind.ReturnStatement, "terminate"],
  [ts.SyntaxKind.ThrowStatement, "terminate"],
  [ts.SyntaxKind.BreakStatement, "terminate"],
  [ts.SyntaxKind.ContinueStatement, "terminate"],
  [ts.SyntaxKind.WhileStatement, "loop"],
  [ts.SyntaxKind.DoStatement, "loop"],
  [ts.SyntaxKind.ForStatement, "loop"],
  [ts.SyntaxKind.ForOfStatement, "loop"],
  [ts.SyntaxKind.ForInStatement, "loop"],
  [ts.SyntaxKind.IfStatement, "branch"],
  [ts.SyntaxKind.ConditionalExpression, "branch"],
  [ts.SyntaxKind.VariableDeclaration, "declaration"],
  [ts.SyntaxKind.BinaryExpression, "assignment"],
]);

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
    node = unwrap(node);
    if (!node) return new Set();
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      return this.aliases(node.right);
    }
    const symbol = ts.isIdentifier(node) ? this.checker.getSymbolAtLocation(node) : undefined;
    return new Set(symbol ? this.bindings.get(symbol) ?? [] : []);
  }

  bind(target, value) {
    const entries = patternEntries(target, value).map(([name, source]) => [name, this.aliases(source)]);
    for (const [name, aliases] of entries) {
      if (ts.isIdentifier(name)) this.bindings.set(this.checker.getSymbolAtLocation(name), aliases);
    }
  }

  mutationAliases(target) {
    target = unwrap(target);
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
    if (condition && !ts.isDoStatement(node)) this.visit(condition);
    const broken = ts.isDoStatement(node) ? this.loopIteration(node) : [];
    let initial;
    do {
      initial = copyBindings(this.bindings);
      broken.push(...this.loopIteration(node));
      this.bindings = mergeBindings([initial, this.bindings]);
    } while (!sameBindings(initial, this.bindings));
    this.bindings = mergeBindings([this.bindings, ...broken]);
  }

  loopIteration(node) {
    const broken = [];
    if (this.collectionLoop(node)) {
      const target = this.loopTarget(node);
      this.record(this.evaluatedReceiver(target));
      this.bind(target, undefined);
    }
    const { normal, exits } = this.capturedBlock(node.statement);
    const continuing = normal ? [this.bindings] : [];
    for (const exit of exits) this.loopExit(exit, { broken, continuing, labels: loopLabels(node) });
    this.bindings = mergeBindings(continuing);
    if (!continuing.length) return broken;
    if (node.incrementor) this.visit(node.incrementor);
    const condition = ts.isWhileStatement(node) || ts.isDoStatement(node) ? node.expression : node.condition;
    if (condition) this.visit(condition);
    return broken;
  }

  loopExit(exit, paths) {
    if (exit.label && !paths.labels.has(exit.label)) {
      if (this.exits.length) this.exits.at(-1).push(exit);
    } else if (exit.kind === "break") paths.broken.push(exit.bindings);
    else if (exit.kind === "continue") paths.continuing.push(exit.bindings);
    else if (this.exits.length) this.exits.at(-1).push(exit);
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
      this.exits.at(-1).push({ ...path, bindings: copyBindings(this.bindings) });
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
    const receiver = this.evaluatedReceiver(node.left);
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

  evaluatedReceiver(target) {
    const entries = patternEntries(target, undefined);
    return new Set(entries.flatMap(([entry]) => [...this.directReceiver(entry)]));
  }

  directReceiver(target) {
    target = unwrap(target);
    if (!ts.isElementAccessExpression(target) && !ts.isPropertyAccessExpression(target)) {
      this.visit(target);
      return new Set();
    }
    this.visit(target.expression);
    const receiver = this.aliases(target.expression);
    if (target.argumentExpression) this.visit(target.argumentExpression);
    if (this.exits.length) this.exits.at(-1).push({ bindings: copyBindings(this.bindings), kind: "throw" });
    return receiver;
  }

  switchStatement(node) {
    this.visit(node.expression);
    const clauses = node.caseBlock.clauses;
    const starts = [];
    for (const clause of clauses) {
      if (clause.expression) this.visit(clause.expression);
      starts.push(copyBindings(this.bindings));
    }
    const unmatched = copyBindings(this.bindings);
    const endings = clauses.some(ts.isDefaultClause) ? [] : [unmatched];
    for (let index = 0; index < clauses.length; index++) {
      this.bindings = copyBindings(ts.isDefaultClause(clauses[index]) ? unmatched : starts[index]);
      endings.push(...this.switchPath(clauses.slice(index)));
    }
    this.bindings = mergeBindings(endings);
    return endings.length > 0;
  }

  switchPath(clauses) {
    this.exits.push([]);
    const normal = this.statements(clauses.flatMap((clause) => [...clause.statements]));
    const exits = this.exits.pop();
    const endings = normal ? [this.bindings] : [];
    for (const exit of exits) {
      if (exit.kind === "break" && !exit.label) endings.push(exit.bindings);
      else if (this.exits.length) this.exits.at(-1).push(exit);
    }
    return endings;
  }

  labeled(node) {
    const { normal, exits } = this.capturedBlock(node.statement);
    const endings = normal ? [this.bindings] : [];
    for (const exit of exits) {
      if (exit.kind === "break" && exit.label === node.label.text) endings.push(exit.bindings);
      else if (this.exits.length) this.exits.at(-1).push(exit);
    }
    this.bindings = mergeBindings(endings);
    return endings.length > 0;
  }

  block(node) {
    return this.statements(node.statements);
  }

  terminate(node) {
    if (node.expression) this.visit(node.expression);
    if (this.exits.length) {
      this.exits.at(-1).push({ bindings: copyBindings(this.bindings), label: node.label?.text, kind: ts.tokenToString(node.kind) ?? ts.SyntaxKind[node.kind].replace("Statement", "").toLowerCase() });
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
    const callee = unwrap(node.expression);
    const receiver = MUTATORS.has(mutatorName(callee))
      ? this.aliases(callee.expression) : new Set();
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
