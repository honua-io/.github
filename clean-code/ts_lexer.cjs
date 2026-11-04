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

// The JSX transform's whitespace rule: inner lines are trimmed, blank lines dropped, the rest joined by spaces.
function jsxChildText(raw) {
  const lines = raw.replace(/\t/g, " ").split(/\r\n|\n|\r/);
  const lastNonEmpty = lines.reduce((last, line, index) => (/[^ ]/.test(line) ? index : last), -1);
  return lines
    .map((line, index) => (index === 0 ? line : line.replace(/^ +/, "")))
    .map((line, index) => (index === lines.length - 1 ? line : line.replace(/ +$/, "")))
    .map((line, index) => (line && index !== lastNonEmpty ? `${line} ` : line))
    .join("");
}

// Each JSX text child stays separate: deleting a {/* comment */} between two texts changes the children.
function collectTokens(source) {
  const tokens = [];
  const visit = (node) => {
    if (isJsDoc(node) || isEmptyJsxExpression(node)) return;
    const children = node.getChildren(source);
    if (children.length > 0) return children.forEach(visit);
    const isJsxText = node.kind === ts.SyntaxKind.JsxText;
    const text = isJsxText ? jsxChildText(node.getFullText(source)) : node.getText(source);
    if (!text) return;
    const trivia = source.text.slice(node.getFullStart(), node.getStart(source));
    tokens.push([text, lineOf(source, node.getStart(source)), !isJsxText && LINE_BREAK.test(trivia) ? "\n" : ""]);
  };
  visit(source);
  return tokens;
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
