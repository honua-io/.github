// Reads [{path, text}] JSON on stdin; writes {path: {tokens, comments, functions, error}} JSON on stdout.
// Tokens come from the TypeScript parser's tree, so regex, template and JSX text lex exactly as the compiler sees them.
const ts = require("typescript");

const SCRIPT_KINDS = {
  ".ts": ts.ScriptKind.TS, ".mts": ts.ScriptKind.TS, ".cts": ts.ScriptKind.TS, ".tsx": ts.ScriptKind.TSX,
  ".js": ts.ScriptKind.JS, ".mjs": ts.ScriptKind.JS, ".cjs": ts.ScriptKind.JS, ".jsx": ts.ScriptKind.JSX,
};
const TEST_BLOCKS = new Set(["describe", "context", "suite", "it", "test", "beforeEach", "afterEach", "beforeAll", "afterAll"]);
const LINE_BREAK = /[\r\n\u2028\u2029]/;

function scriptKind(path) {
  const dot = path.lastIndexOf(".");
  return SCRIPT_KINDS[path.slice(dot)] ?? ts.ScriptKind.TS;
}

function lineOf(source, position) {
  return source.getLineAndCharacterOfPosition(position).line + 1;
}

function isJsDoc(node) {
  return node.kind >= ts.SyntaxKind.FirstJSDocNode && node.kind <= ts.SyntaxKind.LastJSDocNode;
}

function isEmptyJsxExpression(node) {
  return node.kind === ts.SyntaxKind.JsxExpression && !node.expression;
}

function normalizeJsxText(text) {
  return text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).join(" ");
}

// Adjacent JSX text runs are merged before normalizing, so deleting a {/* comment */} between them is a no-op.
function collectTokens(source) {
  const tokens = [];
  const push = (node) => {
    const trivia = source.text.slice(node.getFullStart(), node.getStart(source));
    const isJsxText = node.kind === ts.SyntaxKind.JsxText;
    const previous = tokens[tokens.length - 1];
    const text = isJsxText ? node.getFullText(source) : node.getText(source);
    if (isJsxText && previous?.isJsxText) return void (previous.text += text);
    tokens.push({ text, line: lineOf(source, node.getStart(source)), newline: LINE_BREAK.test(trivia), isJsxText });
  };
  const visit = (node) => {
    if (isJsDoc(node) || isEmptyJsxExpression(node)) return;
    const children = node.getChildren(source);
    if (children.length > 0) return children.forEach(visit);
    if (node.getText(source)) push(node);
  };
  visit(source);
  return tokens
    .map((token) => [token.isJsxText ? normalizeJsxText(token.text) : token.text, token.line, token.newline ? "\n" : ""])
    .filter(([text]) => text);
}

function collectComments(source) {
  const comments = [];
  const seen = new Set();
  const addRange = (start, end) => {
    if (seen.has(start)) return;
    seen.add(start);
    const first = lineOf(source, start);
    source.text.slice(start, end).split("\n").forEach((text, index) => comments.push([first + index, text]));
  };
  const visit = (node) => {
    ts.forEachLeadingCommentRange(source.text, node.getFullStart(), addRange);
    ts.forEachTrailingCommentRange(source.text, node.getEnd(), addRange);
    node.getChildren(source).forEach(visit);
  };
  visit(source);
  return comments.sort((a, b) => a[0] - b[0]);
}

function isTestBlockCallback(node) {
  const call = node.parent;
  if (!call || !ts.isCallExpression(call) || !call.arguments.includes(node)) return false;
  let callee = call.expression;
  while (ts.isCallExpression(callee) || ts.isPropertyAccessExpression(callee)) callee = callee.expression;
  return ts.isIdentifier(callee) && TEST_BLOCKS.has(callee.text);
}

function functionName(node, source) {
  if (node.name) return node.name.getText(source);
  if (node.parent && ts.isVariableDeclaration(node.parent)) return node.parent.name.getText(source);
  if (node.parent && ts.isPropertyAssignment(node.parent)) return node.parent.name.getText(source);
  return node.kind === ts.SyntaxKind.Constructor ? "constructor" : "<anonymous>";
}

function collectFunctions(source) {
  const functions = [];
  const visit = (node) => {
    if (ts.isFunctionLike(node) && node.body && !isTestBlockCallback(node)) {
      functions.push([functionName(node, source), lineOf(source, node.getStart(source)), lineOf(source, node.getEnd())]);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return functions;
}

function lex({ path, text }) {
  const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, scriptKind(path));
  const diagnostics = source.parseDiagnostics ?? [];
  const error = diagnostics.length ? ts.flattenDiagnosticMessageText(diagnostics[0].messageText, " ") : null;
  return { tokens: collectTokens(source), comments: collectComments(source), functions: collectFunctions(source), error };
}

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const results = Object.fromEntries(JSON.parse(input).map((file) => [file.path, lex(file)]));
  process.stdout.write(JSON.stringify(results));
});
